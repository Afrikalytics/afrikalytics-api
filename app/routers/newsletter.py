import secrets
from datetime import datetime
from typing import Optional, List

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import desc
from sqlalchemy.orm import Session

from database import get_db
from models import NewsletterSubscriber, User
from app.dependencies import get_current_user
from app.permissions import check_blog_permission
from app.schemas.newsletter import NewsletterSubscribe, NewsletterSubscriberResponse

router = APIRouter()


@router.post("/api/newsletter/subscribe", status_code=201)
async def newsletter_subscribe(
    data: NewsletterSubscribe,
    db: Session = Depends(get_db),
):
    existing = db.query(NewsletterSubscriber).filter(
        NewsletterSubscriber.email == data.email
    ).first()

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
async def newsletter_confirm(
    token: str,
    db: Session = Depends(get_db),
):
    subscriber = db.query(NewsletterSubscriber).filter(
        NewsletterSubscriber.confirmation_token == token
    ).first()

    if not subscriber:
        raise HTTPException(status_code=404, detail="Token invalide")

    if subscriber.is_confirmed:
        return {"message": "Votre email est déjà confirmé"}

    subscriber.is_confirmed = True
    subscriber.confirmed_at = datetime.utcnow()
    db.commit()

    return {
        "message": "Email confirmé avec succès ! Merci de votre abonnement.",
        "redirect_url": "https://afrikalytics.com/blog",
    }


@router.get("/api/newsletter/unsubscribe/{token}")
async def newsletter_unsubscribe(
    token: str,
    db: Session = Depends(get_db),
):
    subscriber = db.query(NewsletterSubscriber).filter(
        NewsletterSubscriber.unsubscribe_token == token
    ).first()

    if not subscriber:
        raise HTTPException(status_code=404, detail="Token invalide")

    if subscriber.status == "unsubscribed":
        return {"message": "Vous êtes déjà désabonné"}

    subscriber.status = "unsubscribed"
    subscriber.unsubscribed_at = datetime.utcnow()
    db.commit()

    return {
        "message": "Vous avez été désabonné avec succès. Nous sommes tristes de vous voir partir.",
        "redirect_url": "https://afrikalytics.com",
    }


@router.get("/api/newsletter/subscribers", response_model=List[NewsletterSubscriberResponse])
async def get_newsletter_subscribers(
    status: Optional[str] = "active",
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    check_blog_permission(current_user)

    query = db.query(NewsletterSubscriber)

    if status:
        query = query.filter(NewsletterSubscriber.status == status)

    subscribers = query.order_by(desc(NewsletterSubscriber.subscribed_at)).all()
    return subscribers
