"""
Tests RBAC (Role-Based Access Control) cross-role.

Verifie que chaque role admin n'a acces qu'aux ressources autorisees,
que les utilisateurs non-admin sont bloques, et que les tokens
invalides/expires/blacklistes sont rejetes.
"""
import jwt
from datetime import datetime, timedelta, timezone

from app.auth import create_access_token, hash_password, SECRET_KEY, ALGORITHM
from app.models import User, Study, TokenBlacklist


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

STUDY_PAYLOAD = {
    "title": "Etude RBAC Test",
    "description": "Description pour test RBAC.",
    "category": "Finance",
}

INSIGHT_PAYLOAD = {
    "study_id": 1,  # will be overridden per test
    "title": "Insight RBAC Test",
    "summary": "Resume pour test RBAC.",
}

REPORT_PAYLOAD = {
    "study_id": 1,  # will be overridden per test
    "title": "Rapport RBAC Test",
    "file_url": "https://cdn.example.com/reports/rbac-test.pdf",
}


def _make_user(db, *, email, role, is_admin=True, plan="entreprise"):
    """Create a user with a specific admin role."""
    user = User(
        email=email,
        full_name=f"User {role}",
        hashed_password=hash_password("Password123!"),
        plan=plan,
        is_active=True,
        is_admin=is_admin,
        admin_role=role if is_admin else None,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def _headers_for(user):
    """Generate Authorization headers for a user."""
    token = create_access_token(data={"sub": user.email})
    return {"Authorization": f"Bearer {token}"}


def _create_study(db):
    """Insert a study directly in the DB and return it."""
    s = Study(
        title="Etude Support RBAC",
        description="Support study for RBAC tests.",
        category="Test",
        is_active=True,
    )
    db.add(s)
    db.commit()
    db.refresh(s)
    return s


# ===========================================================================
# 1. Basic user CANNOT access admin endpoints
# ===========================================================================

class TestBasicUserBlocked:
    """Un utilisateur basic ne peut pas acceder aux endpoints admin."""

    def test_basic_user_cannot_create_study(self, client, auth_headers):
        response = client.post(
            "/api/studies", json=STUDY_PAYLOAD, headers=auth_headers
        )
        assert response.status_code == 403

    def test_basic_user_cannot_create_insight(self, client, db, auth_headers):
        study = _create_study(db)
        payload = {**INSIGHT_PAYLOAD, "study_id": study.id}
        response = client.post(
            "/api/insights", json=payload, headers=auth_headers
        )
        assert response.status_code == 403

    def test_basic_user_cannot_create_report(self, client, db, auth_headers):
        study = _create_study(db)
        payload = {**REPORT_PAYLOAD, "study_id": study.id}
        response = client.post(
            "/api/reports", json=payload, headers=auth_headers
        )
        assert response.status_code == 403

    def test_basic_user_cannot_delete_study(self, client, db, auth_headers, admin_user):
        study = _create_study(db)
        response = client.delete(
            f"/api/studies/{study.id}", headers=auth_headers
        )
        assert response.status_code == 403

    def test_basic_user_cannot_list_admin_users(self, client, auth_headers):
        response = client.get("/api/admin/users", headers=auth_headers)
        assert response.status_code == 403

    def test_basic_user_cannot_get_admin_roles(self, client, auth_headers):
        response = client.get("/api/admin/roles", headers=auth_headers)
        assert response.status_code == 403


# ===========================================================================
# 2. admin_studies CANNOT create insights or reports
# ===========================================================================

class TestAdminStudiesRestricted:
    """admin_studies n'a que la permission 'studies'."""

    def test_admin_studies_can_create_study(self, client, db):
        user = _make_user(db, email="studies_admin@test.com", role="admin_studies")
        headers = _headers_for(user)
        response = client.post(
            "/api/studies", json=STUDY_PAYLOAD, headers=headers
        )
        assert response.status_code == 201

    def test_admin_studies_cannot_create_insight(self, client, db):
        user = _make_user(db, email="studies_admin2@test.com", role="admin_studies")
        study = _create_study(db)
        headers = _headers_for(user)
        payload = {**INSIGHT_PAYLOAD, "study_id": study.id}
        response = client.post(
            "/api/insights", json=payload, headers=headers
        )
        assert response.status_code == 403

    def test_admin_studies_cannot_create_report(self, client, db):
        user = _make_user(db, email="studies_admin3@test.com", role="admin_studies")
        study = _create_study(db)
        headers = _headers_for(user)
        payload = {**REPORT_PAYLOAD, "study_id": study.id}
        response = client.post(
            "/api/reports", json=payload, headers=headers
        )
        assert response.status_code == 403

    def test_admin_studies_cannot_manage_users(self, client, db):
        user = _make_user(db, email="studies_admin4@test.com", role="admin_studies")
        headers = _headers_for(user)
        response = client.get("/api/admin/users", headers=headers)
        assert response.status_code == 403


# ===========================================================================
# 3. admin_content CAN create studies + insights + reports
# ===========================================================================

class TestAdminContentPermissions:
    """admin_content a les permissions studies, insights et reports."""

    def test_content_admin_can_create_study(
        self, client, content_admin_auth_headers
    ):
        response = client.post(
            "/api/studies", json=STUDY_PAYLOAD, headers=content_admin_auth_headers
        )
        assert response.status_code == 201

    def test_content_admin_can_create_insight(
        self, client, db, content_admin_auth_headers
    ):
        study = _create_study(db)
        payload = {**INSIGHT_PAYLOAD, "study_id": study.id}
        response = client.post(
            "/api/insights", json=payload, headers=content_admin_auth_headers
        )
        assert response.status_code == 201

    def test_content_admin_can_create_report(
        self, client, db, content_admin_auth_headers
    ):
        study = _create_study(db)
        payload = {**REPORT_PAYLOAD, "study_id": study.id}
        response = client.post(
            "/api/reports", json=payload, headers=content_admin_auth_headers
        )
        assert response.status_code == 201

    def test_content_admin_cannot_manage_users(
        self, client, content_admin_auth_headers
    ):
        """admin_content n'a PAS la permission 'users'."""
        response = client.get(
            "/api/admin/users", headers=content_admin_auth_headers
        )
        assert response.status_code == 403


# ===========================================================================
# 4. super_admin CAN do everything
# ===========================================================================

class TestSuperAdminFullAccess:
    """super_admin a acces a toutes les ressources."""

    def test_super_admin_can_create_study(self, client, admin_auth_headers):
        response = client.post(
            "/api/studies", json=STUDY_PAYLOAD, headers=admin_auth_headers
        )
        assert response.status_code == 201

    def test_super_admin_can_create_insight(
        self, client, db, admin_auth_headers
    ):
        study = _create_study(db)
        payload = {**INSIGHT_PAYLOAD, "study_id": study.id}
        response = client.post(
            "/api/insights", json=payload, headers=admin_auth_headers
        )
        assert response.status_code == 201

    def test_super_admin_can_create_report(
        self, client, db, admin_auth_headers
    ):
        study = _create_study(db)
        payload = {**REPORT_PAYLOAD, "study_id": study.id}
        response = client.post(
            "/api/reports", json=payload, headers=admin_auth_headers
        )
        assert response.status_code == 201

    def test_super_admin_can_list_users(self, client, admin_auth_headers):
        response = client.get("/api/admin/users", headers=admin_auth_headers)
        assert response.status_code == 200

    def test_super_admin_can_get_roles(self, client, admin_auth_headers):
        response = client.get("/api/admin/roles", headers=admin_auth_headers)
        assert response.status_code == 200

    def test_super_admin_can_delete_study(
        self, client, db, admin_auth_headers
    ):
        study = _create_study(db)
        response = client.delete(
            f"/api/studies/{study.id}", headers=admin_auth_headers
        )
        assert response.status_code == 200

    def test_super_admin_can_delete_insight(
        self, client, db, admin_auth_headers, study, insight
    ):
        response = client.delete(
            f"/api/insights/{insight.id}", headers=admin_auth_headers
        )
        assert response.status_code == 200

    def test_super_admin_can_delete_report(
        self, client, db, admin_auth_headers, study, report
    ):
        response = client.delete(
            f"/api/reports/{report.id}", headers=admin_auth_headers
        )
        assert response.status_code == 200


# ===========================================================================
# 5. Unauthenticated user receives 401
# ===========================================================================

class TestUnauthenticatedAccess:
    """Toutes les requetes sans token doivent recevoir 401."""

    def test_get_studies_without_token_returns_401(self, client):
        assert client.get("/api/studies").status_code == 401

    def test_post_study_without_token_returns_401(self, client):
        assert client.post("/api/studies", json=STUDY_PAYLOAD).status_code == 401

    def test_get_insights_without_token_returns_401(self, client):
        assert client.get("/api/insights").status_code == 401

    def test_post_insight_without_token_returns_401(self, client):
        assert client.post("/api/insights", json=INSIGHT_PAYLOAD).status_code == 401

    def test_get_reports_without_token_returns_401(self, client):
        assert client.get("/api/reports").status_code == 401

    def test_get_admin_users_without_token_returns_401(self, client):
        assert client.get("/api/admin/users").status_code == 401

    def test_get_admin_roles_without_token_returns_401(self, client):
        assert client.get("/api/admin/roles").status_code == 401

    def test_get_user_me_without_token_returns_401(self, client):
        assert client.get("/api/users/me").status_code == 401


# ===========================================================================
# 6. Expired token receives 401
# ===========================================================================

class TestExpiredToken:
    """Un token expire doit etre rejete avec 401."""

    def test_expired_token_returns_401(self, client, test_user):
        # Create a token that expired 1 hour ago
        expired_token = jwt.encode(
            {
                "sub": test_user.email,
                "exp": datetime.now(timezone.utc) - timedelta(hours=1),
                "token_type": "access",
                "jti": "expired-jti-test",
            },
            SECRET_KEY,
            algorithm=ALGORITHM,
        )
        headers = {"Authorization": f"Bearer {expired_token}"}
        response = client.get("/api/studies", headers=headers)
        assert response.status_code == 401

    def test_expired_token_detail_message(self, client, test_user):
        expired_token = jwt.encode(
            {
                "sub": test_user.email,
                "exp": datetime.now(timezone.utc) - timedelta(seconds=1),
                "token_type": "access",
                "jti": "expired-jti-test-2",
            },
            SECRET_KEY,
            algorithm=ALGORITHM,
        )
        headers = {"Authorization": f"Bearer {expired_token}"}
        response = client.get("/api/users/me", headers=headers)
        assert response.status_code == 401
        assert "expir" in response.json()["detail"].lower()


# ===========================================================================
# 7. Blacklisted token receives 401
# ===========================================================================

class TestBlacklistedToken:
    """Un token blackliste (post-logout) doit etre rejete avec 401."""

    def test_blacklisted_token_returns_401(self, client, db, test_user):
        # Create a valid token
        token = create_access_token(data={"sub": test_user.email})

        # Decode to get the jti
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        jti = payload["jti"]

        # Blacklist the token
        blacklisted = TokenBlacklist(
            jti=jti,
            user_id=test_user.id,
            expires_at=datetime.now(timezone.utc) + timedelta(days=7),
        )
        db.add(blacklisted)
        db.commit()

        # Attempt to use the blacklisted token
        headers = {"Authorization": f"Bearer {token}"}
        response = client.get("/api/studies", headers=headers)
        assert response.status_code == 401

    def test_blacklisted_token_detail_mentions_revoked(self, client, db, test_user):
        token = create_access_token(data={"sub": test_user.email})
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        jti = payload["jti"]

        blacklisted = TokenBlacklist(
            jti=jti,
            user_id=test_user.id,
            expires_at=datetime.now(timezone.utc) + timedelta(days=7),
        )
        db.add(blacklisted)
        db.commit()

        headers = {"Authorization": f"Bearer {token}"}
        response = client.get("/api/users/me", headers=headers)
        assert response.status_code == 401
        assert "revoked" in response.json()["detail"].lower()


# ===========================================================================
# 8. Malformed / invalid tokens
# ===========================================================================

class TestInvalidTokens:
    """Tokens malformes ou invalides doivent etre rejetes."""

    def test_garbage_token_returns_401(self, client):
        headers = {"Authorization": "Bearer not-a-real-jwt-token"}
        response = client.get("/api/studies", headers=headers)
        assert response.status_code == 401

    def test_missing_bearer_prefix_returns_401(self, client):
        headers = {"Authorization": "just-a-token-no-bearer"}
        response = client.get("/api/studies", headers=headers)
        assert response.status_code == 401

    def test_empty_authorization_header_returns_401(self, client):
        headers = {"Authorization": ""}
        response = client.get("/api/studies", headers=headers)
        assert response.status_code == 401

    def test_refresh_token_used_as_access_returns_401(self, client, test_user):
        """A refresh token should not be accepted as an access token."""
        from app.auth import create_refresh_token
        refresh = create_refresh_token(data={"sub": test_user.email})
        headers = {"Authorization": f"Bearer {refresh}"}
        response = client.get("/api/studies", headers=headers)
        assert response.status_code == 401


# ===========================================================================
# 9. admin_insights and admin_reports isolation
# ===========================================================================

class TestAdminInsightsRestricted:
    """admin_insights ne peut gerer que les insights."""

    def test_admin_insights_can_create_insight(self, client, db):
        user = _make_user(db, email="insights_admin@test.com", role="admin_insights")
        study = _create_study(db)
        headers = _headers_for(user)
        payload = {**INSIGHT_PAYLOAD, "study_id": study.id}
        response = client.post("/api/insights", json=payload, headers=headers)
        assert response.status_code == 201

    def test_admin_insights_cannot_create_study(self, client, db):
        user = _make_user(db, email="insights_admin2@test.com", role="admin_insights")
        headers = _headers_for(user)
        response = client.post("/api/studies", json=STUDY_PAYLOAD, headers=headers)
        assert response.status_code == 403

    def test_admin_insights_cannot_create_report(self, client, db):
        user = _make_user(db, email="insights_admin3@test.com", role="admin_insights")
        study = _create_study(db)
        headers = _headers_for(user)
        payload = {**REPORT_PAYLOAD, "study_id": study.id}
        response = client.post("/api/reports", json=payload, headers=headers)
        assert response.status_code == 403


class TestAdminReportsRestricted:
    """admin_reports ne peut gerer que les rapports."""

    def test_admin_reports_can_create_report(self, client, db):
        user = _make_user(db, email="reports_admin@test.com", role="admin_reports")
        study = _create_study(db)
        headers = _headers_for(user)
        payload = {**REPORT_PAYLOAD, "study_id": study.id}
        response = client.post("/api/reports", json=payload, headers=headers)
        assert response.status_code == 201

    def test_admin_reports_cannot_create_study(self, client, db):
        user = _make_user(db, email="reports_admin2@test.com", role="admin_reports")
        headers = _headers_for(user)
        response = client.post("/api/studies", json=STUDY_PAYLOAD, headers=headers)
        assert response.status_code == 403

    def test_admin_reports_cannot_create_insight(self, client, db):
        user = _make_user(db, email="reports_admin3@test.com", role="admin_reports")
        study = _create_study(db)
        headers = _headers_for(user)
        payload = {**INSIGHT_PAYLOAD, "study_id": study.id}
        response = client.post("/api/insights", json=payload, headers=headers)
        assert response.status_code == 403
