"""
Tests d'isolation des donnees (cross-tenant / multi-user).

Verifie qu'un utilisateur ne peut pas acceder aux ressources d'un autre
utilisateur, sauf s'il est admin.

NOTE: Le systeme actuel d'Afrikalytics ne filtre PAS les etudes par user
(les etudes sont globales, gerees par les admins). L'isolation concerne
donc principalement les operations d'ecriture (seuls les admins peuvent
creer/modifier/supprimer) et l'acces au profil utilisateur.

Ces tests verifient le contrat de securite actuel :
- Les utilisateurs standard ne peuvent PAS modifier/supprimer des etudes
- Les admins PEUVENT voir et gerer toutes les etudes
- Le profil /api/users/me retourne uniquement le profil de l'utilisateur connecte
"""
from app.auth import create_access_token, hash_password
from app.models import User, Study


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_user(db, email, name="User Test"):
    """Create a basic (non-admin) user."""
    user = User(
        email=email,
        full_name=name,
        hashed_password=hash_password("Password123!"),
        plan="basic",
        is_active=True,
        is_admin=False,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def _headers_for(user):
    """Generate Authorization headers for a user."""
    token = create_access_token(data={"sub": user.email})
    return {"Authorization": f"Bearer {token}"}


def _create_study_as_admin(client, admin_auth_headers, title="Etude Admin"):
    """Create a study via the API using admin credentials."""
    payload = {
        "title": title,
        "description": "Description de l'etude.",
        "category": "Finance",
    }
    response = client.post(
        "/api/studies", json=payload, headers=admin_auth_headers
    )
    assert response.status_code == 201
    return response.json()


# ===========================================================================
# 1. User A creates a study -> User B CANNOT modify it
# ===========================================================================

class TestStudyWriteIsolation:
    """Un utilisateur standard ne peut pas modifier/supprimer les etudes."""

    def test_user_b_cannot_update_study(
        self, client, db, admin_auth_headers
    ):
        """User B (basic) ne peut PAS modifier une etude creee par un admin."""
        # Admin creates a study
        study_data = _create_study_as_admin(client, admin_auth_headers)
        study_id = study_data["id"]

        # User B tries to update it
        user_b = _make_user(db, "userb_update@test.com")
        headers_b = _headers_for(user_b)

        update_payload = {"title": "Titre modifie par User B"}
        response = client.put(
            f"/api/studies/{study_id}",
            json=update_payload,
            headers=headers_b,
        )
        assert response.status_code == 403

    def test_user_b_cannot_delete_study(
        self, client, db, admin_auth_headers
    ):
        """User B (basic) ne peut PAS supprimer une etude creee par un admin."""
        study_data = _create_study_as_admin(client, admin_auth_headers)
        study_id = study_data["id"]

        user_b = _make_user(db, "userb_delete@test.com")
        headers_b = _headers_for(user_b)

        response = client.delete(
            f"/api/studies/{study_id}", headers=headers_b
        )
        assert response.status_code == 403

    def test_user_b_cannot_create_study(self, client, db):
        """User B (basic) ne peut PAS creer une etude."""
        user_b = _make_user(db, "userb_create@test.com")
        headers_b = _headers_for(user_b)

        payload = {
            "title": "Etude non autorisee",
            "description": "User B tente de creer.",
            "category": "Test",
        }
        response = client.post("/api/studies", json=payload, headers=headers_b)
        assert response.status_code == 403


# ===========================================================================
# 2. Admin CAN see and manage all studies
# ===========================================================================

class TestAdminGlobalAccess:
    """Les admins peuvent voir et gerer les etudes de tous les utilisateurs."""

    def test_admin_can_see_all_studies(
        self, client, db, admin_auth_headers
    ):
        """Un admin peut lister toutes les etudes."""
        # Create multiple studies
        _create_study_as_admin(client, admin_auth_headers, "Etude 1")
        _create_study_as_admin(client, admin_auth_headers, "Etude 2")

        response = client.get("/api/studies", headers=admin_auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert len(data) >= 2

    def test_admin_can_update_any_study(
        self, client, db, admin_auth_headers
    ):
        """Un admin peut modifier n'importe quelle etude."""
        study_data = _create_study_as_admin(client, admin_auth_headers)
        study_id = study_data["id"]

        update_payload = {"title": "Titre modifie par Admin"}
        response = client.put(
            f"/api/studies/{study_id}",
            json=update_payload,
            headers=admin_auth_headers,
        )
        assert response.status_code == 200
        assert response.json()["title"] == "Titre modifie par Admin"

    def test_admin_can_delete_any_study(
        self, client, db, admin_auth_headers
    ):
        """Un admin peut supprimer n'importe quelle etude."""
        study_data = _create_study_as_admin(client, admin_auth_headers)
        study_id = study_data["id"]

        response = client.delete(
            f"/api/studies/{study_id}", headers=admin_auth_headers
        )
        assert response.status_code == 200

        # Verify it's gone
        get_response = client.get(
            f"/api/studies/{study_id}", headers=admin_auth_headers
        )
        assert get_response.status_code == 404


# ===========================================================================
# 3. User profile isolation (/api/users/me)
# ===========================================================================

class TestUserProfileIsolation:
    """Chaque utilisateur ne voit que son propre profil via /api/users/me."""

    def test_user_a_sees_own_profile(self, client, test_user, auth_headers):
        """User A voit son propre profil."""
        response = client.get("/api/users/me", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert data["email"] == test_user.email
        assert data["id"] == test_user.id

    def test_user_b_sees_own_profile_not_user_a(self, client, db, test_user):
        """User B ne voit PAS le profil de User A via /me."""
        user_b = _make_user(db, "userb_profile@test.com", "User B")
        headers_b = _headers_for(user_b)

        response = client.get("/api/users/me", headers=headers_b)
        assert response.status_code == 200
        data = response.json()
        # Should be User B, not User A
        assert data["email"] == user_b.email
        assert data["email"] != test_user.email

    def test_different_users_get_different_profiles(self, client, db):
        """Deux utilisateurs differents obtiennent des profils differents."""
        user_a = _make_user(db, "isolation_a@test.com", "User A")
        user_b = _make_user(db, "isolation_b@test.com", "User B")

        resp_a = client.get("/api/users/me", headers=_headers_for(user_a))
        resp_b = client.get("/api/users/me", headers=_headers_for(user_b))

        assert resp_a.status_code == 200
        assert resp_b.status_code == 200

        data_a = resp_a.json()
        data_b = resp_b.json()

        assert data_a["id"] != data_b["id"]
        assert data_a["email"] == "isolation_a@test.com"
        assert data_b["email"] == "isolation_b@test.com"


# ===========================================================================
# 4. Cross-user insight/report isolation
# ===========================================================================

class TestInsightWriteIsolation:
    """Un utilisateur standard ne peut pas creer/modifier/supprimer des insights."""

    def test_basic_user_cannot_create_insight(self, client, db, study):
        """Un basic user ne peut PAS creer un insight."""
        user = _make_user(db, "basic_insight@test.com")
        headers = _headers_for(user)
        payload = {
            "study_id": study.id,
            "title": "Insight non autorise",
        }
        response = client.post("/api/insights", json=payload, headers=headers)
        assert response.status_code == 403

    def test_basic_user_cannot_delete_insight(
        self, client, db, study, insight
    ):
        """Un basic user ne peut PAS supprimer un insight."""
        user = _make_user(db, "basic_del_insight@test.com")
        headers = _headers_for(user)
        response = client.delete(
            f"/api/insights/{insight.id}", headers=headers
        )
        assert response.status_code == 403


class TestReportWriteIsolation:
    """Un utilisateur standard ne peut pas creer/modifier/supprimer des rapports."""

    def test_basic_user_cannot_create_report(self, client, db, study):
        """Un basic user ne peut PAS creer un rapport."""
        user = _make_user(db, "basic_report@test.com")
        headers = _headers_for(user)
        payload = {
            "study_id": study.id,
            "title": "Rapport non autorise",
            "file_url": "https://example.com/report.pdf",
        }
        response = client.post("/api/reports", json=payload, headers=headers)
        assert response.status_code == 403

    def test_basic_user_cannot_delete_report(
        self, client, db, study, report
    ):
        """Un basic user ne peut PAS supprimer un rapport."""
        user = _make_user(db, "basic_del_report@test.com")
        headers = _headers_for(user)
        response = client.delete(
            f"/api/reports/{report.id}", headers=headers
        )
        assert response.status_code == 403
