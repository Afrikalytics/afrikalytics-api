"""
Service de creation de notifications in-app.
Fonction helper reutilisable par les autres services (paiements, analytics, etc.).
"""
import logging
from typing import Any, Optional

from sqlalchemy.orm import Session

from app.models import Notification

logger = logging.getLogger(__name__)


def create_notification(
    db: Session,
    user_id: int,
    type: str,
    title: str,
    message: str,
    metadata: Optional[dict[str, Any]] = None,
) -> Notification:
    """
    Create an in-app notification for a user.

    Args:
        db: SQLAlchemy session
        user_id: Target user ID
        type: Notification type — one of:
              "study_created", "insight_generated", "payment_confirmed",
              "anomaly_detected", "system"
        title: Short notification title (max 200 chars)
        message: Full notification message
        metadata: Optional extra data (study_id, payment_id, etc.)

    Returns:
        The created Notification instance.
    """
    notification = Notification(
        user_id=user_id,
        notification_type=type,
        title=title,
        message=message,
        metadata_json=metadata,
    )
    db.add(notification)
    db.commit()
    db.refresh(notification)

    logger.info(
        "Notification created: id=%d, user_id=%d, type=%s",
        notification.id,
        user_id,
        type,
    )

    return notification


def create_notification_bulk(
    db: Session,
    user_ids: list[int],
    type: str,
    title: str,
    message: str,
    metadata: Optional[dict[str, Any]] = None,
) -> list[Notification]:
    """
    Create the same notification for multiple users (e.g. system announcements).

    Args:
        db: SQLAlchemy session
        user_ids: List of target user IDs
        type: Notification type
        title: Short notification title
        message: Full notification message
        metadata: Optional extra data

    Returns:
        List of created Notification instances.
    """
    notifications = [
        Notification(
            user_id=uid,
            notification_type=type,
            title=title,
            message=message,
            metadata_json=metadata,
        )
        for uid in user_ids
    ]
    db.add_all(notifications)
    db.commit()
    for n in notifications:
        db.refresh(n)

    logger.info(
        "Bulk notifications created: count=%d, type=%s",
        len(notifications),
        type,
    )

    return notifications
