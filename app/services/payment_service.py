"""
Service de paiement PayDunya.

Centralise la logique PayDunya (URL, headers, creation de facture, enregistrement
de paiement) pour eliminer la duplication dans le router payments.
"""
import logging
from datetime import datetime, timedelta, timezone

import httpx
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models import Payment, TokenBlacklist

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

VALID_PLANS: set[str] = {"basic", "professionnel", "entreprise"}

PLAN_PRICES: dict[str, int] = {
    "professionnel": 295000,
    "entreprise": 500000,
}

PLAN_DURATIONS: dict[str, timedelta] = {
    "professionnel": timedelta(days=30),
    "entreprise": timedelta(days=30),
}

WEBHOOK_IDEMPOTENCY_TTL: timedelta = timedelta(days=90)

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

# Store info (shared across all invoices)
_STORE_INFO: dict = {
    "name": "Afrikalytics AI",
    "tagline": "Intelligence d'Affaires pour l'Afrique",
    "postal_address": "Dakar, Senegal",
    "website_url": "https://afrikalytics.com",
}


# ---------------------------------------------------------------------------
# PayDunya helpers
# ---------------------------------------------------------------------------

def get_paydunya_base_url() -> str:
    """Return the PayDunya API base URL based on configured mode (live/test)."""
    settings = get_settings()
    if settings.paydunya_mode == "live":
        return "https://app.paydunya.com/api/v1"
    return "https://app.paydunya.com/sandbox-api/v1"


def get_paydunya_headers() -> dict[str, str]:
    """Return HTTP headers required by the PayDunya API."""
    settings = get_settings()
    return {
        "Content-Type": "application/json",
        "PAYDUNYA-MASTER-KEY": settings.paydunya_master_key,
        "PAYDUNYA-PRIVATE-KEY": settings.paydunya_private_key,
        "PAYDUNYA-TOKEN": settings.paydunya_token,
    }


def get_plan_price(plan: str) -> int:
    """Return the price in FCFA for the given plan."""
    return PLAN_PRICES.get(plan, 295000)


def get_plan_duration(plan: str) -> timedelta:
    """Return subscription duration for the given plan."""
    return PLAN_DURATIONS.get(plan, timedelta(days=30))


# ---------------------------------------------------------------------------
# Invoice creation
# ---------------------------------------------------------------------------

async def create_paydunya_invoice_request(
    plan: str,
    email: str,
    name: str,
    *,
    item_name: str | None = None,
    item_description: str | None = None,
    invoice_description: str | None = None,
) -> dict:
    """
    Create a PayDunya checkout invoice and return the raw API response dict.

    If item_name / item_description / invoice_description are not provided,
    sensible defaults are generated from the plan name.

    Raises:
        httpx.HTTPError: on network / timeout errors.
    """
    settings = get_settings()
    amount = get_plan_price(plan)
    base_url = get_paydunya_base_url()
    headers = get_paydunya_headers()

    plan_label = plan.capitalize()
    _item_name = item_name or f"Abonnement {plan_label} - Afrikalytics"
    _item_desc = item_description or f"Abonnement mensuel au plan {plan_label}"
    _invoice_desc = invoice_description or f"Abonnement Afrikalytics - Plan {plan_label}"

    invoice_data = {
        "invoice": {
            "items": {
                "item_0": {
                    "name": _item_name,
                    "quantity": 1,
                    "unit_price": amount,
                    "total_price": amount,
                    "description": _item_desc,
                }
            },
            "total_amount": amount,
            "description": _invoice_desc,
        },
        "store": _STORE_INFO,
        "custom_data": {
            "email": email,
            "name": name,
            "plan": plan,
        },
        "actions": {
            "cancel_url": "https://afrikalytics.com/premium?status=cancelled",
            "return_url": "https://dashboard.afrikalytics.com/payment-success",
            "callback_url": settings.api_url + "/api/paydunya/webhook",
        },
    }

    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.post(
            f"{base_url}/checkout-invoice/create",
            json=invoice_data,
            headers=headers,
        )
    return response.json()


async def verify_paydunya_invoice(token: str) -> dict:
    """
    Verify / confirm a PayDunya invoice by token. Returns the raw API response.

    Raises:
        httpx.HTTPError: on network / timeout errors.
    """
    base_url = get_paydunya_base_url()
    headers = get_paydunya_headers()

    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.get(
            f"{base_url}/checkout-invoice/confirm/{token}",
            headers=headers,
        )
    return response.json()


# ---------------------------------------------------------------------------
# DB record helpers
# ---------------------------------------------------------------------------

def create_payment_record(
    db: Session,
    user_id: int,
    plan: str,
    amount: int,
    token: str | None,
    status: str,
    subscription_id: int | None = None,
    invoice_data: dict | None = None,
) -> Payment:
    """Create and persist a Payment record. Caller must commit the session."""
    payment = Payment(
        user_id=user_id,
        subscription_id=subscription_id,
        amount=amount,
        provider="paydunya",
        provider_ref=token,
        provider_status=status,
        plan=plan,
        status=status,
        metadata_json={"invoice_data": invoice_data} if invoice_data else None,
    )
    db.add(payment)
    return payment


def mark_webhook_processed(
    db: Session,
    token: str,
    user_id: int,
) -> TokenBlacklist:
    """
    Insert a TokenBlacklist entry so the same webhook is never processed twice.
    Caller must commit the session.
    """
    entry = TokenBlacklist(
        jti=f"webhook_{token}",
        user_id=user_id,
        expires_at=datetime.now(timezone.utc) + WEBHOOK_IDEMPOTENCY_TTL,
    )
    db.add(entry)
    return entry
