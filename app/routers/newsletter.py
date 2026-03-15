import secrets
from datetime import datetime, timezone
from typing import Optional, List

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import select, desc
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import NewsletterSubscriber, User
from app.dependencies import get_current_user
from app.permissions import check_blog_permission
from app.schemas.newsletter import NewsletterSubscribe, NewsletterSubscriberResponse
from app.rate_limit import limiter

router = APIRouter()


@router.post("/api/newsletter/subscribe", status_code=201)
@limiter.limit("10/minute")
async def newsletter_subscribe(
    request: Request,
    data: NewsletterSubscribe,
    db: Session = Depends(get_db),
):
    existing = db.execute(
        select(NewsletterSubscriber).where(
            NewsletterSubscriber.email == data.email
        )
    ).scalar_one_or_none()

    if existing:
        if existing.status == "active":
            return {"message": "Vous êtes déjà abonné à notre newsletter"}
        else:
            existing.status = "active"
            existing.is_confirmed = False
            existing.confirmation_token = secrets.token_urlsafe(32)
            db.commit()
            return {
                "message": "Abonnement réactivé. Vérifiez votre email pour confirmer.",
                "confirmation_required": True,
            }

    new_subscriber = NewsletterSubscriber(
        email=data.email,
        source=data.source,
        status="active",
        is_confirmed=False,
        confirmation_token=secrets.token_urlsafe(32),
        unsubscribe_token=secrets.token_urlsafe(32),
    )

    db.add(new_subscriber)
    db.commit()

    return {
        "message": "Merci ! Vérifiez votre email pour confirmer votre abonnement.",
        "confirmation_required": True,
    }


@router.get("/api/newsletter/confirm/{token}")
@limiter.limit("20/minute")
async def newsletter_confirm(
    request: Request,
    token: str,
    db: Session = Depends(get_db),
):
    subscriber = db.execute(
        select(NewsletterSubscriber).where(
            NewsletterSubscriber.confirmation_token == token
        )
    ).scalar_one_or_none()

    if not subscriber:
        raise HTTPException(status_code=404, detail="Token invalide")

    if subscriber.is_confirmed:
        return {"message": "Votre email est déjà confirmé"}

    subscriber.is_confirmed = True
    subscriber.confirmed_at = datetime.now(timezone.utc)
    db.commit()

    return {
        "message": "Email confirmé avec succès ! Merci de votre abonnement.",
        "redirect_url": "https://afrikalytics.com/blog",
    }


@router.get("/api/newsletter/unsubscribe/{token}")
@limiter.limit("20/minute")
async def newsletter_unsubscribe(
    request: Request,
    token: str,
    db: Session = Depends(get_db),
):
    subscriber = db.execute(
        select(NewsletterSubscriber).where(
            NewsletterSubscriber.unsubscribe_token == token
        )
    ).scalar_one_or_none()

    if not subscriber:
        raise HTTPException(status_code=404, detail="Token invalide")

    if subscriber.status == "unsubscribed":
        return {"message": "Vous êtes déjà désabonné"}

    subscriber.status = "unsubscribed"
    subscriber.unsubscribed_at = datetime.now(timezone.utc)
    db.commit()

    return {
        "message": "Vous avez été désabonné avec succès. Nous sommes tristes de vous voir partir.",
        "redirect_url": "https://afrikalytics.com",
    }


@router.get("/api/newsletter/subscribers", response_model=List[NewsletterSubscriberResponse])
@limiter.limit("20/minute")
async def get_newsletter_subscribers(
    request: Request,
    status: Optional[str] = "active",
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    check_blog_permission(current_user)

    stmt = select(NewsletterSubscriber)

    if status:
        stmt = stmt.where(NewsletterSubscriber.status == status)

    stmt = stmt.order_by(desc(NewsletterSubscriber.subscribed_at))
    subscribers = db.execute(stmt).scalars().all()
    return subscribers
