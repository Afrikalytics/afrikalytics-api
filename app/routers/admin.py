"""
Router pour la gestion administrative des utilisateurs.
7 endpoints couvrant les roles, le CRUD utilisateurs et le toggle d'activation.
"""
import logging
import secrets
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import select, delete
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

from database import get_db
from models import User, Subscription, AuditLog
from auth import hash_password
from app.dependencies import get_current_user
from app.pagination import PaginationParams, paginate
from app.permissions import check_admin_permission, ADMIN_ROLES
from app.services.email import send_email
from app.services.email_templates import admin_user_created_email
from app.services.audit import log_action
from app.schemas.admin import AdminUserCreate, AdminUserUpdate, AdminUserResponse
from app.schemas.audit import AuditLogResponse, AuditLogListResponse
from app.rate_limit import limiter

router = APIRouter()


@router.get("/api/admin/roles")
@limiter.limit("20/minute")
def get_admin_roles(
    request: Request,
    current_user: User = Depends(get_current_user),
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


@router.get("/api/admin/users")
@limiter.limit("20/minute")
def get_all_users(
    request: Request,
    pagination: PaginationParams = Depends(),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Récupérer tous les utilisateurs (Admin avec permission users).
    Supporte la pagination via page/per_page.
    """
    if not check_admin_permission(current_user, "users"):
        raise HTTPException(
            status_code=403,
            detail="Vous n'avez pas la permission de gérer les utilisateurs",
        )

    stmt = select(User).order_by(User.created_at.desc())
    return paginate(db, stmt, pagination)


@router.get("/api/admin/users/{user_id}", response_model=AdminUserResponse)
@limiter.limit("20/minute")
def get_user_by_id(
    request: Request,
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

    user = db.execute(
        select(User).where(User.id == user_id)
    ).scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="Utilisateur non trouvé")

    return user


@router.post("/api/admin/users", response_model=AdminUserResponse, status_code=201)
@limiter.limit("10/minute")
def create_user_admin(
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
    existing_user = db.execute(
        select(User).where(User.email == data.email)
    ).scalar_one_or_none()
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
        html=admin_user_created_email(new_user.full_name, new_user.email, password, new_user.plan),
    )

    # Audit log
    try:
        log_action(
            db=db, user_id=current_user.id, action="create", resource_type="user",
            resource_id=new_user.id, details={"email": new_user.email, "plan": new_user.plan},
            request=request,
        )
    except Exception as e:
        logger.warning(f"Audit log failed: {e}")

    return new_user


@router.put("/api/admin/users/{user_id}", response_model=AdminUserResponse)
@limiter.limit("10/minute")
def update_user_admin(
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

    user = db.execute(
        select(User).where(User.id == user_id)
    ).scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="Utilisateur non trouvé")

    # Mettre à jour les champs fournis
    if data.email is not None:
        # Vérifier si l'email est déjà utilisé par un autre utilisateur
        existing = db.execute(
            select(User).where(User.email == data.email, User.id != user_id)
        ).scalar_one_or_none()
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
    except Exception as e:
        logger.warning(f"Audit log failed: {e}")

    return user


@router.delete("/api/admin/users/{user_id}")
@limiter.limit("5/minute")
def delete_user_admin(
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

    user = db.execute(
        select(User).where(User.id == user_id)
    ).scalar_one_or_none()
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
    except Exception as e:
        logger.warning(f"Audit log failed: {e}")

    # Supprimer les subscriptions associées
    db.execute(
        delete(Subscription).where(Subscription.user_id == user_id)
    )

    # Supprimer l'utilisateur
    db.delete(user)
    db.commit()

    return {"message": "Utilisateur supprimé avec succès"}


@router.put("/api/admin/users/{user_id}/toggle-active")
@limiter.limit("10/minute")
def toggle_user_active(
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

    user = db.execute(
        select(User).where(User.id == user_id)
    ).scalar_one_or_none()
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
    except Exception as e:
        logger.warning(f"Audit log failed: {e}")

    status = "activé" if user.is_active else "désactivé"
    return {"message": f"Utilisateur {status}", "is_active": user.is_active}


@router.get("/api/admin/audit-log")
@limiter.limit("20/minute")
def get_audit_logs(
    request: Request,
    pagination: PaginationParams = Depends(),
    action: Optional[str] = None,
    resource_type: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Recuperer les logs d'audit (Super Admin ou Admin avec permission users).
    Supporte la pagination via page/per_page et le filtrage par action/resource_type.
    """
    if not check_admin_permission(current_user, "users"):
        raise HTTPException(
            status_code=403,
            detail="Seuls les super admins et admins utilisateurs peuvent consulter les logs d'audit",
        )

    stmt = select(AuditLog).join(User, AuditLog.user_id == User.id)

    if action:
        stmt = stmt.where(AuditLog.action == action)
    if resource_type:
        stmt = stmt.where(AuditLog.resource_type == resource_type)

    stmt = stmt.order_by(AuditLog.created_at.desc())
    result = paginate(db, stmt, pagination)

    # Transform items to include user_email
    items = []
    for log in result["items"]:
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

    result["items"] = items
    return result


# ---------------------------------------------------------------------------
# Cleanup endpoint — purge expired ephemeral rows
# ---------------------------------------------------------------------------

@router.post("/api/admin/cleanup")
@limiter.limit("5/minute")
def run_cleanup(
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Purger les lignes expirées des tables techniques.

    Supprime les ``verification_codes``, ``token_blacklist`` et
    ``sso_exchange_codes`` expirés/consommés pour contrôler la croissance
    indéfinie de ces tables.

    Peut aussi être déclenché par un CRON Railway en fournissant le header
    ``X-Cron-Secret`` plutôt qu'un JWT (voir ``/api/admin/cleanup/cron``).

    Accès : super_admin uniquement.
    """
    if not check_admin_permission(current_user, "users"):
        raise HTTPException(
            status_code=403,
            detail="Seuls les super admins peuvent déclencher le nettoyage.",
        )

    from app.services.cleanup import run_cleanup as _run_cleanup

    try:
        result = _run_cleanup(db)
    except Exception as exc:
        logger.error("cleanup_failed error=%s", exc, exc_info=True)
        raise HTTPException(status_code=500, detail="Erreur lors du nettoyage.") from exc

    log_action(
        db=db,
        user_id=current_user.id,
        action="cleanup",
        resource_type="system",
        details=dict(result),
        request=request,
    )

    return {
        "message": "Nettoyage terminé.",
        "result": result,
    }


@router.post("/api/admin/cleanup/cron", include_in_schema=False)
@limiter.limit("10/minute")
def run_cleanup_cron(
    request: Request,
    db: Session = Depends(get_db),
):
    """Endpoint CRON pour le nettoyage automatique des tables techniques.

    Protégé par le header ``X-Cron-Secret`` (valeur = ``CRON_SECRET`` env var).
    Non exposé dans la documentation Swagger (``include_in_schema=False``).
    """
    from app.config import get_settings

    settings = get_settings()

    cron_secret = request.headers.get("x-cron-secret", "")
    if not cron_secret or not settings.cron_secret:
        raise HTTPException(status_code=401, detail="Secret CRON manquant.")

    import hmac
    if not hmac.compare_digest(cron_secret, settings.cron_secret):
        raise HTTPException(status_code=401, detail="Secret CRON invalide.")

    from app.services.cleanup import run_cleanup as _run_cleanup

    try:
        result = _run_cleanup(db)
    except Exception as exc:
        logger.error("cron_cleanup_failed error=%s", exc, exc_info=True)
        raise HTTPException(status_code=500, detail="Erreur lors du nettoyage CRON.") from exc

    logger.info("cron_cleanup_complete result=%s", result)

    return {"message": "Nettoyage CRON terminé.", "result": result}
