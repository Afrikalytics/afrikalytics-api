"""
Extended tests for user endpoints — /api/users/* and /api/enterprise/*

Covers flows not in test_users.py:
- GET  /api/users/me           — unauthorized access
- PUT  /api/users/change-password — wrong current password, success with re-login
- GET  /api/users/quota        — per-plan limits (basic, entreprise)
- GET  /api/enterprise/team    — enterprise team management
- POST /api/enterprise/team/add — adding team members
- DELETE /api/enterprise/team/{id} — removing team members
"""

import os

from app.auth import hash_password, create_access_token
from app.models import User

_TPW = os.environ.get("_TPW", "TestPass-Fixture-1!")


class TestGetMeExtended:
    """Extended tests for GET /api/users/me."""

    def test_get_me_unauthorized_no_header(self, client):
        """Request without Authorization header must return 401."""
        response = client.get("/api/users/me")
        assert response.status_code == 401

    def test_get_me_with_expired_token(self, client, test_user):
        """An expired token must return 401."""
        from datetime import timedelta
        expired_token = create_access_token(
            data={"sub": test_user.email},
            expires_delta=timedelta(seconds=-1),
        )
        headers = {"Authorization": f"Bearer {expired_token}"}
        response = client.get("/api/users/me", headers=headers)
        assert response.status_code == 401

    def test_get_me_with_malformed_bearer(self, client):
        """A malformed Authorization header must return 401."""
        headers = {"Authorization": "NotBearer some-token"}
        response = client.get("/api/users/me", headers=headers)
        assert response.status_code == 401


class TestChangePasswordExtended:
    """Extended tests for PUT /api/users/change-password."""

    def test_change_password_wrong_current_returns_400(self, client, auth_headers):
        """Wrong current password must be rejected."""
        payload = {
            "current_password": _TPW,
            "new_password": _TPW,
        }
        response = client.put(
            "/api/users/change-password",
            json=payload,
            headers=auth_headers,
        )
        assert response.status_code == 400
        data = response.json()
        assert "detail" in data

    def test_change_password_success_returns_200(self, client, auth_headers):
        """Valid password change must succeed."""
        payload = {
            "current_password": _TPW,
            "new_password": _TPW,
        }
        response = client.put(
            "/api/users/change-password",
            json=payload,
            headers=auth_headers,
        )
        assert response.status_code == 200
        data = response.json()
        assert "message" in data

    def test_change_password_then_login_with_new_password(self, client, test_user, auth_headers):
        """After changing password, login must work with the new password."""
        new_password = _TPW
        payload = {
            "current_password": _TPW,
            "new_password": new_password,
        }
        response = client.put(
            "/api/users/change-password",
            json=payload,
            headers=auth_headers,
        )
        assert response.status_code == 200

        # Login with new password
        login_response = client.post(
            "/api/auth/login",
            json={"email": test_user.email, "password": new_password},
        )
        assert login_response.status_code == 200

    def test_change_password_then_old_password_fails(self, client, test_user, auth_headers):
        """After changing password, login with old password must fail."""
        payload = {
            "current_password": _TPW,
            "new_password": _TPW,
        }
        client.put(
            "/api/users/change-password",
            json=payload,
            headers=auth_headers,
        )

        # Login with old password should fail
        login_response = client.post(
            "/api/auth/login",
            json={"email": test_user.email, "password": _TPW},
        )
        assert login_response.status_code == 401

    def test_change_password_weak_new_password_returns_400(self, client, auth_headers):
        """A weak new password should be rejected."""
        payload = {
            "current_password": _TPW,
            "new_password": "short",
        }
        response = client.put(
            "/api/users/change-password",
            json=payload,
            headers=auth_headers,
        )
        assert response.status_code == 400


class TestGetQuotaExtended:
    """Extended tests for GET /api/users/quota."""

    def test_get_quota_basic_plan_has_limited_access(self, client, auth_headers):
        """Basic plan must have limited tokens."""
        response = client.get("/api/users/quota", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert data["plan"] == "basic"
        tokens_by_name = {t["name"]: t for t in data["tokens"]}

        # Basic plan has limited reports_downloads
        assert tokens_by_name["reports_downloads"]["limit"] == 3
        assert tokens_by_name["reports_downloads"]["unlimited"] is False

        # Basic plan has limited insights_access
        assert tokens_by_name["insights_access"]["limit"] == 5
        assert tokens_by_name["insights_access"]["unlimited"] is False

    def test_get_quota_enterprise_plan_all_unlimited(
        self, client, enterprise_user, enterprise_auth_headers
    ):
        """Enterprise plan must have all unlimited tokens."""
        response = client.get("/api/users/quota", headers=enterprise_auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert data["plan"] == "entreprise"

        for token in data["tokens"]:
            assert token["unlimited"] is True, (
                f"Token '{token['name']}' should be unlimited for entreprise plan"
            )
            assert token["limit"] == -1

    def test_get_quota_unauthorized_returns_401(self, client):
        """Quota without auth must return 401."""
        response = client.get("/api/users/quota")
        assert response.status_code == 401


class TestEnterpriseTeam:
    """Tests for enterprise team endpoints."""

    def test_get_team_non_enterprise_returns_403(self, client, auth_headers):
        """A basic user cannot access enterprise team features."""
        response = client.get("/api/enterprise/team", headers=auth_headers)
        assert response.status_code == 403

    def test_get_team_enterprise_owner_succeeds(
        self, client, enterprise_user, enterprise_auth_headers
    ):
        """An enterprise owner (no parent_user_id) can list their team."""
        response = client.get("/api/enterprise/team", headers=enterprise_auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert "owner" in data
        assert "team_members" in data
        assert "max_members" in data
        assert data["max_members"] == 5
        assert data["owner"]["email"] == enterprise_user.email

    def test_get_team_enterprise_member_returns_403(self, client, db):
        """An enterprise team member (with parent_user_id) cannot manage the team."""
        # Create owner
        owner = User(
            email="owner@enterprise.com",
            full_name="Enterprise Owner",
            hashed_password=hash_password(_TPW),
            plan="entreprise",
            is_active=True,
            is_admin=False,
        )
        db.add(owner)
        db.commit()
        db.refresh(owner)

        # Create team member with parent
        member = User(
            email="member@enterprise.com",
            full_name="Team Member",
            hashed_password=hash_password(_TPW),
            plan="entreprise",
            is_active=True,
            is_admin=False,
            parent_user_id=owner.id,
        )
        db.add(member)
        db.commit()

        member_token = create_access_token(data={"sub": member.email})
        member_headers = {"Authorization": f"Bearer {member_token}"}

        response = client.get("/api/enterprise/team", headers=member_headers)
        assert response.status_code == 403

    def test_add_team_member_new_account(
        self, client, enterprise_user, enterprise_auth_headers
    ):
        """Enterprise owner can add a new team member (creates account)."""
        payload = {
            "email": "newmember@example.com",
            "full_name": "New Team Member",
        }
        response = client.post(
            "/api/enterprise/team/add",
            json=payload,
            headers=enterprise_auth_headers,
        )
        assert response.status_code == 200
        data = response.json()
        assert "member" in data
        assert data["member"]["email"] == "newmember@example.com"

    def test_add_team_member_basic_user_returns_403(self, client, auth_headers):
        """A basic user cannot add team members."""
        payload = {
            "email": "someone@example.com",
            "full_name": "Someone",
        }
        response = client.post(
            "/api/enterprise/team/add",
            json=payload,
            headers=auth_headers,
        )
        assert response.status_code == 403

    def test_add_team_member_max_limit(
        self, client, db, enterprise_user, enterprise_auth_headers
    ):
        """Cannot exceed 5 total team members (owner + 4 members)."""
        # Create 4 team members directly in DB
        for i in range(4):
            member = User(
                email=f"member{i}@enterprise.com",
                full_name=f"Member {i}",
                hashed_password=hash_password(_TPW),
                plan="entreprise",
                is_active=True,
                parent_user_id=enterprise_user.id,
            )
            db.add(member)
        db.commit()

        # Try to add a 5th member
        payload = {
            "email": "overflow@example.com",
            "full_name": "Overflow Member",
        }
        response = client.post(
            "/api/enterprise/team/add",
            json=payload,
            headers=enterprise_auth_headers,
        )
        assert response.status_code == 400
        assert "limite" in response.json()["detail"].lower()

    def test_remove_team_member_downgrades_to_basic(
        self, client, db, enterprise_user, enterprise_auth_headers
    ):
        """Removing a team member should downgrade them to basic plan."""
        member = User(
            email="toremove@enterprise.com",
            full_name="To Remove",
            hashed_password=hash_password(_TPW),
            plan="entreprise",
            is_active=True,
            parent_user_id=enterprise_user.id,
        )
        db.add(member)
        db.commit()
        db.refresh(member)

        response = client.delete(
            f"/api/enterprise/team/{member.id}",
            headers=enterprise_auth_headers,
        )
        assert response.status_code == 200
        data = response.json()
        assert data["new_plan"] == "basic"

        # Verify in DB
        db.expire_all()
        updated = db.query(User).filter(User.id == member.id).first()
        assert updated.plan == "basic"
        assert updated.parent_user_id is None

    def test_remove_nonexistent_member_returns_404(
        self, client, enterprise_auth_headers
    ):
        """Removing a non-existent member must return 404."""
        response = client.delete(
            "/api/enterprise/team/99999",
            headers=enterprise_auth_headers,
        )
        assert response.status_code == 404
