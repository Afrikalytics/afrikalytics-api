"""
Extended tests for admin endpoints — /api/admin/*

Covers flows not in test_admin.py:
- GET    /api/admin/users          — non-admin rejection
- POST   /api/admin/users          — create user with various payloads
- PUT    /api/admin/users/{id}     — update plan, role validation
- DELETE /api/admin/users/{id}     — soft delete behavior
- PUT    /api/admin/users/{id}/toggle-active — toggle states
- GET    /api/admin/audit-log      — audit log access
"""

import os

from app.auth import hash_password, create_access_token
from app.models import User

_TPW = os.environ.get("TEST_PASSWORD", "TestPass-Fixture-1!")


class TestAdminListUsersExtended:
    """Extended tests for GET /api/admin/users."""

    def test_non_admin_cannot_list_users_returns_403(self, client, auth_headers):
        """A regular (non-admin) user must get 403."""
        response = client.get("/api/admin/users", headers=auth_headers)
        assert response.status_code == 403
        data = response.json()
        assert "detail" in data

    def test_unauthenticated_cannot_list_users_returns_401(self, client):
        """No token must return 401."""
        response = client.get("/api/admin/users")
        assert response.status_code == 401

    def test_content_admin_cannot_list_users_returns_403(
        self, client, content_admin_auth_headers
    ):
        """admin_content role does not have 'users' permission."""
        response = client.get("/api/admin/users", headers=content_admin_auth_headers)
        assert response.status_code == 403


class TestCreateAdminUserExtended:
    """Extended tests for POST /api/admin/users."""

    def test_admin_create_user_with_admin_role(self, client, admin_auth_headers):
        """Super admin can create a user with an admin role."""
        payload = {
            "email": "newadmin_ext@example.com",
            "full_name": "New Admin Extended",
            "plan": "entreprise",
            "is_active": True,
            "is_admin": True,
            "admin_role": "admin_studies",
        }
        response = client.post(
            "/api/admin/users",
            json=payload,
            headers=admin_auth_headers,
        )
        assert response.status_code == 201
        data = response.json()
        assert data["is_admin"] is True
        assert data["admin_role"] == "admin_studies"

    def test_admin_create_user_invalid_role_returns_400(self, client, admin_auth_headers):
        """Creating a user with an invalid admin role must fail."""
        payload = {
            "email": "badrole@example.com",
            "full_name": "Bad Role",
            "plan": "basic",
            "is_active": True,
            "is_admin": True,
            "admin_role": "role_inexistant",
        }
        response = client.post(
            "/api/admin/users",
            json=payload,
            headers=admin_auth_headers,
        )
        assert response.status_code == 400

    def test_admin_create_user_duplicate_email_returns_400(
        self, client, test_user, admin_auth_headers
    ):
        """Cannot create a user with an already-used email."""
        payload = {
            "email": test_user.email,
            "full_name": "Duplicate",
            "plan": "basic",
            "is_active": True,
            "is_admin": False,
        }
        response = client.post(
            "/api/admin/users",
            json=payload,
            headers=admin_auth_headers,
        )
        assert response.status_code == 400


class TestUpdateAdminUserExtended:
    """Extended tests for PUT /api/admin/users/{id}."""

    def test_admin_update_user_plan_to_professionnel(
        self, client, test_user, admin_auth_headers
    ):
        """Admin can upgrade a user's plan."""
        payload = {"plan": "professionnel"}
        response = client.put(
            f"/api/admin/users/{test_user.id}",
            json=payload,
            headers=admin_auth_headers,
        )
        assert response.status_code == 200
        data = response.json()
        assert data["plan"] == "professionnel"

    def test_admin_update_user_plan_to_entreprise(
        self, client, test_user, admin_auth_headers
    ):
        """Admin can set plan to entreprise."""
        payload = {"plan": "entreprise"}
        response = client.put(
            f"/api/admin/users/{test_user.id}",
            json=payload,
            headers=admin_auth_headers,
        )
        assert response.status_code == 200
        assert response.json()["plan"] == "entreprise"

    def test_admin_update_user_full_name(
        self, client, test_user, admin_auth_headers
    ):
        """Admin can update a user's full name."""
        payload = {"full_name": "Nom Mis a Jour"}
        response = client.put(
            f"/api/admin/users/{test_user.id}",
            json=payload,
            headers=admin_auth_headers,
        )
        assert response.status_code == 200
        assert response.json()["full_name"] == "Nom Mis a Jour"

    def test_admin_update_user_invalid_admin_role_returns_400(
        self, client, test_user, admin_auth_headers
    ):
        """Setting an invalid admin role must return 400."""
        payload = {"admin_role": "nonexistent_role"}
        response = client.put(
            f"/api/admin/users/{test_user.id}",
            json=payload,
            headers=admin_auth_headers,
        )
        assert response.status_code == 400

    def test_admin_update_nonexistent_user_returns_404(self, client, admin_auth_headers):
        """Updating a non-existent user must return 404."""
        payload = {"full_name": "Ghost"}
        response = client.put(
            "/api/admin/users/99999",
            json=payload,
            headers=admin_auth_headers,
        )
        assert response.status_code == 404

    def test_non_admin_cannot_update_returns_403(
        self, client, test_user, auth_headers
    ):
        """A regular user cannot update another user."""
        payload = {"full_name": "Hacker"}
        response = client.put(
            f"/api/admin/users/{test_user.id}",
            json=payload,
            headers=auth_headers,
        )
        assert response.status_code == 403


class TestDeleteAdminUserExtended:
    """Extended tests for DELETE /api/admin/users/{id}."""

    def test_admin_delete_user_removes_from_db(
        self, client, db, admin_auth_headers
    ):
        """After deletion, the user should no longer appear in admin user list."""
        # Create a user to delete
        target = User(
            email="todelete@example.com",
            full_name="To Delete",
            hashed_password=hash_password(_TPW),
            plan="basic",
            is_active=True,
        )
        db.add(target)
        db.commit()
        db.refresh(target)

        response = client.delete(
            f"/api/admin/users/{target.id}",
            headers=admin_auth_headers,
        )
        assert response.status_code == 200
        assert "supprim" in response.json()["message"].lower()

        # Verify user is gone
        db.expire_all()
        deleted = db.query(User).filter(User.id == target.id).first()
        assert deleted is None

    def test_admin_cannot_delete_self_returns_400(
        self, client, admin_user, admin_auth_headers
    ):
        """Admin cannot delete their own account."""
        response = client.delete(
            f"/api/admin/users/{admin_user.id}",
            headers=admin_auth_headers,
        )
        assert response.status_code == 400

    def test_non_admin_cannot_delete_returns_403(
        self, client, test_user, auth_headers
    ):
        """Regular users cannot delete any user."""
        response = client.delete(
            f"/api/admin/users/{test_user.id}",
            headers=auth_headers,
        )
        assert response.status_code == 403


class TestToggleActiveExtended:
    """Extended tests for PUT /api/admin/users/{id}/toggle-active."""

    def test_toggle_deactivates_active_user(
        self, client, test_user, admin_auth_headers
    ):
        """Toggling an active user deactivates them."""
        response = client.put(
            f"/api/admin/users/{test_user.id}/toggle-active",
            headers=admin_auth_headers,
        )
        assert response.status_code == 200
        assert response.json()["is_active"] is False

    def test_toggle_activates_inactive_user(
        self, client, db, admin_auth_headers
    ):
        """Toggling an inactive user activates them."""
        user = User(
            email="toggleme@example.com",
            full_name="Toggle Me",
            hashed_password=hash_password(_TPW),
            plan="basic",
            is_active=False,
        )
        db.add(user)
        db.commit()
        db.refresh(user)

        response = client.put(
            f"/api/admin/users/{user.id}/toggle-active",
            headers=admin_auth_headers,
        )
        assert response.status_code == 200
        assert response.json()["is_active"] is True

    def test_toggle_nonexistent_returns_404(self, client, admin_auth_headers):
        """Toggling a non-existent user must return 404."""
        response = client.put(
            "/api/admin/users/99999/toggle-active",
            headers=admin_auth_headers,
        )
        assert response.status_code == 404

    def test_non_admin_toggle_returns_403(self, client, test_user, auth_headers):
        """Regular user cannot toggle any user."""
        response = client.put(
            f"/api/admin/users/{test_user.id}/toggle-active",
            headers=auth_headers,
        )
        assert response.status_code == 403


class TestAuditLog:
    """Tests for GET /api/admin/audit-log."""

    def test_super_admin_can_access_audit_log(self, client, admin_auth_headers):
        """Super admin can access audit logs."""
        response = client.get("/api/admin/audit-log", headers=admin_auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert "items" in data
        assert "total" in data
        assert isinstance(data["items"], list)

    def test_regular_user_cannot_access_audit_log_returns_403(
        self, client, auth_headers
    ):
        """Regular users cannot access audit logs."""
        response = client.get("/api/admin/audit-log", headers=auth_headers)
        assert response.status_code == 403

    def test_content_admin_cannot_access_audit_log_returns_403(
        self, client, content_admin_auth_headers
    ):
        """Content admin (no 'users' permission) cannot access audit logs."""
        response = client.get("/api/admin/audit-log", headers=content_admin_auth_headers)
        assert response.status_code == 403

    def test_unauthenticated_cannot_access_audit_log_returns_401(self, client):
        """No token must return 401."""
        response = client.get("/api/admin/audit-log")
        assert response.status_code == 401

    def test_audit_log_records_user_creation(
        self, client, admin_auth_headers
    ):
        """Creating a user should generate an audit log entry."""
        # Create a user to trigger audit log
        payload = {
            "email": "auditlogtest@example.com",
            "full_name": "Audit Test",
            "plan": "basic",
            "is_active": True,
            "is_admin": False,
        }
        create_response = client.post(
            "/api/admin/users",
            json=payload,
            headers=admin_auth_headers,
        )
        assert create_response.status_code == 201

        # Check audit log
        response = client.get(
            "/api/admin/audit-log?action=create&resource_type=user",
            headers=admin_auth_headers,
        )
        assert response.status_code == 200
        data = response.json()
        assert data["total"] >= 1
        # The latest entry should be about the user we just created
        actions = [item["action"] for item in data["items"]]
        assert "create" in actions
