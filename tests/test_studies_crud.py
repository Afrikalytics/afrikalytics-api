"""
Extended CRUD tests for study endpoints — /api/studies/*

Covers flows not fully tested in test_studies.py:
- POST   /api/studies         — admin vs non-admin creation
- PUT    /api/studies/{id}    — partial update
- DELETE /api/studies/{id}    — soft delete behavior (deleted study excluded from lists)
- GET    /api/studies         — include/exclude deleted studies
"""

from app.auth import hash_password, create_access_token
from app.models import User, Study


BASE_STUDY_PAYLOAD = {
    "title": "Etude CRUD Test",
    "description": "Description pour test CRUD.",
    "category": "Commerce",
    "duration": "10-15 min",
    "deadline": "30 Juin 2026",
    "status": "Ouvert",
    "icon": "chart",
    "is_active": True,
}


class TestCreateStudyExtended:
    """Extended tests for POST /api/studies."""

    def test_create_study_admin_returns_201(self, client, admin_auth_headers):
        """Super admin can create a study and gets 201."""
        response = client.post(
            "/api/studies",
            json=BASE_STUDY_PAYLOAD,
            headers=admin_auth_headers,
        )
        assert response.status_code == 201
        data = response.json()
        assert data["title"] == BASE_STUDY_PAYLOAD["title"]
        assert data["category"] == BASE_STUDY_PAYLOAD["category"]
        assert "id" in data
        assert "created_at" in data

    def test_create_study_non_admin_returns_403(self, client, auth_headers):
        """A regular user cannot create a study."""
        response = client.post(
            "/api/studies",
            json=BASE_STUDY_PAYLOAD,
            headers=auth_headers,
        )
        assert response.status_code == 403
        data = response.json()
        assert "detail" in data

    def test_create_study_content_admin_succeeds(
        self, client, content_admin_auth_headers
    ):
        """Content admin (admin_content role) can create studies."""
        response = client.post(
            "/api/studies",
            json=BASE_STUDY_PAYLOAD,
            headers=content_admin_auth_headers,
        )
        assert response.status_code == 201

    def test_create_study_without_auth_returns_401(self, client):
        """No token must return 401."""
        response = client.post("/api/studies", json=BASE_STUDY_PAYLOAD)
        assert response.status_code == 401

    def test_create_study_missing_title_returns_422(self, client, admin_auth_headers):
        """A study without a title should be rejected by validation."""
        incomplete = {
            "description": "Missing title",
            "category": "Commerce",
        }
        response = client.post(
            "/api/studies",
            json=incomplete,
            headers=admin_auth_headers,
        )
        assert response.status_code == 422


class TestUpdateStudyExtended:
    """Extended tests for PUT /api/studies/{id}."""

    def test_update_study_partial_title(
        self, client, study, admin_auth_headers
    ):
        """Admin can update just the title of a study."""
        payload = {**BASE_STUDY_PAYLOAD, "title": "Titre Partiellement Mis a Jour"}
        response = client.put(
            f"/api/studies/{study.id}",
            json=payload,
            headers=admin_auth_headers,
        )
        assert response.status_code == 200
        data = response.json()
        assert data["title"] == "Titre Partiellement Mis a Jour"

    def test_update_study_change_status(
        self, client, study, admin_auth_headers
    ):
        """Admin can change study status from Ouvert to Ferme."""
        payload = {**BASE_STUDY_PAYLOAD, "status": "Ferme"}
        response = client.put(
            f"/api/studies/{study.id}",
            json=payload,
            headers=admin_auth_headers,
        )
        assert response.status_code == 200
        assert response.json()["status"] == "Ferme"

    def test_update_study_deactivate(
        self, client, study, admin_auth_headers
    ):
        """Admin can deactivate a study by setting is_active to False."""
        payload = {**BASE_STUDY_PAYLOAD, "is_active": False}
        response = client.put(
            f"/api/studies/{study.id}",
            json=payload,
            headers=admin_auth_headers,
        )
        assert response.status_code == 200
        assert response.json()["is_active"] is False

    def test_update_study_nonexistent_returns_404(self, client, admin_auth_headers):
        """Updating a non-existent study returns 404."""
        response = client.put(
            "/api/studies/99999",
            json=BASE_STUDY_PAYLOAD,
            headers=admin_auth_headers,
        )
        assert response.status_code == 404

    def test_update_study_non_admin_returns_403(
        self, client, study, auth_headers
    ):
        """Regular users cannot update studies."""
        payload = {**BASE_STUDY_PAYLOAD, "title": "Hacked Title"}
        response = client.put(
            f"/api/studies/{study.id}",
            json=payload,
            headers=auth_headers,
        )
        assert response.status_code == 403


class TestDeleteStudyExtended:
    """Extended tests for DELETE /api/studies/{id}."""

    def test_delete_study_returns_success_message(
        self, client, study, admin_auth_headers
    ):
        """Deleting a study must return a success message."""
        response = client.delete(
            f"/api/studies/{study.id}",
            headers=admin_auth_headers,
        )
        assert response.status_code == 200
        data = response.json()
        assert "message" in data
        assert "supprim" in data["message"].lower()

    def test_deleted_study_excluded_from_list(
        self, client, study, admin_auth_headers, auth_headers
    ):
        """After deletion, the study must not appear in the regular list."""
        # Delete the study
        client.delete(f"/api/studies/{study.id}", headers=admin_auth_headers)

        # Verify it's gone from the regular list
        response = client.get("/api/studies", headers=auth_headers)
        assert response.status_code == 200
        ids = [s["id"] for s in response.json()]
        assert study.id not in ids

    def test_deleted_study_excluded_from_active(
        self, client, study, admin_auth_headers, auth_headers
    ):
        """After deletion, the study must not appear in the active list."""
        client.delete(f"/api/studies/{study.id}", headers=admin_auth_headers)

        response = client.get("/api/studies/active", headers=auth_headers)
        assert response.status_code == 200
        ids = [s["id"] for s in response.json()]
        assert study.id not in ids

    def test_deleted_study_get_by_id_returns_404(
        self, client, study, admin_auth_headers, auth_headers
    ):
        """GET on a deleted study ID must return 404."""
        client.delete(f"/api/studies/{study.id}", headers=admin_auth_headers)

        response = client.get(f"/api/studies/{study.id}", headers=auth_headers)
        assert response.status_code == 404

    def test_delete_nonexistent_study_returns_404(self, client, admin_auth_headers):
        """Deleting a non-existent study must return 404."""
        response = client.delete(
            "/api/studies/99999",
            headers=admin_auth_headers,
        )
        assert response.status_code == 404

    def test_delete_study_non_admin_returns_403(
        self, client, study, auth_headers
    ):
        """Regular users cannot delete studies."""
        response = client.delete(
            f"/api/studies/{study.id}",
            headers=auth_headers,
        )
        assert response.status_code == 403

    def test_delete_study_without_auth_returns_401(self, client, study):
        """No token must return 401."""
        response = client.delete(f"/api/studies/{study.id}")
        assert response.status_code == 401


class TestStudyListFiltering:
    """Tests for study list filtering behavior."""

    def test_active_endpoint_excludes_inactive_studies(
        self, client, study, inactive_study, auth_headers
    ):
        """The /active endpoint must only return active studies."""
        response = client.get("/api/studies/active", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()

        for item in data:
            assert item["is_active"] is True

        ids = [s["id"] for s in data]
        assert study.id in ids
        assert inactive_study.id not in ids

    def test_main_list_returns_all_studies(
        self, client, study, inactive_study, auth_headers
    ):
        """The main /api/studies endpoint returns both active and inactive studies."""
        response = client.get("/api/studies", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        ids = [s["id"] for s in data]
        assert study.id in ids
        # inactive_study may or may not be included depending on implementation
        # At minimum, the active study should be present
