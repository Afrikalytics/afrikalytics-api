"""
Service d'audit logging pour tracer les actions administratives.
Chaque mutation (create, update, delete, publish, toggle) est enregistree.
"""
import json
import logging

from sqlalchemy.orm import Session
from fastapi import Request

from models import AuditLog

logger = logging.getLogger(__name__)


def log_action(
    db: Session,
    user_id: int,
    action: str,
    resource_type: str,
    resource_id: int = None,
    details: dict = None,
    request: Request = None,
):
    """
    Enregistrer une action dans la table audit_logs.

    Args:
        db: Session SQLAlchemy active
        user_id: ID de l'utilisateur effectuant l'action
        action: Type d'action (create, update, delete, toggle_active, publish)
        resource_type: Type de ressource (user, study, insight, report, blog_post)
        resource_id: ID de la ressource concernee (optionnel)
        details: Dictionnaire de details supplementaires (optionnel)
        request: Objet Request FastAPI pour extraire l'IP (optionnel)

    Returns:
        AuditLog cree ou None en cas d'erreur
    """
    try:
        ip_address = None
        if request:
            ip_address = request.client.host if request.client else None

        log = AuditLog(
            user_id=user_id,
            action=action,
            resource_type=resource_type,
            resource_id=resource_id,
            details=json.dumps(details, ensure_ascii=False) if details else None,
            ip_address=ip_address,
        )
        db.add(log)
        db.commit()
        return log
    except Exception as e:
        logger.error(f"Failed to write audit log: {e}")
        # Rollback to avoid corrupting the session for subsequent queries
        try:
            db.rollback()
        except Exception:
            pass
        return None
