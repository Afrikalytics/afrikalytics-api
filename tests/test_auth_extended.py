"""
Extended tests for authentication endpoints — /api/auth/*

Covers error paths and advanced flows not in test_auth.py:
- POST /api/auth/register  — duplicate email, weak password
- POST /api/auth/login     — wrong password, inactive user
- POST /api/auth/verify-code — invalid code, expired code
- POST /api/auth/forgot-password — unknown email (no info leak)
- POST /api/auth/reset-password — invalid token
- POST /api/auth/refresh   — valid refresh, blacklisted token
- POST /api/auth/logout    — blacklists token
"""

import os
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

from app.auth import create_access_token, create_refresh_token, hash_password
from app.models import User, VerificationCode, TokenBlacklist

_TPW = os.environ.get("TEST_PASSWORD", "TestPass-Fixture-1!")


class TestRegisterErrors:
    """Error cases for POST /api/auth/register."""

    def test_register_duplicate_email_returns_400(self, client, test_user):
        """Registering with an existing email must be rejected."""
        payload = {
            "email": test_user.email,
            "name": "Duplicate User",
            "password": _TPW,
        }
        response = client.post("/api/auth/register", json=payload)
        assert response.status_code == 400
        assert "detail" in response.json()

    def test_register_weak_password_no_uppercase(self, client):
        """A password without uppercase letters should be rejected."""
        payload = {
            "email": "weakpwd@example.com",
            "name": "Weak Pwd",
            "password": "nocapital123!",
        }
        response = client.post("/api/auth/register", json=payload)
        assert response.status_code == 400
        data = response.json()
        assert "detail" in data
        assert "majuscule" in data["detail"].lower()

    def test_register_weak_password_too_short(self, client):
        """A password shorter than 8 characters should be rejected."""
        payload = {
            "email": "shortpwd@example.com",
            "name": "Short Pwd",
            "password": "Ab1!",
        }
        response = client.post("/api/auth/register", json=payload)
        assert response.status_code == 400
        data = response.json()
        assert "detail" in data
        assert "8" in data["detail"]

    def test_register_weak_password_no_special_char(self, client):
        """A password without special characters should be rejected."""
        payload = {
            "email": "nospecial@example.com",
            "name": "No Special",
            "password": "NoSpecialChar123",
        }
        response = client.post("/api/auth/register", json=payload)
        assert response.status_code == 400
        data = response.json()
        assert "detail" in data

    def test_register_weak_password_no_digit(self, client):
        """A password without digits should be rejected."""
        payload = {
            "email": "nodigit@example.com",
            "name": "No Digit",
            "password": "NoDigitHere!",
        }
        response = client.post("/api/auth/register", json=payload)
        assert response.status_code == 400


class TestLoginErrors:
    """Error cases for POST /api/auth/login."""

    def test_login_wrong_password_returns_401(self, client, test_user):
        """Wrong password must return 401."""
        payload = {
            "email": test_user.email,
            "password": "WrongValue999!",
        }
        response = client.post("/api/auth/login", json=payload)
        assert response.status_code == 401
        data = response.json()
        assert "detail" in data

    def test_login_inactive_user_returns_403(self, client, db):
        """An inactive user must be rejected with 403."""
        user = User(
            email="inactive@example.com",
            full_name="Inactive User",
            hashed_password=hash_password(_TPW),
            plan="basic",
            is_active=False,
            is_admin=False,
        )
        db.add(user)
        db.commit()

        payload = {
            "email": "inactive@example.com",
            "password": _TPW,
        }
        response = client.post("/api/auth/login", json=payload)
        assert response.status_code == 403
        data = response.json()
        assert "detail" in data
        assert "désactivé" in data["detail"].lower() or "desactiv" in data["detail"].lower()

    def test_login_nonexistent_email_returns_401(self, client):
        """Login with non-existent email must return 401."""
        payload = {
            "email": "nobody@example.com",
            "password": _TPW,
        }
        response = client.post("/api/auth/login", json=payload)
        assert response.status_code == 401


class TestVerifyCodeErrors:
    """Error cases for POST /api/auth/verify-code."""

    def test_verify_code_invalid_returns_401(self, client, test_user, db):
        """An invalid verification code must be rejected."""
        code = VerificationCode(
            user_id=test_user.id,
            code="123456",
            expires_at=datetime.now(timezone.utc) + timedelta(minutes=10),
            is_used=False,
        )
        db.add(code)
        db.commit()

        payload = {
            "email": test_user.email,
            "code": "999999",
        }
        response = client.post("/api/auth/verify-code", json=payload)
        assert response.status_code == 401
        data = response.json()
        assert "detail" in data

    def test_verify_code_expired_returns_401(self, client, test_user, db):
        """An expired verification code must be rejected."""
        code = VerificationCode(
            user_id=test_user.id,
            code="654321",
            expires_at=datetime.now(timezone.utc) - timedelta(minutes=1),
            is_used=False,
        )
        db.add(code)
        db.commit()

        payload = {
            "email": test_user.email,
            "code": "654321",
        }
        response = client.post("/api/auth/verify-code", json=payload)
        assert response.status_code == 401
        data = response.json()
        assert "detail" in data

    def test_verify_code_already_used_returns_401(self, client, test_user, db):
        """A code that has already been used must be rejected."""
        code = VerificationCode(
            user_id=test_user.id,
            code="111111",
            expires_at=datetime.now(timezone.utc) + timedelta(minutes=10),
            is_used=True,
        )
        db.add(code)
        db.commit()

        payload = {
            "email": test_user.email,
            "code": "111111",
        }
        response = client.post("/api/auth/verify-code", json=payload)
        assert response.status_code == 401

    def test_verify_code_valid_returns_tokens(self, client, test_user, db):
        """A valid, non-expired code must return JWT tokens."""
        code = VerificationCode(
            user_id=test_user.id,
            code="777777",
            expires_at=datetime.now(timezone.utc) + timedelta(minutes=10),
            is_used=False,
        )
        db.add(code)
        db.commit()

        payload = {
            "email": test_user.email,
            "code": "777777",
        }
        response = client.post("/api/auth/verify-code", json=payload)
        assert response.status_code == 200
        data = response.json()
        assert "access_token" in data
        assert "refresh_token" in data
        assert data["token_type"] == "bearer"


class TestForgotPassword:
    """Tests for POST /api/auth/forgot-password."""

    def test_forgot_password_unknown_email_returns_200(self, client):
        """Unknown email must still return 200 to avoid leaking."""
        payload = {"email": "unknown@example.com"}
        response = client.post("/api/auth/forgot-password", json=payload)
        assert response.status_code == 200
        data = response.json()
        assert "message" in data

    def test_forgot_password_known_email_returns_200(self, client, test_user):
        """Known email returns 200 and sends reset email."""
        payload = {"email": test_user.email}
        response = client.post("/api/auth/forgot-password", json=payload)
        assert response.status_code == 200
        data = response.json()
        assert "message" in data

    def test_forgot_password_does_not_leak_email_existence(self, client, test_user):
        """Response must be identical for known and unknown emails."""
        known_response = client.post(
            "/api/auth/forgot-password",
            json={"email": test_user.email},
        )
        unknown_response = client.post(
            "/api/auth/forgot-password",
            json={"email": "nobody@example.com"},
        )
        assert known_response.status_code == 200
        assert unknown_response.status_code == 200
        assert known_response.json()["message"] == unknown_response.json()["message"]


class TestResetPassword:
    """Tests for POST /api/auth/reset-password."""

    def test_reset_password_invalid_token_returns_400(self, client):
        """An invalid/garbage token must return 400."""
        payload = {
            "token": "invalid-token-xyz",
            "new_password": _TPW,
        }
        response = client.post("/api/auth/reset-password", json=payload)
        assert response.status_code == 400
        data = response.json()
        assert "detail" in data

    def test_reset_password_non_reset_token_returns_400(self, client, test_user):
        """A regular access token (not a reset token) must be rejected."""
        access_token = create_access_token(data={"sub": test_user.email})
        payload = {
            "token": access_token,
            "new_password": _TPW,
        }
        response = client.post("/api/auth/reset-password", json=payload)
        assert response.status_code == 400
        data = response.json()
        assert "detail" in data

    def test_reset_password_with_valid_token_succeeds(self, client, test_user):
        """A valid reset token should allow password reset."""
        reset_token = create_access_token(
            data={"sub": test_user.email, "type": "reset"},
            expires_delta=timedelta(hours=1),
        )
        payload = {
            "token": reset_token,
            "new_password": _TPW,
        }
        response = client.post("/api/auth/reset-password", json=payload)
        assert response.status_code == 200
        data = response.json()
        assert "message" in data

    def test_reset_password_weak_new_password_returns_400(self, client, test_user):
        """Reset with a weak password should fail validation."""
        reset_token = create_access_token(
            data={"sub": test_user.email, "type": "reset"},
            expires_delta=timedelta(hours=1),
        )
        payload = {
            "token": reset_token,
            "new_password": "weak",
        }
        response = client.post("/api/auth/reset-password", json=payload)
        assert response.status_code == 400


class TestRefreshToken:
    """Tests for POST /api/auth/refresh."""

    def test_refresh_token_valid_returns_new_access_token(self, client, test_user):
        """A valid refresh token must return a new access token."""
        refresh_token = create_refresh_token(
            data={"sub": test_user.email, "user_id": test_user.id}
        )
        payload = {"refresh_token": refresh_token}
        response = client.post("/api/auth/refresh", json=payload)
        assert response.status_code == 200
        data = response.json()
        assert "access_token" in data
        assert data["token_type"] == "bearer"
        assert "expires_at" in data

    def test_refresh_token_invalid_returns_401(self, client):
        """A garbage refresh token must return 401."""
        payload = {"refresh_token": "invalid-refresh-token"}
        response = client.post("/api/auth/refresh", json=payload)
        assert response.status_code == 401

    def test_refresh_with_access_token_returns_401(self, client, test_user):
        """Using an access token instead of a refresh token must fail."""
        access_token = create_access_token(
            data={"sub": test_user.email, "user_id": test_user.id}
        )
        payload = {"refresh_token": access_token}
        response = client.post("/api/auth/refresh", json=payload)
        assert response.status_code == 401
        data = response.json()
        assert "detail" in data

    def test_refresh_token_inactive_user_returns_403(self, client, db):
        """Refresh token for an inactive user must be rejected."""
        user = User(
            email="inactive_refresh@example.com",
            full_name="Inactive Refresh",
            hashed_password=hash_password(_TPW),
            plan="basic",
            is_active=False,
            is_admin=False,
        )
        db.add(user)
        db.commit()
        db.refresh(user)

        refresh_token = create_refresh_token(
            data={"sub": user.email, "user_id": user.id}
        )
        payload = {"refresh_token": refresh_token}
        response = client.post("/api/auth/refresh", json=payload)
        assert response.status_code == 403


class TestLogout:
    """Tests for POST /api/auth/logout."""

    def test_logout_returns_success(self, client, test_user, auth_headers):
        """Logout must return a success message."""
        response = client.post("/api/auth/logout", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert "message" in data

    def test_logout_blacklists_token(self, client, test_user, auth_headers, db):
        """After logout, the token should be blacklisted and unusable."""
        response = client.post("/api/auth/logout", headers=auth_headers)
        assert response.status_code == 200

        me_response = client.get("/api/users/me", headers=auth_headers)
        assert me_response.status_code == 401

    def test_logout_without_token_returns_401(self, client):
        """Logout without a token must return 401."""
        response = client.post("/api/auth/logout")
        assert response.status_code == 401

    def test_logout_with_invalid_token_returns_401(self, client):
        """Logout with an invalid token must return 401."""
        headers = {"Authorization": "Bearer invalid-token-xyz"}
        response = client.post("/api/auth/logout", headers=headers)
        assert response.status_code == 401
