import hashlib
import hmac
import httpx
import json
import logging
import re
import secrets
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.config import get_settings
from database import get_db
from models import User, Subscription, TokenBlacklist
from app.models import Payment
from auth import hash_password
from app.dependencies import get_current_user
from app.services.email import send_email
from app.services.email_templates import payment_upgrade_email, payment_new_user_email
from app.schemas.payments import (
    PaymentCreate,
    PaymentHistoryItem,
    PaymentHistoryResponse,
    CurrentPlanResponse,
    PlanFeatures,
)
from app.rate_limit import limiter

logger = logging.getLogger(__name__)

settings = get_settings()

VALID_PLANS = {"basic", "professionnel", "entreprise"}

PLAN_PRICES = {
    "professionnel": 295000,
    "entreprise": 500000,
}

PLAN_FEATURES: dict[str, dict] = {
    "basic": {
        "max_studies": 3,
        "max_team_members": 1,
        "export_pdf": False,
        "api_access": False,
        "custom_branding": False,
        "price_monthly": 0,
        "price_label": "Gratuit",
    },
    "professionnel": {
        "max_studies": 20,
        "max_team_members": 5,
        "export_pdf": True,
        "api_access": True,
        "custom_branding": False,
        "price_monthly": 15000,
        "price_label": "15 000 FCFA/mois",
    },
    "entreprise": {
        "max_studies": -1,  # illimite
        "max_team_members": -1,
        "export_pdf": True,
        "api_access": True,
        "custom_branding": True,
        "price_monthly": 50000,
        "price_label": "50 000 FCFA/mois",
    },
}

router = APIRouter()

# PayDunya configuration
PAYDUNYA_MASTER_KEY = settings.paydunya_master_key
PAYDUNYA_PRIVATE_KEY = settings.paydunya_private_key
PAYDUNYA_TOKEN = settings.paydunya_token
PAYDUNYA_MODE = settings.paydunya_mode


@router.get("/api/payments/history", response_model=PaymentHistoryResponse)
@limiter.limit("30/minute")
async def get_payment_history(
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
async def get_current_plan(
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
        current_user.plan = "basic"
        db.commit()

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

        return {
            "success": True,
            "action": "downgraded",
            "plan": "basic",
            "message": "Votre plan a ete mis a jour vers Basic.",
        }

    # Upgrade — create PayDunya invoice
    amount = PLAN_PRICES.get(target_plan, 295000)

    if PAYDUNYA_MODE == "live":
        base_url = "https://app.paydunya.com/api/v1"
    else:
        base_url = "https://app.paydunya.com/sandbox-api/v1"

    invoice_data = {
        "invoice": {
            "items": {
                "item_0": {
                    "name": f"Changement vers {target_plan.capitalize()} - Afrikalytics",
                    "quantity": 1,
                    "unit_price": amount,
                    "total_price": amount,
                    "description": f"Passage au plan {target_plan.capitalize()}",
                }
            },
            "total_amount": amount,
            "description": f"Afrikalytics - Passage au plan {target_plan.capitalize()}",
        },
        "store": {
            "name": "Afrikalytics AI",
            "tagline": "Intelligence d'Affaires pour l'Afrique",
            "postal_address": "Dakar, Senegal",
            "website_url": "https://afrikalytics.com",
        },
        "custom_data": {
            "email": current_user.email,
            "name": current_user.full_name,
            "plan": target_plan,
        },
        "actions": {
            "cancel_url": "https://afrikalytics.com/premium?status=cancelled",
            "return_url": "https://dashboard.afrikalytics.com/payment-success",
            "callback_url": settings.api_url + "/api/paydunya/webhook",
        },
    }

    headers = {
        "Content-Type": "application/json",
        "PAYDUNYA-MASTER-KEY": PAYDUNYA_MASTER_KEY,
        "PAYDUNYA-PRIVATE-KEY": PAYDUNYA_PRIVATE_KEY,
        "PAYDUNYA-TOKEN": PAYDUNYA_TOKEN,
    }

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                f"{base_url}/checkout-invoice/create",
                json=invoice_data,
                headers=headers,
            )
        result = response.json()

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
async def get_available_plans(request: Request):
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
    if PAYDUNYA_MODE == "live":
        base_url = "https://app.paydunya.com/api/v1"
    else:
        base_url = "https://app.paydunya.com/sandbox-api/v1"

    amount = PLAN_PRICES.get(data.plan, 295000)

    invoice_data = {
        "invoice": {
            "items": {
                "item_0": {
                    "name": f"Abonnement {data.plan.capitalize()} - Afrikalytics",
                    "quantity": 1,
                    "unit_price": amount,
                    "total_price": amount,
                    "description": f"Abonnement mensuel au plan {data.plan.capitalize()}"
                }
            },
            "total_amount": amount,
            "description": f"Abonnement Afrikalytics - Plan {data.plan.capitalize()}"
        },
        "store": {
            "name": "Afrikalytics AI",
            "tagline": "Intelligence d'Affaires pour l'Afrique",
            "postal_address": "Dakar, Sénégal",
            "website_url": "https://afrikalytics.com"
        },
        "custom_data": {
            "email": data.email,
            "name": data.name,
            "plan": data.plan
        },
        "actions": {
            "cancel_url": "https://afrikalytics.com/premium?status=cancelled",
            "return_url": "https://dashboard.afrikalytics.com/payment-success",
            "callback_url": settings.api_url + "/api/paydunya/webhook"
        }
    }

    headers = {
        "Content-Type": "application/json",
        "PAYDUNYA-MASTER-KEY": PAYDUNYA_MASTER_KEY,
        "PAYDUNYA-PRIVATE-KEY": PAYDUNYA_PRIVATE_KEY,
        "PAYDUNYA-TOKEN": PAYDUNYA_TOKEN
    }

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                f"{base_url}/checkout-invoice/create",
                json=invoice_data,
                headers=headers,
            )
        result = response.json()

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
    # Verify HMAC-SHA512 signature from PAYDUNYA-SIGNATURE header
    body = await request.body()
    signature = request.headers.get("PAYDUNYA-SIGNATURE", "")
    if PAYDUNYA_MASTER_KEY:
        expected_signature = hmac.new(
            PAYDUNYA_MASTER_KEY.encode(),
            body,
            hashlib.sha512,
        ).hexdigest()
        if not hmac.compare_digest(signature, expected_signature):
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
            (PAYDUNYA_MASTER_KEY + invoice_token).encode('utf-8')
        ).hexdigest()
        if received_hash != expected_hash:
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
            if PAYDUNYA_MODE == "live":
                verify_url = f"https://app.paydunya.com/api/v1/checkout-invoice/confirm/{token}"
            else:
                verify_url = f"https://app.paydunya.com/sandbox-api/v1/checkout-invoice/confirm/{token}"

            verify_headers = {
                "PAYDUNYA-MASTER-KEY": PAYDUNYA_MASTER_KEY,
                "PAYDUNYA-PRIVATE-KEY": PAYDUNYA_PRIVATE_KEY,
                "PAYDUNYA-TOKEN": PAYDUNYA_TOKEN
            }

            try:
                async with httpx.AsyncClient(timeout=30.0) as client:
                    verify_response = await client.get(verify_url, headers=verify_headers)
                verify_data = verify_response.json()
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

        existing_user = db.execute(
            select(User).where(User.email == email)
        ).scalar_one_or_none()

        if existing_user:
            existing_user.plan = plan
            existing_user.is_active = True
            db.commit()

            existing_subscription = db.execute(
                select(Subscription).where(
                    Subscription.user_id == existing_user.id,
                    Subscription.status == "active"
                )
            ).scalar_one_or_none()

            if existing_subscription:
                existing_subscription.plan = plan
                existing_subscription.start_date = datetime.now(timezone.utc)
                existing_subscription.end_date = datetime.now(timezone.utc) + timedelta(days=30)
                existing_subscription.status = "active"
            else:
                new_subscription = Subscription(
                    user_id=existing_user.id,
                    plan=plan,
                    status="active",
                    start_date=datetime.now(timezone.utc),
                    end_date=datetime.now(timezone.utc) + timedelta(days=30)
                )
                db.add(new_subscription)

            db.commit()

            # Resolve subscription for payment record
            active_sub = existing_subscription or db.execute(
                select(Subscription).where(
                    Subscription.user_id == existing_user.id,
                    Subscription.status == "active"
                )
            ).scalar_one_or_none()

            # Create Payment record
            payment_record = Payment(
                user_id=existing_user.id,
                subscription_id=active_sub.id if active_sub else None,
                amount=PLAN_PRICES.get(plan, 295000),
                provider="paydunya",
                provider_ref=token,
                provider_status="completed",
                plan=plan,
                status="completed",
                metadata_json={"invoice_data": data},
            )
            db.add(payment_record)
            db.commit()

            send_email(
                to=email,
                subject="Bienvenue dans Afrikalytics Premium !",
                html=payment_upgrade_email(existing_user.full_name, plan),
            )

            # Mark this webhook as processed (idempotency — DB-backed)
            webhook_blacklist = TokenBlacklist(
                jti=f"webhook_{invoice_token}",
                user_id=existing_user.id,
                expires_at=datetime.now(timezone.utc) + timedelta(days=90),
            )
            db.add(webhook_blacklist)
            db.commit()

            return {"status": "success", "action": "user_upgraded", "user_id": existing_user.id}

        else:
            temp_password = secrets.token_urlsafe(12)
            hashed_password = hash_password(temp_password)

            new_user = User(
                email=email,
                full_name=name,
                hashed_password=hashed_password,
                plan=plan,
                is_active=True
            )

            db.add(new_user)
            db.commit()
            db.refresh(new_user)

            new_subscription = Subscription(
                user_id=new_user.id,
                plan=plan,
                status="active",
                start_date=datetime.now(timezone.utc),
                end_date=datetime.now(timezone.utc) + timedelta(days=30)
            )
            db.add(new_subscription)
            db.commit()
            db.refresh(new_subscription)

            # Create Payment record
            payment_record = Payment(
                user_id=new_user.id,
                subscription_id=new_subscription.id,
                amount=PLAN_PRICES.get(plan, 295000),
                provider="paydunya",
                provider_ref=token,
                provider_status="completed",
                plan=plan,
                status="completed",
                metadata_json={"invoice_data": data},
            )
            db.add(payment_record)
            db.commit()

            send_email(
                to=email,
                subject="Bienvenue dans Afrikalytics Premium !",
                html=payment_new_user_email(name, email, temp_password, plan),
            )

            # Mark this webhook as processed (idempotency — DB-backed)
            webhook_blacklist = TokenBlacklist(
                jti=f"webhook_{invoice_token}",
                user_id=new_user.id,
                expires_at=datetime.now(timezone.utc) + timedelta(days=90),
            )
            db.add(webhook_blacklist)
            db.commit()

            return {"status": "success", "action": "user_created", "user_id": new_user.id}

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
    if PAYDUNYA_MODE == "live":
        base_url = "https://app.paydunya.com/api/v1"
    else:
        base_url = "https://app.paydunya.com/sandbox-api/v1"

    headers = {
        "Content-Type": "application/json",
        "PAYDUNYA-MASTER-KEY": PAYDUNYA_MASTER_KEY,
        "PAYDUNYA-PRIVATE-KEY": PAYDUNYA_PRIVATE_KEY,
        "PAYDUNYA-TOKEN": PAYDUNYA_TOKEN
    }

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(
                f"{base_url}/checkout-invoice/confirm/{token}",
                headers=headers,
            )
        return response.json()
    except httpx.HTTPError:
        raise HTTPException(status_code=500, detail="Erreur de connexion au service de paiement")
