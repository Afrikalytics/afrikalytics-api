"""
Tests pour les endpoints des insights — /api/insights/*

Couvre:
- GET    /api/insights              — liste des insights publies
- GET    /api/insights/study/{id}   — insight par etude
- GET    /api/insights/{id}         — detail d'un insight (404 si absent)
- POST   /api/insights              — creation (admin 201, user 403)
- PUT    /api/insights/{id}         — mise a jour (admin, 404)
- DELETE /api/insights/{id}         — suppression (admin, user 403)
"""

# Payload de base reutilise dans les tests de creation/mise a jour
BASE_INSIGHT_PAYLOAD = {
    "study_id": None,  # sera remplace dans les tests avec study.id
    "title": "Nouvel Insight Marche Dakar",
    "summary": "Resume de l'analyse du marche de Dakar.",
    "key_findings": "Resultat 1, Resultat 2, Resultat 3",
    "recommendations": "Recommandation principale : investir dans le secteur X",
    "author": "Equipe Afrikalytics",
    "images": [],
    "is_published": True,
}


class TestListInsights:
    """Tests pour GET /api/insights."""

    def test_authenticated_user_can_list_insights(
        self, client, insight, auth_headers
    ):
        response = client.get("/api/insights", headers=auth_headers)

        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        assert len(data) >= 1

    def test_list_insights_response_contains_expected_fields(
        self, client, insight, auth_headers
    ):
        response = client.get("/api/insights", headers=auth_headers)

        assert response.status_code == 200
        item = response.json()[0]
        for field in ["id", "study_id", "title", "summary", "is_published", "created_at"]:
            assert field in item, f"Champ '{field}' manquant dans la reponse"

    def test_list_insights_returns_only_published(
        self, client, insight, auth_headers, db
    ):
        """Seuls les insights avec is_published=True doivent etre retournes."""
        response = client.get("/api/insights", headers=auth_headers)

        assert response.status_code == 200
        for item in response.json():
            assert item["is_published"] is True

    def test_list_insights_pagination_skip_limit(self, client, insight, auth_headers):
        response = client.get("/api/insights?skip=0&limit=10", headers=auth_headers)

        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        assert len(data) <= 10

    def test_list_insights_without_token_returns_401(self, client):
        response = client.get("/api/insights")

        assert response.status_code == 401


class TestGetInsightByStudy:
    """Tests pour GET /api/insights/study/{study_id}."""

    def test_authenticated_user_can_get_insight_by_study(
        self, client, insight, study, auth_headers
    ):
        response = client.get(
            f"/api/insights/study/{study.id}", headers=auth_headers
        )

        assert response.status_code == 200
        data = response.json()
        assert data["study_id"] == study.id
        assert data["title"] == insight.title

    def test_get_insight_by_nonexistent_study_returns_404(
        self, client, auth_headers
    ):
        response = client.get("/api/insights/study/99999", headers=auth_headers)

        assert response.status_code == 404
        assert "detail" in response.json()

    def test_get_insight_by_study_without_token_returns_401(self, client, study):
        response = client.get(f"/api/insights/study/{study.id}")

        assert response.status_code == 401


class TestGetInsightById:
    """Tests pour GET /api/insights/{insight_id}."""

    def test_authenticated_user_can_get_insight_by_id(
        self, client, insight, auth_headers
    ):
        response = client.get(f"/api/insights/{insight.id}", headers=auth_headers)

        assert response.status_code == 200
        data = response.json()
        assert data["id"] == insight.id
        assert data["title"] == insight.title
        assert data["author"] == insight.author

    def test_get_nonexistent_insight_returns_404(self, client, auth_headers):
        response = client.get("/api/insights/99999", headers=auth_headers)

        assert response.status_code == 404
        assert "detail" in response.json()

    def test_get_insight_without_token_returns_401(self, client, insight):
        response = client.get(f"/api/insights/{insight.id}")

        assert response.status_code == 401


class TestCreateInsight:
    """Tests pour POST /api/insights."""

    def test_super_admin_can_create_insight(
        self, client, study, admin_auth_headers
    ):
        payload = {**BASE_INSIGHT_PAYLOAD, "study_id": study.id}
        response = client.post(
            "/api/insights",
            json=payload,
            headers=admin_auth_headers,
        )

        assert response.status_code == 201
        data = response.json()
        assert data["title"] == payload["title"]
        assert data["study_id"] == study.id
        assert data["is_published"] is True
        assert "id" in data
        assert "created_at" in data

    def test_content_admin_can_create_insight(
        self, client, study, content_admin_auth_headers
    ):
        """admin_content a la permission 'insights'."""
        payload = {**BASE_INSIGHT_PAYLOAD, "study_id": study.id}
        response = client.post(
            "/api/insights",
            json=payload,
            headers=content_admin_auth_headers,
        )

        assert response.status_code == 201

    def test_regular_user_cannot_create_insight_returns_403(
        self, client, study, auth_headers
    ):
        payload = {**BASE_INSIGHT_PAYLOAD, "study_id": study.id}
        response = client.post(
            "/api/insights",
            json=payload,
            headers=auth_headers,
        )

        assert response.status_code == 403
        assert "detail" in response.json()

    def test_create_insight_without_token_returns_401(self, client, study):
        payload = {**BASE_INSIGHT_PAYLOAD, "study_id": study.id}
        response = client.post("/api/insights", json=payload)

        assert response.status_code == 401

    def test_create_insight_missing_required_fields_returns_422(
        self, client, admin_auth_headers
    ):
        # Manque study_id et title (obligatoires)
        incomplete_payload = {"summary": "Resume seulement"}
        response = client.post(
            "/api/insights",
            json=incomplete_payload,
            headers=admin_auth_headers,
        )

        assert response.status_code == 422


class TestUpdateInsight:
    """Tests pour PUT /api/insights/{insight_id}."""

    def test_super_admin_can_update_insight(
        self, client, insight, study, admin_auth_headers
    ):
        updated_payload = {
            **BASE_INSIGHT_PAYLOAD,
            "study_id": study.id,
            "title": "Insight Mis a Jour",
            "is_published": False,
        }
        response = client.put(
            f"/api/insights/{insight.id}",
            json=updated_payload,
            headers=admin_auth_headers,
        )

        assert response.status_code == 200
        data = response.json()
        assert data["title"] == "Insight Mis a Jour"
        assert data["is_published"] is False

    def test_regular_user_cannot_update_insight_returns_403(
        self, client, insight, study, auth_headers
    ):
        updated_payload = {**BASE_INSIGHT_PAYLOAD, "study_id": study.id}
        response = client.put(
            f"/api/insights/{insight.id}",
            json=updated_payload,
            headers=auth_headers,
        )

        assert response.status_code == 403

    def test_update_nonexistent_insight_returns_404(
        self, client, study, admin_auth_headers
    ):
        payload = {**BASE_INSIGHT_PAYLOAD, "study_id": study.id}
        response = client.put(
            "/api/insights/99999",
            json=payload,
            headers=admin_auth_headers,
        )

        assert response.status_code == 404


class TestDeleteInsight:
    """Tests pour DELETE /api/insights/{insight_id}."""

    def test_super_admin_can_delete_insight(
        self, client, insight, admin_auth_headers
    ):
        response = client.delete(
            f"/api/insights/{insight.id}",
            headers=admin_auth_headers,
        )

        assert response.status_code == 200
        data = response.json()
        assert "message" in data

    def test_deleted_insight_no_longer_accessible(
        self, client, insight, admin_auth_headers, auth_headers
    ):
        """Apres suppression, un GET sur l'insight doit retourner 404."""
        client.delete(f"/api/insights/{insight.id}", headers=admin_auth_headers)

        get_response = client.get(
            f"/api/insights/{insight.id}", headers=auth_headers
        )
        assert get_response.status_code == 404

    def test_regular_user_cannot_delete_insight_returns_403(
        self, client, insight, auth_headers
    ):
        response = client.delete(
            f"/api/insights/{insight.id}",
            headers=auth_headers,
        )

        assert response.status_code == 403

    def test_delete_nonexistent_insight_returns_404(
        self, client, admin_auth_headers
    ):
        response = client.delete(
            "/api/insights/99999",
            headers=admin_auth_headers,
        )

        assert response.status_code == 404

    def test_delete_insight_without_token_returns_401(self, client, insight):
        response = client.delete(f"/api/insights/{insight.id}")

        assert response.status_code == 401
