"""
Tests for SSO authentication endpoints — /api/auth/sso/*

Covers:
- GET  /api/auth/sso/google          — Google auth URL generation
- GET  /api/auth/sso/google/callback  — Google OAuth2 callback
- GET  /api/auth/sso/microsoft        — Microsoft auth URL generation
- GET  /api/auth/sso/microsoft/callback — Microsoft OAuth2 callback
- POST /api/auth/sso/exchange         — Exchange SSO code for JWT

TDD RED phase: these tests define the SSO contract.
All external HTTP calls (Google, Microsoft APIs) are mocked.
"""
import os
import secrets
from datetime import datetime, timedelta, timezone
from unittest.mock import patch, AsyncMock, MagicMock

import pytest

from app.auth import hash_password, create_access_token
from app.models import User, SSOExchangeCode


_TPW = os.environ.get("TEST_PASSWORD", "TestPass-Fixture-1!")


# ================================================================
# SSO Google — Login URL
# ================================================================

class TestSSOGoogleLogin:
    """Tests for GET /api/auth/sso/google."""

    @patch("app.routers.auth.get_settings")
    @patch("app.routers.auth.get_google_auth_url", new_callable=AsyncMock)
    def test_google_login_returns_auth_url(self, mock_auth_url, mock_settings, client):
        """Should return a Google OAuth2 authorization URL."""
        mock_settings.return_value = MagicMock(
            google_client_id="test-client-id",
            google_client_secret="test-secret",
            api_url="https://api.test.com",
            secret_key="test-key",
        )
        mock_auth_url.return_value = "https://accounts.google.com/o/oauth2/auth?..."

        response = client.get("/api/auth/sso/google")
        assert response.status_code == 200
        data = response.json()
        assert "auth_url" in data
        assert data["provider"] == "google"

    @patch("app.routers.auth.get_settings")
    def test_google_login_not_configured_returns_501(self, mock_settings, client):
        """If Google OAuth is not configured, return 501."""
        mock_settings.return_value = MagicMock(
            google_client_id="",
            google_client_secret="",
        )

        response = client.get("/api/auth/sso/google")
        assert response.status_code == 501


# ================================================================
# SSO Microsoft — Login URL
# ================================================================

class TestSSOMicrosoftLogin:
    """Tests for GET /api/auth/sso/microsoft."""

    @patch("app.routers.auth.get_settings")
    @patch("app.routers.auth.get_microsoft_auth_url", new_callable=AsyncMock)
    def test_microsoft_login_returns_auth_url(self, mock_auth_url, mock_settings, client):
        """Should return a Microsoft OAuth2 authorization URL."""
        mock_settings.return_value = MagicMock(
            microsoft_client_id="test-client-id",
            microsoft_client_secret="test-secret",
            microsoft_tenant_id="common",
            api_url="https://api.test.com",
            secret_key="test-key",
        )
        mock_auth_url.return_value = "https://login.microsoftonline.com/common/oauth2/v2.0/authorize?..."

        response = client.get("/api/auth/sso/microsoft")
        assert response.status_code == 200
        data = response.json()
        assert "auth_url" in data
        assert data["provider"] == "microsoft"

    @patch("app.routers.auth.get_settings")
    def test_microsoft_login_not_configured_returns_501(self, mock_settings, client):
        """If Microsoft OAuth is not configured, return 501."""
        mock_settings.return_value = MagicMock(
            microsoft_client_id="",
            microsoft_client_secret="",
        )

        response = client.get("/api/auth/sso/microsoft")
        assert response.status_code == 501


# ================================================================
# SSO Exchange Code
# ================================================================

class TestSSOExchange:
    """Tests for POST /api/auth/sso/exchange."""

    def test_valid_code_returns_jwt(self, client, test_user, db):
        """A valid, unused, non-expired SSO code should return a JWT."""
        access_token = create_access_token(
            data={"sub": test_user.email, "user_id": test_user.id}
        )
        code = secrets.token_urlsafe(32)
        exchange = SSOExchangeCode(
            code=code,
            user_id=test_user.id,
            access_token=access_token,
            expires_at=datetime.now(timezone.utc) + timedelta(seconds=60),
        )
        db.add(exchange)
        db.commit()

        response = client.post(
            "/api/auth/sso/exchange",
            json={"sso_code": code},
        )
        assert response.status_code == 200
        data = response.json()
        assert "access_token" in data
        assert data["token_type"] == "bearer"
        assert "user" in data

    def test_used_code_returns_400(self, client, test_user, db):
        """An already-used SSO code should be rejected."""
        access_token = create_access_token(
            data={"sub": test_user.email, "user_id": test_user.id}
        )
        code = secrets.token_urlsafe(32)
        exchange = SSOExchangeCode(
            code=code,
            user_id=test_user.id,
            access_token=access_token,
            expires_at=datetime.now(timezone.utc) + timedelta(seconds=60),
            is_used=True,
        )
        db.add(exchange)
        db.commit()

        response = client.post(
            "/api/auth/sso/exchange",
            json={"sso_code": code},
        )
        assert response.status_code == 400

    def test_expired_code_returns_400(self, client, test_user, db):
        """An expired SSO code should be rejected."""
        access_token = create_access_token(
            data={"sub": test_user.email, "user_id": test_user.id}
        )
        code = secrets.token_urlsafe(32)
        exchange = SSOExchangeCode(
            code=code,
            user_id=test_user.id,
            access_token=access_token,
            expires_at=datetime.now(timezone.utc) - timedelta(seconds=10),
        )
        db.add(exchange)
        db.commit()

        response = client.post(
            "/api/auth/sso/exchange",
            json={"sso_code": code},
        )
        assert response.status_code == 400

    def test_nonexistent_code_returns_400(self, client):
        """A code that doesn't exist should return 400 (no oracle)."""
        fake_code = secrets.token_urlsafe(32)
        response = client.post(
            "/api/auth/sso/exchange",
            json={"sso_code": fake_code},
        )
        assert response.status_code == 400

    def test_code_is_single_use(self, client, test_user, db):
        """After first use, the same code must be rejected."""
        access_token = create_access_token(
            data={"sub": test_user.email, "user_id": test_user.id}
        )
        code = secrets.token_urlsafe(32)
        exchange = SSOExchangeCode(
            code=code,
            user_id=test_user.id,
            access_token=access_token,
            expires_at=datetime.now(timezone.utc) + timedelta(seconds=60),
        )
        db.add(exchange)
        db.commit()

        # First use
        r1 = client.post("/api/auth/sso/exchange", json={"sso_code": code})
        assert r1.status_code == 200

        # Second use
        r2 = client.post("/api/auth/sso/exchange", json={"sso_code": code})
        assert r2.status_code == 400

    def test_exchange_inactive_user_returns_403(self, client, db):
        """Exchange for an inactive user should return 403."""
        user = User(
            email="sso_inactive@example.com",
            full_name="SSO Inactive",
            hashed_password="",
            plan="basic",
            is_active=False,
            is_admin=False,
            sso_provider="google",
        )
        db.add(user)
        db.commit()
        db.refresh(user)

        access_token = create_access_token(
            data={"sub": user.email, "user_id": user.id}
        )
        code = secrets.token_urlsafe(32)
        exchange = SSOExchangeCode(
            code=code,
            user_id=user.id,
            access_token=access_token,
            expires_at=datetime.now(timezone.utc) + timedelta(seconds=60),
        )
        db.add(exchange)
        db.commit()

        response = client.post(
            "/api/auth/sso/exchange",
            json={"sso_code": code},
        )
        assert response.status_code == 403

    def test_exchange_code_too_short_returns_422(self, client):
        """A code shorter than min_length should fail validation."""
        response = client.post(
            "/api/auth/sso/exchange",
            json={"sso_code": "short"},
        )
        assert response.status_code == 422
