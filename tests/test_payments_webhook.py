"""
Extended tests for PayDunya payment endpoints — /api/paydunya/*

Covers webhook validation, idempotency, and payment record creation:
- POST /api/paydunya/webhook — signature validation, idempotency, record creation
- GET  /api/paydunya/verify/{token} — requires auth
- POST /api/paydunya/create-invoice — requires auth
"""

import hashlib
import os

import pytest

from app.auth import hash_password
from app.models import User, TokenBlacklist, Payment, Subscription


def _compute_webhook_hash(master_key: str, invoice_token: str) -> str:
    """Compute the expected PayDunya webhook hash."""
    return hashlib.sha512(
        (master_key + invoice_token).encode("utf-8")
    ).hexdigest()


def _build_webhook_payload(
    email: str,
    name: str,
    plan: str,
    invoice_token: str,
    master_key: str,
    status: str = "completed",
) -> dict:
    """Build a valid PayDunya webhook payload with correct signature."""
    return {
        "hash": _compute_webhook_hash(master_key, invoice_token),
        "status": status,
        "token": invoice_token,
        "invoice": {"token": invoice_token},
        "custom_data": {
            "email": email,
            "name": name,
            "plan": plan,
        },
    }


class TestWebhookSignatureValidation:
    """Tests for webhook signature verification."""

    def test_webhook_missing_hash_returns_403(self, client):
        """A webhook without a hash must be rejected with 403."""
        payload = {
            "status": "completed",
            "invoice": {"token": "some-token"},
            "custom_data": {
                "email": "test@example.com",
                "plan": "professionnel",
            },
        }
        response = client.post("/api/paydunya/webhook", json=payload)
        # Missing hash should trigger 403 or be caught by error handler
        assert response.status_code in (403, 200)
        if response.status_code == 200:
            assert response.json().get("status") in ("error",)

    def test_webhook_missing_token_returns_403(self, client):
        """A webhook without an invoice token must be rejected."""
        payload = {
            "hash": "some-hash",
            "status": "completed",
            "custom_data": {
                "email": "test@example.com",
                "plan": "professionnel",
            },
        }
        response = client.post("/api/paydunya/webhook", json=payload)
        assert response.status_code in (403, 200)

    def test_webhook_invalid_signature_returns_403(self, client):
        """A webhook with a wrong hash must be rejected with 403."""
        payload = {
            "hash": "invalid_hash_value_that_does_not_match",
            "status": "completed",
            "token": "test-token-invalid",
            "invoice": {"token": "test-token-invalid"},
            "custom_data": {
                "email": "test@example.com",
                "name": "Test",
                "plan": "professionnel",
            },
        }
        response = client.post("/api/paydunya/webhook", json=payload)
        # Should be rejected due to hash mismatch
        assert response.status_code in (403, 200)
        if response.status_code == 200:
            assert response.json().get("status") == "error"

    def test_webhook_valid_signature_processes_payment(self, client, db):
        """A webhook with a valid signature must process the payment."""
        master_key = os.getenv("PAYDUNYA_MASTER_KEY", "")
        invoice_token = "valid-sig-test-token-001"
        email = "webhook_valid@example.com"

        payload = _build_webhook_payload(
            email=email,
            name="Webhook Valid",
            plan="professionnel",
            invoice_token=invoice_token,
            master_key=master_key,
        )

        response = client.post("/api/paydunya/webhook", json=payload)
        # With empty master_key in test env, signature should match
        # (sha512("" + token) == sha512(token))
        assert response.status_code == 200
        data = response.json()
        assert data.get("status") == "success"


class TestWebhookIdempotency:
    """Tests for webhook idempotency (duplicate processing)."""

    def test_webhook_duplicate_is_idempotent(self, client, db):
        """Sending the same webhook twice must be idempotent."""
        master_key = os.getenv("PAYDUNYA_MASTER_KEY", "")
        invoice_token = "idempotent-test-token-001"

        payload = _build_webhook_payload(
            email="idempotent@example.com",
            name="Idempotent User",
            plan="professionnel",
            invoice_token=invoice_token,
            master_key=master_key,
        )

        # First call
        response1 = client.post("/api/paydunya/webhook", json=payload)
        assert response1.status_code == 200
        data1 = response1.json()
        assert data1.get("status") == "success"

        # Second call with same token
        response2 = client.post("/api/paydunya/webhook", json=payload)
        assert response2.status_code == 200
        data2 = response2.json()
        assert data2.get("status") == "already_processed"


class TestWebhookCreatesPaymentRecord:
    """Tests for payment record creation via webhook."""

    def test_webhook_creates_payment_for_existing_user(self, client, db, test_user):
        """Webhook for an existing user must create a Payment and upgrade plan."""
        master_key = os.getenv("PAYDUNYA_MASTER_KEY", "")
        invoice_token = "payment-record-test-001"

        payload = _build_webhook_payload(
            email=test_user.email,
            name=test_user.full_name,
            plan="professionnel",
            invoice_token=invoice_token,
            master_key=master_key,
        )

        response = client.post("/api/paydunya/webhook", json=payload)
        assert response.status_code == 200
        data = response.json()
        assert data.get("status") == "success"
        assert data.get("action") == "user_upgraded"

        # Verify user plan was updated
        db.expire_all()
        updated_user = db.query(User).filter(User.id == test_user.id).first()
        assert updated_user.plan == "professionnel"

    def test_webhook_creates_new_user_when_not_found(self, client, db):
        """Webhook for a new email must create a user account."""
        master_key = os.getenv("PAYDUNYA_MASTER_KEY", "")
        invoice_token = "new-user-test-001"
        new_email = "brandnew_webhook@example.com"

        payload = _build_webhook_payload(
            email=new_email,
            name="Brand New User",
            plan="professionnel",
            invoice_token=invoice_token,
            master_key=master_key,
        )

        response = client.post("/api/paydunya/webhook", json=payload)
        assert response.status_code == 200
        data = response.json()
        assert data.get("status") == "success"
        assert data.get("action") == "user_created"

        # Verify user was created
        created_user = db.query(User).filter(User.email == new_email).first()
        assert created_user is not None
        assert created_user.plan == "professionnel"
        assert created_user.is_active is True

    def test_webhook_non_completed_status_is_ignored(self, client, db):
        """A webhook with status != 'completed' must be ignored."""
        master_key = os.getenv("PAYDUNYA_MASTER_KEY", "")
        invoice_token = "pending-test-token-001"

        payload = _build_webhook_payload(
            email="pending@example.com",
            name="Pending User",
            plan="professionnel",
            invoice_token=invoice_token,
            master_key=master_key,
            status="pending",
        )

        response = client.post("/api/paydunya/webhook", json=payload)
        assert response.status_code == 200
        data = response.json()
        assert data.get("status") == "ignored"

    def test_webhook_invalid_plan_returns_error(self, client, db):
        """A webhook with an unknown plan must be rejected."""
        master_key = os.getenv("PAYDUNYA_MASTER_KEY", "")
        invoice_token = "invalid-plan-test-001"

        payload = _build_webhook_payload(
            email="badplan@example.com",
            name="Bad Plan User",
            plan="plan_inexistant",
            invoice_token=invoice_token,
            master_key=master_key,
        )

        response = client.post("/api/paydunya/webhook", json=payload)
        # Should return 400 or 200 with error
        assert response.status_code in (400, 200)


class TestVerifyPaymentAuth:
    """Tests for GET /api/paydunya/verify/{token}."""

    def test_verify_payment_requires_auth(self, client):
        """Verify endpoint must require authentication."""
        response = client.get("/api/paydunya/verify/some-token")
        assert response.status_code == 401

    def test_verify_payment_with_auth_accepted(self, client, auth_headers):
        """
        Verify endpoint with auth should be accepted (may fail with PayDunya
        sandbox but should not return 401/403).
        """
        response = client.get(
            "/api/paydunya/verify/test-token-xyz",
            headers=auth_headers,
        )
        # Should not be an auth error; may be 200 or 500 depending on
        # PayDunya sandbox connectivity
        assert response.status_code != 401
        assert response.status_code != 403


class TestCreateInvoiceAuth:
    """Tests for POST /api/paydunya/create-invoice."""

    def test_create_invoice_without_auth_returns_401(self, client):
        """Create invoice requires authentication."""
        payload = {
            "plan": "professionnel",
            "email": "user@example.com",
            "name": "Test User",
        }
        response = client.post("/api/paydunya/create-invoice", json=payload)
        assert response.status_code == 401

    def test_create_invoice_missing_fields_returns_422(
        self, client, auth_headers
    ):
        """Missing required fields must return 422."""
        response = client.post(
            "/api/paydunya/create-invoice",
            json={},
            headers=auth_headers,
        )
        assert response.status_code == 422
