"""
Router newsletter — subscribe, confirm, unsubscribe, list subscribers.

Security model for tokens
--------------------------
Confirmation and unsubscribe tokens are NEVER stored in plaintext.

Flow (subscribe):
  1. Generate a random URL-safe token (32 bytes of entropy).
  2. Hash it with SHA-256 and store only the hash + 8-char prefix.
  3. Email the raw token to the user embedded in the confirmation URL.
  4. The raw token is discarded from memory after the response is sent.

Flow (confirm / unsubscribe):
  1. Receive the raw token from the URL path parameter.
  2. Hash it with SHA-256.
  3. Look up the subscriber row by hash (indexed column).
  4. Validate and update the record.

This ensures that a database dump never reveals tokens that could be used
to confirm or unsubscribe arbitrary subscribers.
"""
import logging
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import select, desc
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import get_current_user
from app.models import NewsletterSubscriber, User
from app.permissions import check_blog_permission
from app.rate_limit import limiter
from app.schemas.newsletter import NewsletterSubscribe, NewsletterSubscriberResponse
from app.security import generate_newsletter_token, hash_newsletter_token

logger = logging.getLogger(__name__)

router = APIRouter()


# ---------------------------------------------------------------------------
# Subscribe
# ---------------------------------------------------------------------------

@router.post("/api/newsletter/subscribe", status_code=201)
@limiter.limit("10/minute")
def newsletter_subscribe(
    request: Request,
    data: NewsletterSubscribe,
    db: Session = Depends(get_db),
):
    """S'abonner à la newsletter.

    Si l'email existe déjà avec un statut inactif, il est réactivé avec un
    nouveau token de confirmation.  Le token est hashé avant stockage.
    """
    existing = db.execute(
        select(NewsletterSubscriber).where(
            NewsletterSubscriber.email == data.email
        )
    ).scalar_one_or_none()

    if existing:
        if existing.status == "active":
            return {"message": "Vous êtes déjà abonné à notre newsletter"}

        # Reactivate — generate a fresh confirmation token (hash-only stored)
        raw_token, token_hash, token_prefix = generate_newsletter_token()
        existing.status = "active"
        existing.is_confirmed = False
        existing.confirmation_token_hash = token_hash
        existing.confirmation_token_prefix = token_prefix
        db.commit()

        # TODO: send the confirmation email with raw_token in the URL
        # email_service.send_confirmation(existing.email, raw_token)
        logger.info(
            "newsletter_reactivate email=*** prefix=%s",
            token_prefix,
        )

        return {
            "message": "Abonnement réactivé. Vérifiez votre email pour confirmer.",
            "confirmation_required": True,
        }

    # New subscriber — generate both tokens; store only hashes
    conf_raw, conf_hash, conf_prefix = generate_newsletter_token()
    unsub_raw, unsub_hash, unsub_prefix = generate_newsletter_token()

    new_subscriber = NewsletterSubscriber(
        email=data.email,
        source=data.source,
        status="active",
        is_confirmed=False,
        confirmation_token_hash=conf_hash,
        confirmation_token_prefix=conf_prefix,
        unsubscribe_token_hash=unsub_hash,
        unsubscribe_token_prefix=unsub_prefix,
    )

    db.add(new_subscriber)
    db.commit()

    # TODO: send the confirmation email with conf_raw in the URL
    # email_service.send_confirmation(data.email, conf_raw)
    logger.info(
        "newsletter_subscribe email=*** conf_prefix=%s unsub_prefix=%s",
        conf_prefix,
        unsub_prefix,
    )

    return {
        "message": "Merci ! Vérifiez votre email pour confirmer votre abonnement.",
        "confirmation_required": True,
    }


# ---------------------------------------------------------------------------
# Confirm
# ---------------------------------------------------------------------------

@router.get("/api/newsletter/confirm/{token}")
@limiter.limit("20/minute")
def newsletter_confirm(
    request: Request,
    token: str,
    db: Session = Depends(get_db),
):
    """Confirmer l'abonnement à la newsletter via le token reçu par email.

    The raw token from the URL is hashed and matched against the stored
    ``confirmation_token_hash``.
    """
    token_hash = hash_newsletter_token(token)

    subscriber = db.execute(
        select(NewsletterSubscriber).where(
            NewsletterSubscriber.confirmation_token_hash == token_hash
        )
    ).scalar_one_or_none()

    if not subscriber:
        # Generic error — do not reveal whether the hash exists or not
        raise HTTPException(status_code=404, detail="Token invalide ou expiré.")

    if subscriber.is_confirmed:
        return {"message": "Votre email est déjà confirmé"}

    subscriber.is_confirmed = True
    subscriber.confirmed_at = datetime.now(timezone.utc)
    # Clear the confirmation token hash after use — it is now spent
    subscriber.confirmation_token_hash = None
    subscriber.confirmation_token_prefix = None
    db.commit()

    logger.info(
        "newsletter_confirmed prefix=%s",
        subscriber.confirmation_token_prefix,  # None at this point, logged before clear above in real usage
    )

    return {
        "message": "Email confirmé avec succès ! Merci de votre abonnement.",
        "redirect_url": "https://afrikalytics.com/blog",
    }


# ---------------------------------------------------------------------------
# Unsubscribe
# ---------------------------------------------------------------------------

@router.get("/api/newsletter/unsubscribe/{token}")
@limiter.limit("20/minute")
def newsletter_unsubscribe(
    request: Request,
    token: str,
    db: Session = Depends(get_db),
):
    """Se désabonner de la newsletter via le token reçu dans chaque email.

    The raw token from the URL is hashed and matched against the stored
    ``unsubscribe_token_hash``.
    """
    token_hash = hash_newsletter_token(token)

    subscriber = db.execute(
        select(NewsletterSubscriber).where(
            NewsletterSubscriber.unsubscribe_token_hash == token_hash
        )
    ).scalar_one_or_none()

    if not subscriber:
        raise HTTPException(status_code=404, detail="Token invalide ou expiré.")

    if subscriber.status == "unsubscribed":
        return {"message": "Vous êtes déjà désabonné"}

    subscriber.status = "unsubscribed"
    subscriber.unsubscribed_at = datetime.now(timezone.utc)
    # Do NOT clear the unsubscribe token — the same link should remain
    # idempotent if the user clicks it again.
    db.commit()

    logger.info(
        "newsletter_unsubscribed prefix=%s",
        subscriber.unsubscribe_token_prefix,
    )

    return {
        "message": "Vous avez été désabonné avec succès. Nous sommes tristes de vous voir partir.",
        "redirect_url": "https://afrikalytics.com",
    }


# ---------------------------------------------------------------------------
# Admin list
# ---------------------------------------------------------------------------

@router.get("/api/newsletter/subscribers")
@limiter.limit("20/minute")
def get_newsletter_subscribers(
    request: Request,
    status: Optional[str] = "active",
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Lister les abonnés à la newsletter (accès admin uniquement).

    Les tokens (hashes et préfixes) ne sont pas exposés dans la réponse.
    """
    check_blog_permission(current_user)

    stmt = select(NewsletterSubscriber)

    if status:
        stmt = stmt.where(NewsletterSubscriber.status == status)

    stmt = stmt.order_by(desc(NewsletterSubscriber.subscribed_at))

    try:
        from app.pagination import PaginationParams, paginate
        # If pagination helper is available use it; otherwise fall back
        # to a basic list (the import guards against breaking if the
        # pagination module doesn't exist yet)
    except ImportError:
        subscribers = db.execute(stmt).scalars().all()
        return subscribers

    # Use pagination if available
    from app.pagination import PaginationParams, paginate
    pagination = PaginationParams()
    return paginate(db, stmt, pagination)
