"""
Router pour les notifications in-app.
Toutes les routes requierent l'authentification.
"""
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import get_current_user
from app.models import Notification, User
from app.pagination import PaginationParams, paginate
from app.rate_limit import limiter
from app.schemas.notifications import (
    NotificationListResponse,
    NotificationResponse,
    UnreadCountResponse,
)

router = APIRouter(tags=["notifications"])


@router.get("/api/notifications")
@limiter.limit("30/minute")
async def list_notifications(
    request: Request,
    pagination: PaginationParams = Depends(),
    status: str = Query("all", pattern="^(all|read|unread)$"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """List notifications for the current user, with pagination and read/unread filter."""
    stmt = select(Notification).where(Notification.user_id == current_user.id)

    if status == "read":
        stmt = stmt.where(Notification.is_read.is_(True))
    elif status == "unread":
        stmt = stmt.where(Notification.is_read.is_(False))

    stmt = stmt.order_by(Notification.created_at.desc())
    result = paginate(db, stmt, pagination)

    # Unread count (always based on all unread, regardless of filter)
    unread_count = db.execute(
        select(func.count(Notification.id)).where(
            Notification.user_id == current_user.id,
            Notification.is_read.is_(False),
        )
    ).scalar() or 0

    return {
        **result,
        "unread_count": unread_count,
    }


@router.get("/api/notifications/unread-count", response_model=UnreadCountResponse)
@limiter.limit("30/minute")
async def get_unread_count(
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Return the number of unread notifications for the current user."""
    count = db.execute(
        select(func.count(Notification.id)).where(
            Notification.user_id == current_user.id,
            Notification.is_read.is_(False),
        )
    ).scalar() or 0

    return UnreadCountResponse(unread_count=count)


@router.put("/api/notifications/{notification_id}/read")
@limiter.limit("20/minute")
async def mark_notification_as_read(
    request: Request,
    notification_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Mark a single notification as read."""
    notification = db.execute(
        select(Notification).where(
            Notification.id == notification_id,
            Notification.user_id == current_user.id,
        )
    ).scalar_one_or_none()

    if not notification:
        raise HTTPException(status_code=404, detail="Notification non trouvee")

    if not notification.is_read:
        notification.is_read = True
        notification.read_at = datetime.now(timezone.utc)
        db.commit()

    return {"message": "Notification marquee comme lue"}


@router.put("/api/notifications/read-all")
@limiter.limit("20/minute")
async def mark_all_notifications_as_read(
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Mark all unread notifications as read for the current user."""
    now = datetime.now(timezone.utc)
    result = db.execute(
        update(Notification)
        .where(
            Notification.user_id == current_user.id,
            Notification.is_read.is_(False),
        )
        .values(is_read=True, read_at=now)
    )
    db.commit()

    return {
        "message": "Toutes les notifications ont ete marquees comme lues",
        "updated_count": result.rowcount,
    }


@router.delete("/api/notifications/{notification_id}")
@limiter.limit("10/minute")
async def delete_notification(
    request: Request,
    notification_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Delete a notification belonging to the current user."""
    notification = db.execute(
        select(Notification).where(
            Notification.id == notification_id,
            Notification.user_id == current_user.id,
        )
    ).scalar_one_or_none()

    if not notification:
        raise HTTPException(status_code=404, detail="Notification non trouvee")

    db.delete(notification)
    db.commit()

    return {"message": "Notification supprimee"}
