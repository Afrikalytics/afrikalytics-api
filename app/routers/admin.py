"""
Router pour la gestion administrative des utilisateurs.
7 endpoints couvrant les roles, le CRUD utilisateurs et le toggle d'activation.
"""
import html
import secrets
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy.orm import Session

from database import get_db
from models import User, Subscription, AuditLog
from auth import hash_password
from app.dependencies import get_current_user
from app.permissions import check_admin_permission, ADMIN_ROLES
from app.services.email import send_email
from app.services.audit import log_action
from app.schemas.admin import AdminUserCreate, AdminUserUpdate, AdminUserResponse
from app.schemas.audit import AuditLogResponse, AuditLogListResponse

router = APIRouter()


@router.get("/api/admin/roles")
async def get_admin_roles(
    current_user: User = Depends(get_current_user)
):
    """
    Récupérer la liste des rôles admin disponibles.
    Requiert is_admin == True (pas de permission spécifique).
    """
    if not current_user.is_admin:
        raise HTTPException(status_code=403, detail="Accès réservé aux administrateurs")

    return {
        "roles": [
            {
                "code": code,
                "label": info["label"],
                "permissions": {k: v for k, v in info.items() if k != "label"},
            }
            for code, info in ADMIN_ROLES.items()
        ]
    }


@router.get("/api/admin/users", response_model=List[AdminUserResponse])
async def get_all_users(
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Récupérer tous les utilisateurs (Admin avec permission users).
    Supporte la pagination via skip/limit.
    """
    if not check_admin_permission(current_user, "users"):
        raise HTTPException(
            status_code=403,
            detail="Vous n'avez pas la permission de gérer les utilisateurs",
        )

    users = db.query(User).order_by(User.created_at.desc()).offset(skip).limit(limit).all()
    return users


@router.get("/api/admin/users/{user_id}", response_model=AdminUserResponse)
async def get_user_by_id(
    user_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Récupérer un utilisateur par son ID (Admin avec permission users).
    """
    if not check_admin_permission(current_user, "users"):
        raise HTTPException(
            status_code=403,
            detail="Vous n'avez pas la permission de gérer les utilisateurs",
        )

    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="Utilisateur non trouvé")

    return user


@router.post("/api/admin/users", response_model=AdminUserResponse, status_code=201)
async def create_user_admin(
    data: AdminUserCreate,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Créer un utilisateur manuellement (Admin avec permission users).
    Génère un mot de passe aléatoire si non fourni et envoie un email de bienvenue.
    """
    if not check_admin_permission(current_user, "users"):
        raise HTTPException(
            status_code=403,
            detail="Vous n'avez pas la permission de gérer les utilisateurs",
        )

    # Vérifier si l'email existe déjà
    existing_user = db.query(User).filter(User.email == data.email).first()
    if existing_user:
        raise HTTPException(status_code=400, detail="Cet email est déjà utilisé")

    # Générer mot de passe si non fourni
    password = data.password or secrets.token_urlsafe(12)
    hashed_password = hash_password(password)

    # Valider admin_role si fourni
    if data.admin_role and data.admin_role not in ADMIN_ROLES:
        raise HTTPException(
            status_code=400,
            detail=f"Rôle admin invalide. Valeurs possibles: {list(ADMIN_ROLES.keys())}",
        )

    new_user = User(
        email=data.email,
        full_name=data.full_name,
        hashed_password=hashed_password,
        plan=data.plan,
        is_active=data.is_active,
        is_admin=data.is_admin,
        admin_role=data.admin_role if data.is_admin else None,
    )

    db.add(new_user)
    db.commit()
    db.refresh(new_user)

    # Envoyer email de bienvenue
    send_email(
        to=new_user.email,
        subject="Bienvenue sur Afrikalytics AI",
        html=f"""
            <h2>Bienvenue sur Afrikalytics AI !</h2>
            <p>Bonjour {html.escape(new_user.full_name)},</p>
            <p>Votre compte a été créé avec succès.</p>
            <p><strong>Email :</strong> {html.escape(new_user.email)}</p>
            <p><strong>Mot de passe :</strong> {html.escape(password)}</p>
            <p><strong>Plan :</strong> {html.escape(new_user.plan.capitalize())}</p>
            <p style="margin: 30px 0;">
                <a href="https://dashboard.afrikalytics.com/login"
                   style="background-color: #2563eb; color: white; padding: 12px 24px; text-decoration: none; border-radius: 8px; font-weight: bold;">
                    Se connecter
                </a>
            </p>
            <p style="color: #666;">Nous vous recommandons de changer votre mot de passe après votre première connexion.</p>
            <hr>
            <p><em>L'équipe Afrikalytics AI by Marketym</em></p>
        """,
    )

    # Audit log
    try:
        log_action(
            db=db, user_id=current_user.id, action="create", resource_type="user",
            resource_id=new_user.id, details={"email": new_user.email, "plan": new_user.plan},
            request=request,
        )
    except Exception:
        pass

    return new_user


@router.put("/api/admin/users/{user_id}", response_model=AdminUserResponse)
async def update_user_admin(
    user_id: int,
    data: AdminUserUpdate,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Modifier un utilisateur (Admin avec permission users).
    Valide le rôle admin et vérifie l'unicité de l'email.
    """
    if not check_admin_permission(current_user, "users"):
        raise HTTPException(
            status_code=403,
            detail="Vous n'avez pas la permission de gérer les utilisateurs",
        )

    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="Utilisateur non trouvé")

    # Mettre à jour les champs fournis
    if data.email is not None:
        # Vérifier si l'email est déjà utilisé par un autre utilisateur
        existing = db.query(User).filter(User.email == data.email, User.id != user_id).first()
        if existing:
            raise HTTPException(status_code=400, detail="Cet email est déjà utilisé")
        user.email = data.email

    if data.full_name is not None:
        user.full_name = data.full_name

    if data.plan is not None:
        user.plan = data.plan

    if data.is_active is not None:
        user.is_active = data.is_active

    if data.is_admin is not None:
        user.is_admin = data.is_admin
        # Si on retire les droits admin, effacer le rôle
        if not data.is_admin:
            user.admin_role = None

    if data.admin_role is not None:
        if data.admin_role not in ADMIN_ROLES:
            raise HTTPException(
                status_code=400,
                detail=f"Rôle admin invalide. Valeurs possibles: {list(ADMIN_ROLES.keys())}",
            )
        user.admin_role = data.admin_role
        user.is_admin = True  # Activer admin si un rôle est défini

    if data.new_password is not None and len(data.new_password) >= 8:
        user.hashed_password = hash_password(data.new_password)

    db.commit()
    db.refresh(user)

    # Audit log
    try:
        log_action(
            db=db, user_id=current_user.id, action="update", resource_type="user",
            resource_id=user_id, details={"updated_fields": list(data.dict(exclude_unset=True).keys())},
            request=request,
        )
    except Exception:
        pass

    return user


@router.delete("/api/admin/users/{user_id}")
async def delete_user_admin(
    user_id: int,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Supprimer un utilisateur (Admin avec permission users).
    Empêche l'auto-suppression et supprime les subscriptions associées.
    """
    if not check_admin_permission(current_user, "users"):
        raise HTTPException(
            status_code=403,
            detail="Vous n'avez pas la permission de gérer les utilisateurs",
        )

    # Empêcher de supprimer son propre compte
    if user_id == current_user.id:
        raise HTTPException(
            status_code=400, detail="Vous ne pouvez pas supprimer votre propre compte"
        )

    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="Utilisateur non trouvé")

    # Audit log BEFORE deletion (user still exists)
    deleted_email = user.email
    try:
        log_action(
            db=db, user_id=current_user.id, action="delete", resource_type="user",
            resource_id=user_id, details={"deleted_email": deleted_email},
            request=request,
        )
    except Exception:
        pass

    # Supprimer les subscriptions associées
    db.query(Subscription).filter(Subscription.user_id == user_id).delete()

    # Supprimer l'utilisateur
    db.delete(user)
    db.commit()

    return {"message": "Utilisateur supprimé avec succès"}


@router.put("/api/admin/users/{user_id}/toggle-active")
async def toggle_user_active(
    user_id: int,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Activer/Désactiver un utilisateur (Admin seulement, sans permission spécifique).
    """
    if not current_user.is_admin:
        raise HTTPException(status_code=403, detail="Accès réservé aux administrateurs")

    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="Utilisateur non trouvé")

    user.is_active = not user.is_active
    db.commit()

    # Audit log
    try:
        log_action(
            db=db, user_id=current_user.id, action="toggle_active", resource_type="user",
            resource_id=user_id, details={"new_is_active": user.is_active},
            request=request,
        )
    except Exception:
        pass

    status = "activé" if user.is_active else "désactivé"
    return {"message": f"Utilisateur {status}", "is_active": user.is_active}


@router.get("/api/admin/audit-log", response_model=AuditLogListResponse)
async def get_audit_logs(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    action: Optional[str] = None,
    resource_type: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Recuperer les logs d'audit (Super Admin ou Admin avec permission users).
    Supporte la pagination via skip/limit et le filtrage par action/resource_type.
    """
    if not check_admin_permission(current_user, "users"):
        raise HTTPException(
            status_code=403,
            detail="Seuls les super admins et admins utilisateurs peuvent consulter les logs d'audit",
        )

    query = db.query(AuditLog).join(User, AuditLog.user_id == User.id)

    if action:
        query = query.filter(AuditLog.action == action)
    if resource_type:
        query = query.filter(AuditLog.resource_type == resource_type)

    total = query.count()

    logs = (
        query
        .order_by(AuditLog.created_at.desc())
        .offset(skip)
        .limit(limit)
        .all()
    )

    items = []
    for log in logs:
        items.append(AuditLogResponse(
            id=log.id,
            user_id=log.user_id,
            user_email=log.user.email if log.user else None,
            action=log.action,
            resource_type=log.resource_type,
            resource_id=log.resource_id,
            details=log.details,
            ip_address=log.ip_address,
            created_at=log.created_at,
        ))

    return AuditLogListResponse(items=items, total=total)
