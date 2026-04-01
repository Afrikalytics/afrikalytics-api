import hashlib
import hmac
import httpx
import json
import logging
import re
import secrets
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.database import get_db
from app.models import User, Subscription, TokenBlacklist, Payment
from app.auth import hash_password
from app.dependencies import get_current_user
from app.services.email import send_email
from app.services.email_templates import payment_upgrade_email, payment_new_user_email
from app.services.payment_service import (
    PLAN_FEATURES,
    VALID_PLANS,
    create_payment_record,
    create_paydunya_invoice_request,
    get_plan_duration,
    get_plan_price,
    mark_webhook_processed,
    verify_paydunya_invoice,
)
from app.schemas.payments import (
    PaymentCreate,
    PaymentHistoryItem,
    PaymentHistoryResponse,
    CurrentPlanResponse,
)
from app.rate_limit import limiter

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/api/payments/history", response_model=PaymentHistoryResponse)
@limiter.limit("30/minute")
def get_payment_history(
    request: Request,
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Recuperer l'historique des paiements de l'utilisateur."""
    # Count total payments for this user
    total = db.execute(
        select(func.count(Payment.id)).where(Payment.user_id == current_user.id)
    ).scalar_one()

    # Fetch paginated payments ordered by most recent first
    payments = db.execute(
        select(Payment)
        .where(Payment.user_id == current_user.id)
        .order_by(Payment.created_at.desc())
        .offset(skip)
        .limit(limit)
    ).scalars().all()

    items = [
        PaymentHistoryItem(
            id=p.id,
            amount=p.amount,
            currency=p.currency or "XOF",
            status=p.status,
            plan=p.plan,
            payment_method=p.payment_method or "mobile_money",
            created_at=p.created_at,
            reference=p.provider_ref,
        )
        for p in payments
    ]

    current_page = (skip // limit) + 1 if limit > 0 else 1

    return PaymentHistoryResponse(
        payments=items,
        total=total,
        current_page=current_page,
    )


@router.get("/api/payments/current-plan", response_model=CurrentPlanResponse)
@limiter.limit("30/minute")
def get_current_plan(
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Recuperer le plan actuel et les details d'abonnement."""
    # Fetch the latest active subscription
    active_subscription = db.execute(
        select(Subscription)
        .where(
            Subscription.user_id == current_user.id,
            Subscription.status == "active",
        )
        .order_by(Subscription.created_at.desc())
    ).scalar_one_or_none()

    expires_at = active_subscription.end_date if active_subscription else None
    features = PLAN_FEATURES.get(current_user.plan, PLAN_FEATURES["basic"])

    return CurrentPlanResponse(
        plan=current_user.plan,
        is_active=current_user.is_active,
        expires_at=expires_at,
        features=features,
    )


@router.post("/api/payments/change-plan")
@limiter.limit("10/minute")
async def change_plan(
    request: Request,
    data: PaymentCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Initier un changement de plan (upgrade/downgrade) via PayDunya."""
    target_plan = data.plan

    if target_plan not in VALID_PLANS:
        raise HTTPException(status_code=400, detail=f"Plan invalide: {target_plan}")

    if target_plan == current_user.plan:
        raise HTTPException(status_code=400, detail="Vous etes deja sur ce plan.")

    # Downgrade to basic — immediate, no payment needed
    if target_plan == "basic":
        try:
            current_user.plan = "basic"

            # Cancel active subscription
            active_sub = db.execute(
                select(Subscription).where(
                    Subscription.user_id == current_user.id,
                    Subscription.status == "active",
                )
            ).scalar_one_or_none()
            if active_sub:
                active_sub.status = "cancelled"

            db.commit()
        except Exception:
            db.rollback()
            raise

        return {
            "success": True,
            "action": "downgraded",
            "plan": "basic",
            "message": "Votre plan a ete mis a jour vers Basic.",
        }

    # Upgrade — create PayDunya invoice
    try:
        plan_label = target_plan.capitalize()
        result = await create_paydunya_invoice_request(
            plan=target_plan,
            email=current_user.email,
            name=current_user.full_name,
            item_name=f"Changement vers {plan_label} - Afrikalytics",
            item_description=f"Passage au plan {plan_label}",
            invoice_description=f"Afrikalytics - Passage au plan {plan_label}",
        )

        if result.get("response_code") == "00":
            return {
                "success": True,
                "action": "payment_required",
                "payment_url": result.get("response_text"),
                "token": result.get("token"),
                "target_plan": target_plan,
            }
        else:
            logger.error(f"PayDunya plan change invoice failed: response_code={result.get('response_code')}")
            raise HTTPException(
                status_code=400,
                detail=f"Erreur creation facture: {result.get('response_text', 'Erreur inconnue')}",
            )
    except httpx.HTTPError:
        raise HTTPException(status_code=500, detail="Erreur de connexion au service de paiement")


@router.get("/api/payments/plans")
@limiter.limit("60/minute")
def get_available_plans(request: Request):
    """Recuperer la liste des plans disponibles avec leurs features."""
    return {
        "plans": PLAN_FEATURES,
    }


@router.post("/api/paydunya/create-invoice")
@limiter.limit("10/minute")
async def create_paydunya_invoice(
    request: Request,
    data: PaymentCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    try:
        result = await create_paydunya_invoice_request(
            plan=data.plan,
            email=data.email,
            name=data.name,
        )

        if result.get("response_code") == "00":
            return {
                "success": True,
                "payment_url": result.get("response_text"),
                "token": result.get("token")
            }
        else:
            logger.error(f"PayDunya invoice creation failed: response_code={result.get('response_code')}")
            raise HTTPException(
                status_code=400,
                detail=f"Erreur création facture: {result.get('response_text', 'Erreur inconnue')}"
            )
    except httpx.HTTPError:
        raise HTTPException(status_code=500, detail="Erreur de connexion au service de paiement")


@router.post("/api/paydunya/webhook")
@limiter.limit("20/minute")
async def paydunya_webhook(
    request: Request,
    db: Session = Depends(get_db),
):
    settings = get_settings()

    # Read the raw body first — required for HMAC verification and later parsing.
    # body must be bytes for hmac.new(); do not decode here.
    body = await request.body()

    # Verify HMAC-SHA512 signature from PAYDUNYA-SIGNATURE header.
    # This check is intentionally outside the broad except block below so that
    # a signature mismatch always returns 403 and is never silently swallowed.
    # SECURITY: HMAC verification is mandatory — fail closed if key is not configured.
    if not settings.paydunya_master_key:
        logger.error("paydunya_master_key not configured — refusing all webhook requests")
        raise HTTPException(status_code=503, detail="Payment webhook not configured")

    signature = request.headers.get("PAYDUNYA-SIGNATURE", "")
    computed_hash = hmac.new(
        settings.paydunya_master_key.encode('utf-8'),
        body,                   # bytes — required by hmac.new()
        hashlib.sha512,
    ).hexdigest()
    if not hmac.compare_digest(signature, computed_hash):
        logger.warning("PayDunya webhook HMAC signature mismatch - rejecting")
        raise HTTPException(status_code=403, detail="Invalid webhook signature")

    try:
        content_type = request.headers.get("content-type", "")

        if "application/json" in content_type:
            data = await request.json()
        else:
            form_data = await request.form()
            raw_data = dict(form_data)

            logger.info("PayDunya Webhook received (form data)")

            data = {}
            for key, value in raw_data.items():
                if key.startswith("data["):
                    matches = re.findall(r'\[([^\]]+)\]', key)
                    if len(matches) == 1:
                        data[matches[0]] = value
                    elif len(matches) == 2:
                        if matches[0] not in data:
                            data[matches[0]] = {}
                        data[matches[0]][matches[1]] = value
                    elif len(matches) == 3:
                        if matches[0] not in data:
                            data[matches[0]] = {}
                        if matches[1] not in data[matches[0]]:
                            data[matches[0]][matches[1]] = {}
                        data[matches[0]][matches[1]][matches[2]] = value

        logger.info("PayDunya Webhook parsed successfully")

        # Verification signature — NEVER skip, always reject unsigned webhooks
        received_hash = data.get("hash")
        invoice_token = data.get("invoice", {}).get("token") if isinstance(data.get("invoice"), dict) else data.get("token")

        if not received_hash or not invoice_token:
            logger.warning("PayDunya webhook missing hash or token - rejecting")
            raise HTTPException(status_code=403, detail="Missing webhook signature")

        expected_hash = hashlib.sha512(
            (settings.paydunya_master_key + invoice_token).encode('utf-8')
        ).hexdigest()
        if not hmac.compare_digest(received_hash, expected_hash):
            logger.warning("PayDunya webhook hash mismatch - rejecting")
            raise HTTPException(status_code=403, detail="Invalid webhook signature")

        # Idempotency: reject already-processed webhooks (DB-backed, survives restarts)
        existing_blacklist = db.execute(
            select(TokenBlacklist).where(TokenBlacklist.jti == f"webhook_{invoice_token}")
        ).scalar_one_or_none()
        if existing_blacklist:
            logger.info(f"PayDunya webhook already processed for token {invoice_token[:8]}... - ignoring")
            return {"status": "already_processed", "reason": "This webhook has already been processed"}

        # Verifier statut paiement
        status = data.get("status") or data.get("response_code")
        token = data.get("token") or data.get("invoice_token")

        if token and not status:
            try:
                verify_data = await verify_paydunya_invoice(token)
                logger.info("PayDunya verification completed")
                status = verify_data.get("status")
                if not data.get("custom_data"):
                    data["custom_data"] = verify_data.get("custom_data", {})
            except httpx.HTTPError:
                logger.exception("PayDunya verification error")

        if status != "completed":
            logger.info(f"Payment not completed: {status}")
            return {"status": "ignored", "reason": f"Status: {status}"}

        # Recuperer custom_data
        custom_data = data.get("custom_data", {})
        if isinstance(custom_data, str):
            try:
                custom_data = json.loads(custom_data)
            except (json.JSONDecodeError, ValueError):
                custom_data = {}

        email = custom_data.get("email")
        name = custom_data.get("name")
        plan = custom_data.get("plan", "professionnel")

        # Validate plan to prevent injection of unknown plans
        if plan not in VALID_PLANS:
            logger.warning(f"PayDunya webhook received unknown plan: {plan}")
            raise HTTPException(status_code=400, detail=f"Plan invalide: {plan}")

        logger.info(f"Payment processing for plan={plan}")

        if not email:
            logger.warning("Missing email in custom_data")
            return {"status": "error", "reason": "Email manquant"}

        amount = get_plan_price(plan)
        duration = get_plan_duration(plan)
        now = datetime.now(timezone.utc)

        existing_user = db.execute(
            select(User).where(User.email == email)
        ).scalar_one_or_none()

        if existing_user:
            try:
                existing_user.plan = plan
                existing_user.is_active = True

                existing_subscription = db.execute(
                    select(Subscription).where(
                        Subscription.user_id == existing_user.id,
                        Subscription.status == "active"
                    )
                ).scalar_one_or_none()

                if existing_subscription:
                    existing_subscription.plan = plan
                    existing_subscription.start_date = now
                    existing_subscription.end_date = now + duration
                    existing_subscription.status = "active"
                else:
                    new_subscription = Subscription(
                        user_id=existing_user.id,
                        plan=plan,
                        status="active",
                        start_date=now,
                        end_date=now + duration,
                    )
                    db.add(new_subscription)

                # Flush to get subscription IDs without committing
                db.flush()

                # Resolve subscription for payment record
                active_sub = existing_subscription or db.execute(
                    select(Subscription).where(
                        Subscription.user_id == existing_user.id,
                        Subscription.status == "active"
                    )
                ).scalar_one_or_none()

                create_payment_record(
                    db,
                    user_id=existing_user.id,
                    plan=plan,
                    amount=amount,
                    token=token,
                    status="completed",
                    subscription_id=active_sub.id if active_sub else None,
                    invoice_data=data,
                )

                mark_webhook_processed(db, invoice_token, existing_user.id)

                db.commit()
            except Exception:
                db.rollback()
                raise

            send_email(
                to=email,
                subject="Bienvenue dans Afrikalytics Premium !",
                html=payment_upgrade_email(existing_user.full_name, plan),
            )

            return {"status": "success", "action": "user_upgraded", "user_id": existing_user.id}

        else:
            temp_password = secrets.token_urlsafe(12)
            hashed_password = hash_password(temp_password)

            try:
                new_user = User(
                    email=email,
                    full_name=name,
                    hashed_password=hashed_password,
                    plan=plan,
                    is_active=True
                )

                db.add(new_user)
                db.flush()

                new_subscription = Subscription(
                    user_id=new_user.id,
                    plan=plan,
                    status="active",
                    start_date=now,
                    end_date=now + duration,
                )
                db.add(new_subscription)
                db.flush()

                create_payment_record(
                    db,
                    user_id=new_user.id,
                    plan=plan,
                    amount=amount,
                    token=token,
                    status="completed",
                    subscription_id=new_subscription.id,
                    invoice_data=data,
                )

                mark_webhook_processed(db, invoice_token, new_user.id)

                db.commit()
            except Exception:
                db.rollback()
                raise

            send_email(
                to=email,
                subject="Bienvenue dans Afrikalytics Premium !",
                html=payment_new_user_email(name, email, temp_password, plan),
            )

            return {"status": "success", "action": "user_created", "user_id": new_user.id}

    except HTTPException:
        # Re-raise security rejections (403, 400) — never swallow them.
        raise
    except Exception:
        logger.exception("Erreur webhook PayDunya")
        return {"status": "error", "reason": "Erreur interne de traitement"}


@router.get("/api/paydunya/verify/{token}")
@limiter.limit("30/minute")
async def verify_payment(
    request: Request,
    token: str,
    current_user: User = Depends(get_current_user),
):
    try:
        return await verify_paydunya_invoice(token)
    except httpx.HTTPError:
        raise HTTPException(status_code=500, detail="Erreur de connexion au service de paiement")
