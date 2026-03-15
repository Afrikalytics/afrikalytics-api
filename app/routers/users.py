"""
Router utilisateurs — /api/users/* et /api/enterprise/*
Extrait de main.py.

Endpoints:
    POST   /api/users/create              — Creation via Zapier (webhook)
    GET    /api/users/me                   — Profil utilisateur courant
    GET    /api/users/quota               — Quotas/tokens de l'utilisateur
    GET    /api/users/{user_id}            — Detail utilisateur
    PUT    /api/users/{user_id}/deactivate — Desactiver utilisateur (Zapier)
    PUT    /api/users/change-password      — Changer mot de passe
    GET    /api/enterprise/team            — Lister les membres equipe entreprise
    POST   /api/enterprise/team/add        — Ajouter un membre
    DELETE /api/enterprise/team/{member_id} — Retirer un membre
"""
import logging
import secrets
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Header, Request
from sqlalchemy import select, func
from sqlalchemy.orm import Session
from typing import Optional

from app.config import get_settings
from app.database import get_db
from app.models import User, Subscription, TokenBlacklist
from app.auth import hash_password, verify_password, decode_access_token
from app.dependencies import get_current_user
from app.schemas.auth import UserResponse
from app.schemas.users import UserCreate, PasswordChange, EnterpriseUserAdd
from app.services.email import send_email
from app.services.email_templates import (
    password_changed_email,
    enterprise_team_join_email,
    enterprise_team_invite_email,
    enterprise_team_removal_email,
)
from app.utils import calculate_days_remaining, validate_password
from app.rate_limit import limiter

logger = logging.getLogger(__name__)

settings = get_settings()

# Quotas de tokens par plan (limites mensuelles)
PLAN_QUOTAS = {
    "basic": {
        "reports_downloads": 3,
        "insights_access": 5,
        "studies_participation": 5,
        "api_requests": 100,
    },
    "professionnel": {
        "reports_downloads": 50,
        "insights_access": -1,  # -1 = illimite
        "studies_participation": -1,
        "api_requests": 5000,
    },
    "entreprise": {
        "reports_downloads": -1,
        "insights_access": -1,
        "studies_participation": -1,
        "api_requests": -1,
    },
}

router = APIRouter(tags=["Users"])

ZAPIER_SECRET = settings.zapier_secret
if not ZAPIER_SECRET:
    logger.warning("ZAPIER_SECRET is not set. Zapier endpoints will return 503.")


# ==================== ZAPIER WEBHOOK ====================

@router.post("/api/users/create")
@limiter.limit("10/minute")
def create_user_from_zapier(
    request: Request,
    data: UserCreate,
    db: Session = Depends(get_db),
    x_zapier_secret: Optional[str] = Header(None),
):
    """
    Creer un utilisateur apres paiement WooCommerce (appele par Zapier).
    """
    if not ZAPIER_SECRET:
        raise HTTPException(status_code=503, detail="Zapier integration not configured")
    if not x_zapier_secret or x_zapier_secret != ZAPIER_SECRET:
        raise HTTPException(status_code=401, detail="Unauthorized")

    existing_user = db.execute(
        select(User).where(User.email == data.email)
    ).scalar_one_or_none()
    if existing_user:
        existing_user.plan = data.plan
        existing_user.is_active = True
        db.commit()
        return {
            "message": "User updated",
            "user_id": existing_user.id,
            "email": existing_user.email,
            "dashboard_url": "https://dashboard.afrikalytics.com"
        }

    temp_password = secrets.token_urlsafe(12)
    hashed_password = hash_password(temp_password)

    new_user = User(
        email=data.email,
        full_name=data.name,
        hashed_password=hashed_password,
        plan=data.plan,
        order_id=data.order_id,
        is_active=True
    )

    db.add(new_user)
    db.commit()
    db.refresh(new_user)

    return {
        "message": "User created successfully",
        "user_id": new_user.id,
        "email": new_user.email,
        "dashboard_url": "https://dashboard.afrikalytics.com"
    }


# ==================== USER PROFILE ====================

@router.get("/api/users/me", response_model=UserResponse)
@limiter.limit("30/minute")
def get_current_user_info(request: Request, current_user: User = Depends(get_current_user)):
    """Recuperer le profil de l'utilisateur connecte."""
    return current_user


@router.get("/api/users/quota")
@limiter.limit("30/minute")
def get_user_quota(
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Retourner les quotas/tokens de l'utilisateur selon son plan.
    Calcule l'utilisation du mois en cours.
    """
    plan = current_user.plan or "basic"
    quotas = PLAN_QUOTAS.get(plan, PLAN_QUOTAS["basic"])

    # Debut du mois en cours
    now = datetime.now(timezone.utc)
    month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)

    # TODO: A per-user download tracking table is needed to accurately count
    # downloads per user per month. Until then, we return 0 to avoid the previous
    # bug that counted ALL reports with downloads globally.
    reports_used = 0

    # Jours restants d'abonnement
    days_remaining = None
    subscription_end = None
    if plan in ["professionnel", "entreprise"]:
        subscription = db.execute(
            select(Subscription).where(
                Subscription.user_id == current_user.id,
                Subscription.status == "active",
            )
        ).scalar_one_or_none()
        if subscription and subscription.end_date:
            days_remaining = calculate_days_remaining(subscription.end_date)
            subscription_end = subscription.end_date.isoformat()

    # Construire la reponse avec les tokens
    tokens = []
    for key, limit in quotas.items():
        token_info = {
            "name": key,
            "limit": limit,
            "unlimited": limit == -1,
        }

        # Ajouter les valeurs d'utilisation connues
        if key == "reports_downloads":
            token_info["used"] = min(reports_used, limit) if limit > 0 else reports_used
        else:
            token_info["used"] = 0  # A enrichir avec un vrai tracking

        if limit > 0:
            token_info["remaining"] = max(0, limit - token_info["used"])
            token_info["percentage"] = round((token_info["used"] / limit) * 100, 1)
        else:
            token_info["remaining"] = None
            token_info["percentage"] = 0

        tokens.append(token_info)

    return {
        "plan": plan,
        "tokens": tokens,
        "days_remaining": days_remaining,
        "subscription_end": subscription_end,
        "billing_period_start": month_start.isoformat(),
    }


@router.get("/api/users/{user_id}", response_model=UserResponse)
@limiter.limit("30/minute")
def get_user(
    request: Request,
    user_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Recuperer un utilisateur par son ID (authentification requise)."""
    # Non-admin users can only view their own profile
    if not current_user.is_admin and current_user.id != user_id:
        raise HTTPException(status_code=403, detail="Accès non autorisé")

    user = db.execute(
        select(User).where(User.id == user_id)
    ).scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="Utilisateur non trouvé")
    return user


@router.put("/api/users/{user_id}/deactivate")
@limiter.limit("10/minute")
def deactivate_user(
    request: Request,
    user_id: int,
    db: Session = Depends(get_db),
    x_zapier_secret: Optional[str] = Header(None),
):
    """Desactiver un utilisateur (appele par Zapier)."""
    if not ZAPIER_SECRET:
        raise HTTPException(status_code=503, detail="Zapier integration not configured")
    if not x_zapier_secret or x_zapier_secret != ZAPIER_SECRET:
        raise HTTPException(status_code=401, detail="Unauthorized")

    user = db.execute(
        select(User).where(User.id == user_id)
    ).scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="Utilisateur non trouvé")

    user.is_active = False
    db.commit()

    return {"message": "Utilisateur désactivé", "user_id": user_id}


@router.put("/api/users/change-password")
@limiter.limit("10/minute")
def change_password(
    request: Request,
    data: PasswordChange,
    authorization: str = Header(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Changer le mot de passe de l'utilisateur connecte."""
    # Verifier l'ancien mot de passe
    if not verify_password(data.current_password, current_user.hashed_password):
        raise HTTPException(status_code=400, detail="Mot de passe actuel incorrect")

    # Valider le nouveau mot de passe
    is_valid, error_message = validate_password(data.new_password)
    if not is_valid:
        raise HTTPException(status_code=400, detail=error_message)

    # Mettre a jour le mot de passe
    current_user.hashed_password = hash_password(data.new_password)

    # Blacklist the current token to force re-authentication
    if authorization and authorization.startswith("Bearer "):
        token = authorization.replace("Bearer ", "")
        payload = decode_access_token(token)
        if payload:
            jti = payload.get("jti")
            if jti:
                existing = db.execute(
                    select(TokenBlacklist).where(TokenBlacklist.jti == jti)
                ).scalar_one_or_none()
                if not existing:
                    blacklisted = TokenBlacklist(
                        jti=jti,
                        user_id=current_user.id,
                        expires_at=datetime.fromtimestamp(payload.get("exp")),
                    )
                    db.add(blacklisted)

    db.commit()

    # Envoyer email de confirmation
    send_email(
        to=current_user.email,
        subject="Mot de passe modifié - Afrikalytics",
        html=password_changed_email(current_user.full_name),
    )

    return {"message": "Mot de passe modifié avec succès"}


# ==================== FORFAIT ENTREPRISE ====================

@router.get("/api/enterprise/team")
@limiter.limit("30/minute")
def get_enterprise_team(
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Recuperer les membres de l'equipe entreprise (proprietaire uniquement).
    """
    if current_user.plan != "entreprise":
        raise HTTPException(
            status_code=403,
            detail="Cette fonctionnalité est réservée au plan Entreprise"
        )

    # Seul le proprietaire peut gerer l'equipe (pas les membres invites)
    if current_user.parent_user_id is not None:
        raise HTTPException(
            status_code=403,
            detail="Seul le propriétaire du compte peut gérer l'équipe"
        )

    # Recuperer les sous-utilisateurs
    team_members = db.execute(
        select(User).where(User.parent_user_id == current_user.id)
    ).scalars().all()

    return {
        "owner": {
            "id": current_user.id,
            "email": current_user.email,
            "full_name": current_user.full_name
        },
        "team_members": [
            {
                "id": m.id,
                "email": m.email,
                "full_name": m.full_name,
                "is_active": m.is_active,
                "created_at": m.created_at.isoformat()
            } for m in team_members
        ],
        "max_members": 5,
        "current_count": len(team_members) + 1  # +1 pour le proprietaire
    }


@router.post("/api/enterprise/team/add")
@limiter.limit("10/minute")
def add_enterprise_team_member(
    request: Request,
    data: EnterpriseUserAdd,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Ajouter un membre a l'equipe entreprise (max 5 total, proprietaire uniquement).
    Gere les cas : nouveau compte, utilisateur Basic existant, utilisateur Pro existant.
    """
    if current_user.plan != "entreprise":
        raise HTTPException(
            status_code=403,
            detail="Cette fonctionnalité est réservée au plan Entreprise"
        )

    # Seul le proprietaire peut ajouter des membres
    if current_user.parent_user_id is not None:
        raise HTTPException(
            status_code=403,
            detail="Seul le propriétaire du compte peut ajouter des membres"
        )

    # Compter les membres actuels
    current_members = db.execute(
        select(func.count()).select_from(User).where(
            User.parent_user_id == current_user.id
        )
    ).scalar()

    if current_members >= 4:  # 4 membres + 1 proprietaire = 5 max
        raise HTTPException(
            status_code=400,
            detail="Limite de 5 utilisateurs atteinte pour votre forfait Entreprise"
        )

    # Verifier si l'email existe deja
    existing_user = db.execute(
        select(User).where(User.email == data.email)
    ).scalar_one_or_none()

    if existing_user:
        # CAS : Utilisateur deja dans une equipe entreprise
        if existing_user.plan == "entreprise":
            if existing_user.parent_user_id is None:
                raise HTTPException(
                    status_code=400,
                    detail="Cet utilisateur est déjà propriétaire d'une équipe Entreprise"
                )
            else:
                raise HTTPException(
                    status_code=400,
                    detail="Cet utilisateur fait déjà partie d'une équipe Entreprise"
                )

        # CAS : Utilisateur Basic ou Professionnel -> Peut rejoindre l'equipe
        old_plan = existing_user.plan

        # Si l'utilisateur avait un abonnement Professionnel, on l'annule
        if old_plan == "professionnel":
            active_subscription = db.execute(
                select(Subscription).where(
                    Subscription.user_id == existing_user.id,
                    Subscription.status == "active"
                )
            ).scalar_one_or_none()

            if active_subscription:
                active_subscription.status = "cancelled"
                active_subscription.end_date = datetime.now(timezone.utc)

        # Mettre a jour l'utilisateur existant
        existing_user.plan = "entreprise"
        existing_user.parent_user_id = current_user.id

        db.commit()
        db.refresh(existing_user)

        # Email pour utilisateur existant (il garde son mot de passe)
        email_sent = send_email(
            to=existing_user.email,
            subject="Vous avez rejoint une équipe Entreprise sur Afrikalytics",
            html=enterprise_team_join_email(existing_user.full_name, current_user.full_name, old_plan),
        )

        return {
            "message": f"Membre ajouté avec succès (compte existant converti de {old_plan} à entreprise)",
            "member": {
                "id": existing_user.id,
                "email": existing_user.email,
                "full_name": existing_user.full_name
            },
            "converted_from": old_plan,
            "email_sent": email_sent
        }

    # CAS : Nouveau compte -> Creer le membre
    temp_password = secrets.token_urlsafe(12)
    hashed_password = hash_password(temp_password)

    new_member = User(
        email=data.email,
        full_name=data.full_name,
        hashed_password=hashed_password,
        plan="entreprise",
        is_active=True,
        parent_user_id=current_user.id
    )

    db.add(new_member)
    db.commit()
    db.refresh(new_member)

    # Email pour nouveau compte
    send_email(
        to=new_member.email,
        subject="Vous êtes invité(e) à rejoindre Afrikalytics",
        html=enterprise_team_invite_email(new_member.full_name, new_member.email, current_user.full_name, temp_password),
    )

    return {
        "message": "Membre ajouté avec succès (nouveau compte créé)",
        "member": {
            "id": new_member.id,
            "email": new_member.email,
            "full_name": new_member.full_name
        },
        "new_account": True
    }


@router.delete("/api/enterprise/team/{member_id}")
@limiter.limit("5/minute")
def remove_enterprise_team_member(
    request: Request,
    member_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Retirer un membre de l'equipe entreprise (proprietaire uniquement).
    Le membre est retrograde vers le plan Basic (pas supprime).
    """
    if current_user.plan != "entreprise":
        raise HTTPException(
            status_code=403,
            detail="Cette fonctionnalité est réservée au plan Entreprise"
        )

    # Seul le proprietaire peut retirer des membres
    if current_user.parent_user_id is not None:
        raise HTTPException(
            status_code=403,
            detail="Seul le propriétaire du compte peut retirer des membres"
        )

    member = db.execute(
        select(User).where(
            User.id == member_id,
            User.parent_user_id == current_user.id
        )
    ).scalar_one_or_none()

    if not member:
        raise HTTPException(
            status_code=404,
            detail="Membre non trouvé dans votre équipe"
        )

    member_name = member.full_name
    member_email = member.email

    # Retrograder vers Basic au lieu de supprimer
    member.plan = "basic"
    member.parent_user_id = None

    db.commit()

    # Notifier le membre par email
    send_email(
        to=member_email,
        subject="Modification de votre accès Afrikalytics",
        html=enterprise_team_removal_email(member_name, current_user.full_name),
    )

    return {
        "message": f"Membre retiré avec succès. {member_name} a été rétrogradé vers le plan Basic.",
        "member_id": member_id,
        "new_plan": "basic"
    }
