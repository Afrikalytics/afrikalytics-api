"""
Tests for the enterprise team management endpoints — /api/enterprise/*
Covers: team list, add member, remove member.
"""
import pytest
from app.models import User, Subscription
from app.auth import hash_password, create_access_token
from datetime import datetime, timedelta, timezone


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def enterprise_owner(db):
    """Create an enterprise owner (parent_user_id=None)."""
    user = User(
        email="owner@enterprise.com",
        full_name="Enterprise Owner",
        hashed_password=hash_password("OwnerPass123!"),
        plan="entreprise",
        is_active=True,
        is_admin=False,
        parent_user_id=None,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


@pytest.fixture()
def owner_auth_headers(enterprise_owner):
    token = create_access_token(data={"sub": enterprise_owner.email})
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture()
def team_member(db, enterprise_owner):
    """Create a team member under enterprise_owner."""
    user = User(
        email="member@enterprise.com",
        full_name="Team Member",
        hashed_password=hash_password("MemberPass123!"),
        plan="entreprise",
        is_active=True,
        is_admin=False,
        parent_user_id=enterprise_owner.id,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


@pytest.fixture()
def member_auth_headers(team_member):
    token = create_access_token(data={"sub": team_member.email})
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture()
def basic_user(db):
    """Create a basic plan user (for conversion tests)."""
    user = User(
        email="basic_convert@example.com",
        full_name="Basic Convert User",
        hashed_password=hash_password("BasicPass123!"),
        plan="basic",
        is_active=True,
        is_admin=False,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


@pytest.fixture()
def pro_user_with_sub(db):
    """Create a professionnel user with active subscription (for conversion tests)."""
    user = User(
        email="pro_convert@example.com",
        full_name="Pro Convert User",
        hashed_password=hash_password("ProPass123!"),
        plan="professionnel",
        is_active=True,
        is_admin=False,
    )
    db.add(user)
    db.flush()

    now = datetime.now(timezone.utc)
    sub = Subscription(
        user_id=user.id,
        plan="professionnel",
        status="active",
        start_date=now,
        end_date=now + timedelta(days=30),
    )
    db.add(sub)
    db.commit()
    db.refresh(user)
    return user


# ---------------------------------------------------------------------------
# GET /api/enterprise/team
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestGetTeam:
    def test_get_team_owner(self, client, owner_auth_headers, team_member):
        resp = client.get("/api/enterprise/team", headers=owner_auth_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["owner"]["email"] == "owner@enterprise.com"
        assert len(data["team_members"]) == 1
        assert data["team_members"][0]["email"] == "member@enterprise.com"
        assert data["max_members"] == 5
        assert data["current_count"] == 2  # owner + 1 member

    def test_get_team_empty(self, client, owner_auth_headers):
        resp = client.get("/api/enterprise/team", headers=owner_auth_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["team_members"]) == 0
        assert data["current_count"] == 1  # just the owner

    def test_get_team_basic_user_forbidden(self, client, auth_headers):
        """Basic plan users cannot access enterprise team."""
        resp = client.get("/api/enterprise/team", headers=auth_headers)
        assert resp.status_code == 403

    def test_get_team_member_forbidden(self, client, member_auth_headers):
        """Team members (non-owners) cannot manage the team."""
        resp = client.get("/api/enterprise/team", headers=member_auth_headers)
        assert resp.status_code == 403

    def test_get_team_unauthorized(self, client):
        resp = client.get("/api/enterprise/team")
        assert resp.status_code == 401


# ---------------------------------------------------------------------------
# POST /api/enterprise/team/add
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestAddTeamMember:
    def test_add_new_member(self, client, owner_auth_headers):
        resp = client.post(
            "/api/enterprise/team/add",
            json={"email": "new_member@example.com", "full_name": "New Member"},
            headers=owner_auth_headers,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["new_account"] is True
        assert data["member"]["email"] == "new_member@example.com"

    def test_add_existing_basic_user(self, client, owner_auth_headers, basic_user):
        """Adding an existing basic user converts them to entreprise."""
        resp = client.post(
            "/api/enterprise/team/add",
            json={"email": basic_user.email, "full_name": basic_user.full_name},
            headers=owner_auth_headers,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["converted_from"] == "basic"

    def test_add_existing_pro_user(self, client, owner_auth_headers, pro_user_with_sub):
        """Adding a pro user converts them and cancels their subscription."""
        resp = client.post(
            "/api/enterprise/team/add",
            json={"email": pro_user_with_sub.email, "full_name": pro_user_with_sub.full_name},
            headers=owner_auth_headers,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["converted_from"] == "professionnel"

    def test_add_existing_enterprise_owner(self, client, db, owner_auth_headers):
        """Cannot add someone who is already an enterprise owner."""
        other_owner = User(
            email="other_owner@enterprise.com",
            full_name="Other Owner",
            hashed_password=hash_password("OtherPass123!"),
            plan="entreprise",
            is_active=True,
            parent_user_id=None,
        )
        db.add(other_owner)
        db.commit()

        resp = client.post(
            "/api/enterprise/team/add",
            json={"email": other_owner.email, "full_name": other_owner.full_name},
            headers=owner_auth_headers,
        )
        assert resp.status_code == 400
        assert "propriétaire" in resp.json()["detail"].lower() or "proprietaire" in resp.json()["detail"].lower()

    def test_add_existing_enterprise_member(self, client, owner_auth_headers, team_member):
        """Cannot add someone who is already in an enterprise team."""
        resp = client.post(
            "/api/enterprise/team/add",
            json={"email": team_member.email, "full_name": team_member.full_name},
            headers=owner_auth_headers,
        )
        assert resp.status_code == 400

    def test_add_max_members_reached(self, client, db, enterprise_owner, owner_auth_headers):
        """Cannot add more than 4 members (+ owner = 5 total)."""
        for i in range(4):
            db.add(User(
                email=f"fill_{i}@enterprise.com",
                full_name=f"Fill {i}",
                hashed_password=hash_password("Pass123!"),
                plan="entreprise",
                is_active=True,
                parent_user_id=enterprise_owner.id,
            ))
        db.commit()

        resp = client.post(
            "/api/enterprise/team/add",
            json={"email": "fifth@example.com", "full_name": "Fifth Member"},
            headers=owner_auth_headers,
        )
        assert resp.status_code == 400
        assert "Limite" in resp.json()["detail"]

    def test_add_basic_user_forbidden(self, client, auth_headers):
        resp = client.post(
            "/api/enterprise/team/add",
            json={"email": "test@test.com", "full_name": "Test"},
            headers=auth_headers,
        )
        assert resp.status_code == 403

    def test_add_member_not_owner(self, client, member_auth_headers):
        """Team members cannot add other members."""
        resp = client.post(
            "/api/enterprise/team/add",
            json={"email": "test@test.com", "full_name": "Test"},
            headers=member_auth_headers,
        )
        assert resp.status_code == 403


# ---------------------------------------------------------------------------
# DELETE /api/enterprise/team/{member_id}
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestRemoveTeamMember:
    def test_remove_member(self, client, owner_auth_headers, team_member):
        resp = client.delete(
            f"/api/enterprise/team/{team_member.id}",
            headers=owner_auth_headers,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["new_plan"] == "basic"
        assert data["member_id"] == team_member.id

    def test_remove_not_found(self, client, owner_auth_headers):
        resp = client.delete("/api/enterprise/team/99999", headers=owner_auth_headers)
        assert resp.status_code == 404

    def test_remove_not_in_my_team(self, client, db, owner_auth_headers):
        """Cannot remove a member from another team."""
        other_owner = User(
            email="other2@enterprise.com",
            full_name="Other2",
            hashed_password=hash_password("Pass123!"),
            plan="entreprise",
            is_active=True,
            parent_user_id=None,
        )
        db.add(other_owner)
        db.flush()
        other_member = User(
            email="other_member2@enterprise.com",
            full_name="Other Member2",
            hashed_password=hash_password("Pass123!"),
            plan="entreprise",
            is_active=True,
            parent_user_id=other_owner.id,
        )
        db.add(other_member)
        db.commit()

        resp = client.delete(
            f"/api/enterprise/team/{other_member.id}",
            headers=owner_auth_headers,
        )
        assert resp.status_code == 404

    def test_remove_basic_user_forbidden(self, client, auth_headers, team_member):
        resp = client.delete(
            f"/api/enterprise/team/{team_member.id}",
            headers=auth_headers,
        )
        assert resp.status_code == 403

    def test_remove_member_not_owner(self, client, member_auth_headers, team_member):
        resp = client.delete(
            f"/api/enterprise/team/{team_member.id}",
            headers=member_auth_headers,
        )
        assert resp.status_code == 403
