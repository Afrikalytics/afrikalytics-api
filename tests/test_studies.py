"""
Tests pour les endpoints des etudes de marche — /api/studies/*

Couvre:
- GET    /api/studies         — liste paginee de toutes les etudes
- GET    /api/studies/active  — etudes actives uniquement
- GET    /api/studies/{id}    — detail d'une etude
- POST   /api/studies         — creation (admin requis)
- PUT    /api/studies/{id}    — mise a jour (admin requis)
- DELETE /api/studies/{id}    — suppression (admin requis)
"""

# Payload de base reutilise dans les tests de creation/mise a jour
BASE_STUDY_PAYLOAD = {
    "title": "Nouvelle Etude Marche Senegal",
    "description": "Description de la nouvelle etude de marche.",
    "category": "Commerce",
    "duration": "10-15 min",
    "deadline": "30 Juin 2026",
    "status": "Ouvert",
    "icon": "chart",
    "is_active": True,
}


class TestListStudies:
    """Tests pour GET /api/studies."""

    def test_authenticated_user_can_list_studies(
        self, client, study, auth_headers
    ):
        response = client.get("/api/studies", headers=auth_headers)

        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        assert len(data) >= 1

    def test_list_studies_response_contains_expected_fields(
        self, client, study, auth_headers
    ):
        response = client.get("/api/studies", headers=auth_headers)

        assert response.status_code == 200
        item = response.json()[0]
        for field in ["id", "title", "description", "category", "status", "is_active", "created_at"]:
            assert field in item, f"Champ '{field}' manquant dans la reponse"

    def test_list_studies_pagination_skip_limit(self, client, study, auth_headers):
        response = client.get("/api/studies?skip=0&limit=5", headers=auth_headers)

        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        assert len(data) <= 5

    def test_list_studies_without_token_returns_401(self, client):
        response = client.get("/api/studies")

        assert response.status_code == 401


class TestActiveStudies:
    """Tests pour GET /api/studies/active."""

    def test_returns_only_active_studies(
        self, client, study, inactive_study, auth_headers
    ):
        """La liste active ne doit contenir que les etudes avec is_active=True."""
        response = client.get("/api/studies/active", headers=auth_headers)

        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)

        # Toutes les etudes retournees doivent etre actives
        for item in data:
            assert item["is_active"] is True, (
                f"L'etude '{item['title']}' (id={item['id']}) ne devrait pas etre dans la liste active"
            )

    def test_active_studies_excludes_inactive(
        self, client, study, inactive_study, auth_headers
    ):
        """L'etude inactive ne doit pas apparaitre dans /active."""
        response = client.get("/api/studies/active", headers=auth_headers)

        assert response.status_code == 200
        ids = [item["id"] for item in response.json()]
        assert study.id in ids
        assert inactive_study.id not in ids

    def test_active_studies_without_token_returns_401(self, client):
        response = client.get("/api/studies/active")

        assert response.status_code == 401


class TestGetStudyById:
    """Tests pour GET /api/studies/{id}."""

    def test_authenticated_user_can_get_study_by_id(
        self, client, study, auth_headers
    ):
        response = client.get(f"/api/studies/{study.id}", headers=auth_headers)

        assert response.status_code == 200
        data = response.json()
        assert data["id"] == study.id
        assert data["title"] == study.title
        assert data["category"] == study.category

    def test_get_nonexistent_study_returns_404(self, client, auth_headers):
        response = client.get("/api/studies/99999", headers=auth_headers)

        assert response.status_code == 404
        data = response.json()
        assert "detail" in data

    def test_get_study_without_token_returns_401(self, client, study):
        response = client.get(f"/api/studies/{study.id}")

        assert response.status_code == 401


class TestCreateStudy:
    """Tests pour POST /api/studies."""

    def test_super_admin_can_create_study(self, client, admin_auth_headers):
        response = client.post(
            "/api/studies",
            json=BASE_STUDY_PAYLOAD,
            headers=admin_auth_headers,
        )

        assert response.status_code == 201
        data = response.json()
        assert data["title"] == BASE_STUDY_PAYLOAD["title"]
        assert data["category"] == BASE_STUDY_PAYLOAD["category"]
        assert data["is_active"] is True
        assert "id" in data
        assert "created_at" in data

    def test_content_admin_can_create_study(
        self, client, content_admin_auth_headers
    ):
        """admin_content a la permission 'studies'."""
        response = client.post(
            "/api/studies",
            json=BASE_STUDY_PAYLOAD,
            headers=content_admin_auth_headers,
        )

        assert response.status_code == 201

    def test_regular_user_cannot_create_study_returns_403(
        self, client, auth_headers
    ):
        response = client.post(
            "/api/studies",
            json=BASE_STUDY_PAYLOAD,
            headers=auth_headers,
        )

        assert response.status_code == 403
        data = response.json()
        assert "detail" in data

    def test_create_study_without_token_returns_401(self, client):
        response = client.post("/api/studies", json=BASE_STUDY_PAYLOAD)

        assert response.status_code == 401

    def test_create_study_missing_required_fields_returns_422(
        self, client, admin_auth_headers
    ):
        # Seulement le titre, sans description ni category
        incomplete_payload = {"title": "Etude Incomplete"}
        response = client.post(
            "/api/studies",
            json=incomplete_payload,
            headers=admin_auth_headers,
        )

        assert response.status_code == 422


class TestUpdateStudy:
    """Tests pour PUT /api/studies/{id}."""

    def test_super_admin_can_update_study(
        self, client, study, admin_auth_headers
    ):
        updated_payload = {**BASE_STUDY_PAYLOAD, "title": "Titre Mis a Jour", "status": "Ferme"}
        response = client.put(
            f"/api/studies/{study.id}",
            json=updated_payload,
            headers=admin_auth_headers,
        )

        assert response.status_code == 200
        data = response.json()
        assert data["title"] == "Titre Mis a Jour"
        assert data["status"] == "Ferme"

    def test_regular_user_cannot_update_study_returns_403(
        self, client, study, auth_headers
    ):
        updated_payload = {**BASE_STUDY_PAYLOAD, "title": "Tentative de Hack"}
        response = client.put(
            f"/api/studies/{study.id}",
            json=updated_payload,
            headers=auth_headers,
        )

        assert response.status_code == 403

    def test_update_nonexistent_study_returns_404(self, client, admin_auth_headers):
        response = client.put(
            "/api/studies/99999",
            json=BASE_STUDY_PAYLOAD,
            headers=admin_auth_headers,
        )

        assert response.status_code == 404


class TestDeleteStudy:
    """Tests pour DELETE /api/studies/{id}."""

    def test_super_admin_can_delete_study(
        self, client, study, admin_auth_headers
    ):
        response = client.delete(
            f"/api/studies/{study.id}",
            headers=admin_auth_headers,
        )

        assert response.status_code == 200
        data = response.json()
        assert "message" in data
        assert "supprim" in data["message"].lower()

    def test_deleted_study_no_longer_accessible(
        self, client, study, admin_auth_headers, auth_headers
    ):
        """Apres suppression, un GET sur l'etude doit retourner 404."""
        client.delete(f"/api/studies/{study.id}", headers=admin_auth_headers)

        get_response = client.get(f"/api/studies/{study.id}", headers=auth_headers)
        assert get_response.status_code == 404

    def test_regular_user_cannot_delete_study_returns_403(
        self, client, study, auth_headers
    ):
        response = client.delete(
            f"/api/studies/{study.id}",
            headers=auth_headers,
        )

        assert response.status_code == 403

    def test_delete_nonexistent_study_returns_404(self, client, admin_auth_headers):
        response = client.delete(
            "/api/studies/99999",
            headers=admin_auth_headers,
        )

        assert response.status_code == 404

    def test_delete_study_without_token_returns_401(self, client, study):
        response = client.delete(f"/api/studies/{study.id}")

        assert response.status_code == 401
