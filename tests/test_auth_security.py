"""
Security-focused tests for authentication — /api/auth/*

Covers attack vectors and edge cases NOT in test_auth.py / test_auth_extended.py:
- Brute-force protection on verify-code (5 attempts lockout)
- Resend-code endpoint
- Subscription expiry check during login
- Token reuse after reset
- SSO state CSRF protection helpers
- get_current_user dependency edge cases

TDD RED phase: these tests define the security contract.
"""
import os
import time
from datetime import datetime, timedelta, timezone
from unittest.mock import patch, MagicMock

import pytest

from app.auth import (
    create_access_token,
    create_refresh_token,
    hash_password,
)
from app.models import User, VerificationCode, Subscription, TokenBlacklist
from app.routers.auth import generate_sso_state, verify_sso_state

_TPW = os.environ.get("TEST_PASSWORD", "TestPass-Fixture-1!")


# ================================================================
# SSO State CSRF helpers
# ================================================================

class TestSSOStateHelpers:
    """Unit tests for generate_sso_state / verify_sso_state."""

    def test_generate_returns_string_with_three_parts(self):
        state = generate_sso_state("test-secret")
        parts = state.split(".")
        assert len(parts) == 3  # timestamp.nonce.signature

    def test_valid_state_verifies(self):
        secret = "my-secret-key"
        state = generate_sso_state(secret)
        assert verify_sso_state(state, secret) is True

    def test_wrong_secret_rejects(self):
        state = generate_sso_state("correct-secret")
        assert verify_sso_state(state, "wrong-secret") is False

    def test_tampered_state_rejects(self):
        state = generate_sso_state("secret")
        tampered = state[:-4] + "ZZZZ"
        assert verify_sso_state(tampered, "secret") is False

    def test_expired_state_rejects(self):
        """State older than max_age should be rejected."""
        secret = "secret"
        state = generate_sso_state(secret)
        # Simulate time passage by using a very short max_age
        assert verify_sso_state(state, secret, max_age=0) is False

    def test_empty_state_rejects(self):
        assert verify_sso_state("", "secret") is False

    def test_malformed_state_rejects(self):
        assert verify_sso_state("no-dots-here", "secret") is False

    def test_two_states_are_unique(self):
        secret = "secret"
        s1 = generate_sso_state(secret)
        s2 = generate_sso_state(secret)
        assert s1 != s2


# ================================================================
# Brute-force protection on verify-code
# ================================================================

class TestVerifyCodeBruteForce:
    """Tests for the 5-attempt lockout on verify-code."""

    def test_lockout_after_five_failed_attempts(self, client, test_user, db):
        """
        After 5 failed verify-code attempts within 10 minutes,
        the endpoint must return 429 and invalidate all active codes.
        """
        # Create a valid code
        valid_code = VerificationCode(
            user_id=test_user.id,
            code="123456",
            expires_at=datetime.now(timezone.utc) + timedelta(minutes=10),
            is_used=False,
        )
        db.add(valid_code)
        db.commit()

        # Make 5 failed attempts with wrong codes
        for i in range(5):
            response = client.post(
                "/api/auth/verify-code",
                json={"email": test_user.email, "code": f"00000{i}"},
            )
            assert response.status_code == 401

        # 6th attempt should be rate-limited (429)
        response = client.post(
            "/api/auth/verify-code",
            json={"email": test_user.email, "code": "123456"},
        )
        assert response.status_code == 429
        assert "tentatives" in response.json()["detail"].lower()

    def test_valid_code_works_before_lockout(self, client, test_user, db):
        """A valid code on the 3rd attempt should still work."""
        valid_code = VerificationCode(
            user_id=test_user.id,
            code="555555",
            expires_at=datetime.now(timezone.utc) + timedelta(minutes=10),
            is_used=False,
        )
        db.add(valid_code)
        db.commit()

        # 2 failed attempts
        for _ in range(2):
            client.post(
                "/api/auth/verify-code",
                json={"email": test_user.email, "code": "000000"},
            )

        # 3rd attempt with valid code should succeed
        response = client.post(
            "/api/auth/verify-code",
            json={"email": test_user.email, "code": "555555"},
        )
        assert response.status_code == 200
        assert "access_token" in response.json()


# ================================================================
# Resend-code endpoint
# ================================================================

class TestResendCode:
    """Tests for POST /api/auth/resend-code."""

    def test_resend_code_known_email(self, client, test_user):
        """Resend-code for a known email should return 200."""
        response = client.post(
            "/api/auth/resend-code",
            json={"email": test_user.email},
        )
        assert response.status_code == 200
        assert "message" in response.json()

    def test_resend_code_unknown_email_no_leak(self, client):
        """Resend-code for an unknown email should return 200 (no leak)."""
        response = client.post(
            "/api/auth/resend-code",
            json={"email": "unknown@example.com"},
        )
        assert response.status_code == 200
        assert "message" in response.json()

    def test_resend_code_invalidates_old_codes(self, client, test_user, db):
        """Old unused codes should be deleted when resending."""
        # Create old code
        old_code = VerificationCode(
            user_id=test_user.id,
            code="111111",
            expires_at=datetime.now(timezone.utc) + timedelta(minutes=10),
            is_used=False,
        )
        db.add(old_code)
        db.commit()

        # Resend
        client.post(
            "/api/auth/resend-code",
            json={"email": test_user.email},
        )

        # Old code should no longer work
        response = client.post(
            "/api/auth/verify-code",
            json={"email": test_user.email, "code": "111111"},
        )
        assert response.status_code == 401


# ================================================================
# Subscription expiry check during login
# ================================================================

class TestLoginSubscriptionExpiry:
    """Tests for automatic subscription downgrade on login."""

    def test_expired_subscription_downgrades_to_basic(self, client, db):
        """A user with an expired pro subscription should be downgraded on login."""
        user = User(
            email="pro_expired@example.com",
            full_name="Pro Expired",
            hashed_password=hash_password(_TPW),
            plan="professionnel",
            is_active=True,
            is_admin=False,
        )
        db.add(user)
        db.commit()
        db.refresh(user)

        # Create expired subscription
        sub = Subscription(
            user_id=user.id,
            plan="professionnel",
            status="active",
            start_date=datetime.now(timezone.utc) - timedelta(days=60),
            end_date=datetime.now(timezone.utc) - timedelta(days=1),
        )
        db.add(sub)
        db.commit()

        # Login — should trigger downgrade
        response = client.post(
            "/api/auth/login",
            json={"email": "pro_expired@example.com", "password": _TPW},
        )
        assert response.status_code == 200

        # Verify user was downgraded
        db.refresh(user)
        assert user.plan == "basic"

    def test_active_subscription_not_downgraded(self, client, db):
        """A user with an active subscription should keep their plan."""
        user = User(
            email="pro_active@example.com",
            full_name="Pro Active",
            hashed_password=hash_password(_TPW),
            plan="professionnel",
            is_active=True,
            is_admin=False,
        )
        db.add(user)
        db.commit()
        db.refresh(user)

        # Create active subscription (ends in 30 days)
        sub = Subscription(
            user_id=user.id,
            plan="professionnel",
            status="active",
            start_date=datetime.now(timezone.utc) - timedelta(days=5),
            end_date=datetime.now(timezone.utc) + timedelta(days=30),
        )
        db.add(sub)
        db.commit()

        # Login
        response = client.post(
            "/api/auth/login",
            json={"email": "pro_active@example.com", "password": _TPW},
        )
        assert response.status_code == 200

        # Plan should remain professionnel
        db.refresh(user)
        assert user.plan == "professionnel"


# ================================================================
# Token reuse protection (reset password)
# ================================================================

class TestResetTokenReuse:
    """Tests for single-use reset tokens."""

    def test_reset_token_cannot_be_reused(self, client, test_user, db):
        """A reset token used once should be blacklisted and rejected on second use."""
        reset_token = create_access_token(
            data={"sub": test_user.email, "type": "reset"},
            expires_delta=timedelta(hours=1),
        )

        # First use — should succeed
        response1 = client.post(
            "/api/auth/reset-password",
            json={"token": reset_token, "new_password": "NewPassword123!"},
        )
        assert response1.status_code == 200

        # Second use — should fail
        response2 = client.post(
            "/api/auth/reset-password",
            json={"token": reset_token, "new_password": "AnotherPassword123!"},
        )
        assert response2.status_code == 400
        assert "déjà" in response2.json()["detail"].lower()


# ================================================================
# get_current_user dependency edge cases
# ================================================================

class TestGetCurrentUser:
    """Tests for the get_current_user dependency via /api/users/me."""

    def test_no_auth_header_returns_401(self, client):
        response = client.get("/api/users/me")
        assert response.status_code == 401

    def test_malformed_bearer_returns_401(self, client):
        response = client.get(
            "/api/users/me",
            headers={"Authorization": "NotBearer token"},
        )
        assert response.status_code == 401

    def test_expired_token_returns_401(self, client, test_user):
        token = create_access_token(
            data={"sub": test_user.email},
            expires_delta=timedelta(seconds=-1),
        )
        response = client.get(
            "/api/users/me",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == 401
        assert "expiré" in response.json()["detail"].lower()

    def test_refresh_token_as_access_returns_401(self, client, test_user):
        """Using a refresh token to access protected endpoints must fail."""
        refresh = create_refresh_token(
            data={"sub": test_user.email, "user_id": test_user.id}
        )
        response = client.get(
            "/api/users/me",
            headers={"Authorization": f"Bearer {refresh}"},
        )
        assert response.status_code == 401

    def test_blacklisted_token_returns_401(self, client, test_user, db):
        """A blacklisted token must be rejected."""
        token = create_access_token(
            data={"sub": test_user.email, "user_id": test_user.id}
        )
        from app.auth import decode_access_token
        payload = decode_access_token(token)

        # Blacklist the token
        bl = TokenBlacklist(
            jti=payload["jti"],
            user_id=test_user.id,
            expires_at=datetime.fromtimestamp(payload["exp"], tz=timezone.utc),
        )
        db.add(bl)
        db.commit()

        response = client.get(
            "/api/users/me",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == 401

    def test_deleted_user_token_returns_401(self, client, db):
        """Token for a user that no longer exists must return 401."""
        user = User(
            email="ghost@example.com",
            full_name="Ghost",
            hashed_password=hash_password(_TPW),
            plan="basic",
            is_active=True,
            is_admin=False,
        )
        db.add(user)
        db.commit()
        db.refresh(user)

        token = create_access_token(data={"sub": user.email, "user_id": user.id})

        # Delete the user
        db.delete(user)
        db.commit()

        response = client.get(
            "/api/users/me",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == 401

    def test_inactive_user_token_returns_403(self, client, db):
        """Token for an inactive user must return 403."""
        user = User(
            email="disabled@example.com",
            full_name="Disabled",
            hashed_password=hash_password(_TPW),
            plan="basic",
            is_active=False,
            is_admin=False,
        )
        db.add(user)
        db.commit()
        db.refresh(user)

        token = create_access_token(data={"sub": user.email, "user_id": user.id})

        response = client.get(
            "/api/users/me",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == 403


# ================================================================
# Register endpoint — field mapping edge case
# ================================================================

class TestRegisterFieldMapping:
    """Test that register correctly maps 'name' to 'full_name'."""

    def test_register_uses_name_field(self, client):
        """The register schema uses 'name' but the model uses 'full_name'."""
        payload = {
            "email": "fieldtest@example.com",
            "name": "Field Test User",
            "password": "StrongPass123!",
        }
        response = client.post("/api/auth/register", json=payload)
        assert response.status_code == 201
        data = response.json()
        assert data["user"]["full_name"] == "Field Test User"
