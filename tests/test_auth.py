"""
Tests for authentication endpoints — /api/auth/*

Covers:
- POST /api/auth/register  — user registration
- POST /api/auth/login     — user login (step 1, sends 2FA code)
- GET  /                   — root endpoint (smoke test)
- GET  /health             — health check
"""


class TestRootEndpoints:
    """Smoke tests for root-level endpoints."""

    def test_root(self, client):
        response = client.get("/")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "online"
        assert "version" in data

    def test_health(self, client):
        response = client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"


class TestRegister:
    """Tests for POST /api/auth/register."""

    def test_register_success(self, client):
        payload = {
            "email": "newuser@example.com",
            "full_name": "New User",
            "password": "StrongPassword123!",
        }
        response = client.post("/api/auth/register", json=payload)
        # Should succeed (200 or 201) and return a token or user info
        assert response.status_code in (200, 201)
        data = response.json()
        assert "access_token" in data or "user" in data or "message" in data

    def test_register_duplicate_email(self, client, test_user):
        payload = {
            "email": test_user.email,
            "full_name": "Duplicate User",
            "password": "StrongPassword123!",
        }
        response = client.post("/api/auth/register", json=payload)
        assert response.status_code == 400

    def test_register_missing_fields(self, client):
        payload = {"email": "incomplete@example.com"}
        response = client.post("/api/auth/register", json=payload)
        assert response.status_code == 422


class TestLogin:
    """Tests for POST /api/auth/login."""

    def test_login_success(self, client, test_user):
        payload = {
            "email": test_user.email,
            "password": "TestPassword123!",
        }
        response = client.post("/api/auth/login", json=payload)
        # Login step 1 may return 200 with requires_verification or access_token
        assert response.status_code == 200
        data = response.json()
        assert (
            "access_token" in data
            or "requires_verification" in data
            or "message" in data
        )

    def test_login_wrong_password(self, client, test_user):
        payload = {
            "email": test_user.email,
            "password": "WrongPassword!",
        }
        response = client.post("/api/auth/login", json=payload)
        assert response.status_code in (400, 401)

    def test_login_nonexistent_user(self, client):
        payload = {
            "email": "ghost@example.com",
            "password": "NoOneHere123!",
        }
        response = client.post("/api/auth/login", json=payload)
        assert response.status_code in (400, 401, 404)
