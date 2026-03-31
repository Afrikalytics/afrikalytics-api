"""
Tests for the payments router — endpoints NOT covered by test_payments.py / test_payments_webhook.py.
Covers: plans list, current-plan, payment history, change-plan, verify payment.
"""
import pytest
from datetime import datetime, timedelta, timezone
from unittest.mock import patch, AsyncMock

from app.models import User, Subscription, Payment
from app.auth import hash_password, create_access_token
from app.services.payment_service import PLAN_FEATURES, VALID_PLANS


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def subscription(db, test_user):
    """Create an active subscription for test_user."""
    now = datetime.now(timezone.utc)
    sub = Subscription(
        user_id=test_user.id,
        plan="professionnel",
        status="active",
        start_date=now,
        end_date=now + timedelta(days=30),
    )
    db.add(sub)
    db.commit()
    db.refresh(sub)
    return sub


@pytest.fixture()
def pro_user_with_sub(db, subscription):
    """Update test_user to professionnel plan (subscription already created)."""
    user = db.get(User, subscription.user_id)
    user.plan = "professionnel"
    db.commit()
    db.refresh(user)
    return user


@pytest.fixture()
def payment_records(db, test_user, subscription):
    """Create 3 payment records for test_user."""
    payments = []
    for i in range(3):
        p = Payment(
            user_id=test_user.id,
            subscription_id=subscription.id,
            amount=295000,
            provider="paydunya",
            provider_ref=f"token_{i}",
            provider_status="completed",
            plan="professionnel",
            status="completed",
        )
        db.add(p)
        payments.append(p)
    db.commit()
    for p in payments:
        db.refresh(p)
    return payments


# ---------------------------------------------------------------------------
# GET /api/payments/plans — Public endpoint
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestGetPlans:
    def test_get_plans(self, client, auth_headers):
        resp = client.get("/api/payments/plans", headers=auth_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert "plans" in data
        assert "basic" in data["plans"]
        assert "professionnel" in data["plans"]
        assert "entreprise" in data["plans"]

    def test_get_plans_structure(self, client, auth_headers):
        resp = client.get("/api/payments/plans", headers=auth_headers)
        plans = resp.json()["plans"]
        for plan_name in ["basic", "professionnel", "entreprise"]:
            assert "max_studies" in plans[plan_name]
            assert "price_monthly" in plans[plan_name]


# ---------------------------------------------------------------------------
# GET /api/payments/current-plan
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestGetCurrentPlan:
    def test_current_plan_basic(self, client, auth_headers):
        resp = client.get("/api/payments/current-plan", headers=auth_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["plan"] == "basic"
        assert data["is_active"] is True
        assert data["expires_at"] is None
        assert "features" in data

    def test_current_plan_with_subscription(self, client, auth_headers, pro_user_with_sub, subscription):
        resp = client.get("/api/payments/current-plan", headers=auth_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["plan"] == "professionnel"
        assert data["expires_at"] is not None

    def test_current_plan_unauthorized(self, client):
        resp = client.get("/api/payments/current-plan")
        assert resp.status_code == 401


# ---------------------------------------------------------------------------
# GET /api/payments/history
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestPaymentHistory:
    def test_history_empty(self, client, auth_headers):
        resp = client.get("/api/payments/history", headers=auth_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 0
        assert data["payments"] == []
        assert data["current_page"] == 1

    def test_history_with_payments(self, client, auth_headers, payment_records):
        resp = client.get("/api/payments/history", headers=auth_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 3
        assert len(data["payments"]) == 3

    def test_history_pagination(self, client, auth_headers, payment_records):
        resp = client.get("/api/payments/history?skip=0&limit=2", headers=auth_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["payments"]) == 2
        assert data["total"] == 3
        assert data["current_page"] == 1

    def test_history_pagination_page2(self, client, auth_headers, payment_records):
        resp = client.get("/api/payments/history?skip=2&limit=2", headers=auth_headers)
        data = resp.json()
        assert len(data["payments"]) == 1
        assert data["current_page"] == 2

    def test_history_unauthorized(self, client):
        resp = client.get("/api/payments/history")
        assert resp.status_code == 401


# ---------------------------------------------------------------------------
# POST /api/payments/change-plan
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestChangePlan:
    def test_change_plan_same_plan(self, client, auth_headers):
        """Cannot change to the same plan."""
        resp = client.post(
            "/api/payments/change-plan",
            json={"plan": "basic", "email": "testuser@example.com", "name": "Test User"},
            headers=auth_headers,
        )
        assert resp.status_code == 400
        assert "deja" in resp.json()["detail"].lower() or "déjà" in resp.json()["detail"].lower()

    def test_change_plan_invalid(self, client, auth_headers):
        resp = client.post(
            "/api/payments/change-plan",
            json={"plan": "invalid_plan", "email": "testuser@example.com", "name": "Test User"},
            headers=auth_headers,
        )
        assert resp.status_code == 400

    def test_downgrade_to_basic(self, client, auth_headers, pro_user_with_sub, subscription):
        """Downgrade to basic is immediate, no payment needed."""
        resp = client.post(
            "/api/payments/change-plan",
            json={"plan": "basic", "email": "testuser@example.com", "name": "Test User"},
            headers=auth_headers,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert data["action"] == "downgraded"
        assert data["plan"] == "basic"

    @patch("app.routers.payments.create_paydunya_invoice_request", new_callable=AsyncMock)
    def test_upgrade_to_pro(self, mock_invoice, client, auth_headers):
        """Upgrade creates a PayDunya invoice."""
        mock_invoice.return_value = {
            "response_code": "00",
            "response_text": "https://paydunya.com/checkout/test",
            "token": "test_token_123",
        }

        resp = client.post(
            "/api/payments/change-plan",
            json={"plan": "professionnel", "email": "testuser@example.com", "name": "Test User"},
            headers=auth_headers,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert data["action"] == "payment_required"
        assert "payment_url" in data

    @patch("app.routers.payments.create_paydunya_invoice_request", new_callable=AsyncMock)
    def test_upgrade_paydunya_error(self, mock_invoice, client, auth_headers):
        """PayDunya error returns 400."""
        mock_invoice.return_value = {
            "response_code": "99",
            "response_text": "Service indisponible",
        }

        resp = client.post(
            "/api/payments/change-plan",
            json={"plan": "professionnel", "email": "testuser@example.com", "name": "Test User"},
            headers=auth_headers,
        )
        assert resp.status_code == 400

    def test_change_plan_unauthorized(self, client):
        resp = client.post(
            "/api/payments/change-plan",
            json={"plan": "professionnel", "email": "test@example.com", "name": "Test"},
        )
        assert resp.status_code == 401


# ---------------------------------------------------------------------------
# GET /api/paydunya/verify/{token}
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestVerifyPayment:
    @patch("app.routers.payments.verify_paydunya_invoice", new_callable=AsyncMock)
    def test_verify_success(self, mock_verify, client, auth_headers):
        mock_verify.return_value = {"status": "completed", "invoice": {"token": "abc"}}
        resp = client.get("/api/paydunya/verify/test_token", headers=auth_headers)
        assert resp.status_code == 200
        assert resp.json()["status"] == "completed"

    def test_verify_unauthorized(self, client):
        resp = client.get("/api/paydunya/verify/test_token")
        assert resp.status_code == 401
