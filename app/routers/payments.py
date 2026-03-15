import hashlib
import json
import logging
import re
import secrets
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from database import get_db
from models import User, Subscription, TokenBlacklist
from app.models import Payment
from auth import hash_password
from app.dependencies import get_current_user
from app.services.email import send_email
from app.services.email_templates import payment_upgrade_email, payment_new_user_email
from app.schemas.payments import PaymentCreate

logger = logging.getLogger(__name__)

settings = get_settings()

VALID_PLANS = {"basic", "professionnel", "entreprise"}

PLAN_PRICES = {
    "professionnel": 295000,
    "entreprise": 500000,
}

router = APIRouter()

# PayDunya configuration
PAYDUNYA_MASTER_KEY = settings.paydunya_master_key
PAYDUNYA_PRIVATE_KEY = settings.paydunya_private_key
PAYDUNYA_TOKEN = settings.paydunya_token
PAYDUNYA_MODE = settings.paydunya_mode


@router.post("/api/paydunya/create-invoice")
async def create_paydunya_invoice(
    data: PaymentCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    import requests

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
        response = requests.post(
            f"{base_url}/checkout-invoice/create",
            json=invoice_data,
            headers=headers
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
    except __import__('requests').RequestException:
        raise HTTPException(status_code=500, detail="Erreur de connexion au service de paiement")


@router.post("/api/paydunya/webhook")
async def paydunya_webhook(
    request: Request,
    db: Session = Depends(get_db),
):
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
            import requests as req
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
                verify_response = req.get(verify_url, headers=verify_headers)
                verify_data = verify_response.json()
                logger.info("PayDunya verification completed")
                status = verify_data.get("status")
                if not data.get("custom_data"):
                    data["custom_data"] = verify_data.get("custom_data", {})
            except Exception:
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
async def verify_payment(
    token: str,
    current_user: User = Depends(get_current_user),
):
    import requests

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
        response = requests.get(
            f"{base_url}/checkout-invoice/confirm/{token}",
            headers=headers
        )
        return response.json()
    except requests.RequestException:
        raise HTTPException(status_code=500, detail="Erreur de connexion au service de paiement")
