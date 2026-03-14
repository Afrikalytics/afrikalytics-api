"""
Tests pour les endpoints des rapports — /api/reports/*

Couvre:
- GET    /api/reports                               — liste des rapports disponibles
- GET    /api/reports/study/{id}                    — rapport par etude
- GET    /api/reports/{id}                          — detail (404 si absent)
- POST   /api/reports                               — creation (admin 201, user 403)
- PUT    /api/reports/{id}                          — mise a jour (admin, 404)
- DELETE /api/reports/{id}                          — suppression (admin, user 403)
- POST   /api/reports/{id}/download                 — enregistrer un telechargement
- GET    /api/reports/{id} plan-gated               — basic vs premium
"""

# Payload de base reutilise dans les tests de creation/mise a jour
BASE_REPORT_PAYLOAD = {
    "study_id": None,  # sera remplace avec study.id
    "title": "Rapport Annuel Marche Senegal 2026",
    "description": "Analyse complete du marche senegalais pour 2026.",
    "file_url": "https://cdn.example.com/reports/marche-senegal-2026.pdf",
    "file_name": "marche-senegal-2026.pdf",
    "file_size": 512000,
    "report_type": "basic",
    "is_available": True,
}


class TestListReports:
    """Tests pour GET /api/reports."""

    def test_authenticated_user_can_list_reports(
        self, client, report, auth_headers
    ):
        response = client.get("/api/reports", headers=auth_headers)

        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        assert len(data) >= 1

    def test_list_reports_response_contains_expected_fields(
        self, client, report, auth_headers
    ):
        response = client.get("/api/reports", headers=auth_headers)

        assert response.status_code == 200
        item = response.json()[0]
        for field in ["id", "study_id", "title", "file_url", "report_type", "is_available", "created_at"]:
            assert field in item, f"Champ '{field}' manquant dans la reponse"

    def test_list_reports_returns_only_available(
        self, client, report, auth_headers
    ):
        """Seuls les rapports avec is_available=True doivent etre retournes."""
        response = client.get("/api/reports", headers=auth_headers)

        assert response.status_code == 200
        for item in response.json():
            assert item["is_available"] is True

    def test_list_reports_without_token_returns_401(self, client):
        response = client.get("/api/reports")

        assert response.status_code == 401


class TestGetReportByStudy:
    """Tests pour GET /api/reports/study/{study_id}."""

    def test_authenticated_user_can_get_report_by_study(
        self, client, report, study, auth_headers
    ):
        response = client.get(
            f"/api/reports/study/{study.id}", headers=auth_headers
        )

        assert response.status_code == 200
        data = response.json()
        assert data["study_id"] == study.id
        assert data["title"] == report.title

    def test_get_report_by_nonexistent_study_returns_404(
        self, client, auth_headers
    ):
        response = client.get("/api/reports/study/99999", headers=auth_headers)

        assert response.status_code == 404
        assert "detail" in response.json()

    def test_get_report_by_study_without_token_returns_401(self, client, study):
        response = client.get(f"/api/reports/study/{study.id}")

        assert response.status_code == 401


class TestGetReportById:
    """Tests pour GET /api/reports/{report_id}."""

    def test_basic_user_can_access_basic_report(
        self, client, report, auth_headers
    ):
        """Le rapport de test est de type 'basic', accessible aux utilisateurs basic."""
        response = client.get(f"/api/reports/{report.id}", headers=auth_headers)

        assert response.status_code == 200
        data = response.json()
        assert data["id"] == report.id
        assert data["title"] == report.title
        assert data["file_url"] == report.file_url

    def test_get_nonexistent_report_returns_404(self, client, auth_headers):
        response = client.get("/api/reports/99999", headers=auth_headers)

        assert response.status_code == 404
        assert "detail" in response.json()

    def test_get_report_without_token_returns_401(self, client, report):
        response = client.get(f"/api/reports/{report.id}")

        assert response.status_code == 401

    def test_basic_user_cannot_access_premium_report(
        self, client, study, db, auth_headers
    ):
        """Un utilisateur basic ne peut pas acceder a un rapport de type 'premium'."""
        from models import Report
        premium_report = Report(
            study_id=study.id,
            title="Rapport Premium",
            description="Rapport accessible au plan professionnel uniquement.",
            file_url="https://cdn.example.com/reports/premium.pdf",
            file_name="premium.pdf",
            file_size=1024000,
            report_type="premium",
            download_count=0,
            is_available=True,
        )
        db.add(premium_report)
        db.commit()
        db.refresh(premium_report)

        response = client.get(
            f"/api/reports/{premium_report.id}", headers=auth_headers
        )

        assert response.status_code == 403
        assert "detail" in response.json()

    def test_enterprise_user_can_access_premium_report(
        self, client, study, db, enterprise_auth_headers
    ):
        """Un utilisateur entreprise peut acceder aux rapports premium."""
        from models import Report
        premium_report = Report(
            study_id=study.id,
            title="Rapport Premium Entreprise",
            description="Rapport premium.",
            file_url="https://cdn.example.com/reports/premium-ent.pdf",
            file_name="premium-ent.pdf",
            file_size=2048000,
            report_type="premium",
            download_count=0,
            is_available=True,
        )
        db.add(premium_report)
        db.commit()
        db.refresh(premium_report)

        response = client.get(
            f"/api/reports/{premium_report.id}", headers=enterprise_auth_headers
        )

        assert response.status_code == 200
        data = response.json()
        assert data["report_type"] == "premium"


class TestCreateReport:
    """Tests pour POST /api/reports."""

    def test_super_admin_can_create_report(
        self, client, study, admin_auth_headers
    ):
        payload = {**BASE_REPORT_PAYLOAD, "study_id": study.id}
        response = client.post(
            "/api/reports",
            json=payload,
            headers=admin_auth_headers,
        )

        assert response.status_code == 201
        data = response.json()
        assert data["title"] == payload["title"]
        assert data["study_id"] == study.id
        assert data["is_available"] is True
        assert "id" in data
        assert "created_at" in data

    def test_content_admin_can_create_report(
        self, client, study, content_admin_auth_headers
    ):
        """admin_content a la permission 'reports'."""
        payload = {**BASE_REPORT_PAYLOAD, "study_id": study.id}
        response = client.post(
            "/api/reports",
            json=payload,
            headers=content_admin_auth_headers,
        )

        assert response.status_code == 201

    def test_regular_user_cannot_create_report_returns_403(
        self, client, study, auth_headers
    ):
        payload = {**BASE_REPORT_PAYLOAD, "study_id": study.id}
        response = client.post(
            "/api/reports",
            json=payload,
            headers=auth_headers,
        )

        assert response.status_code == 403
        assert "detail" in response.json()

    def test_create_report_without_token_returns_401(self, client, study):
        payload = {**BASE_REPORT_PAYLOAD, "study_id": study.id}
        response = client.post("/api/reports", json=payload)

        assert response.status_code == 401

    def test_create_report_missing_required_fields_returns_422(
        self, client, admin_auth_headers
    ):
        # Manque file_url (obligatoire)
        incomplete_payload = {
            "study_id": 1,
            "title": "Rapport Incomplet",
        }
        response = client.post(
            "/api/reports",
            json=incomplete_payload,
            headers=admin_auth_headers,
        )

        assert response.status_code == 422


class TestUpdateReport:
    """Tests pour PUT /api/reports/{report_id}."""

    def test_super_admin_can_update_report(
        self, client, report, study, admin_auth_headers
    ):
        updated_payload = {
            **BASE_REPORT_PAYLOAD,
            "study_id": study.id,
            "title": "Rapport Mis a Jour",
            "report_type": "premium",
        }
        response = client.put(
            f"/api/reports/{report.id}",
            json=updated_payload,
            headers=admin_auth_headers,
        )

        assert response.status_code == 200
        data = response.json()
        assert data["title"] == "Rapport Mis a Jour"
        assert data["report_type"] == "premium"

    def test_regular_user_cannot_update_report_returns_403(
        self, client, report, study, auth_headers
    ):
        updated_payload = {**BASE_REPORT_PAYLOAD, "study_id": study.id}
        response = client.put(
            f"/api/reports/{report.id}",
            json=updated_payload,
            headers=auth_headers,
        )

        assert response.status_code == 403

    def test_update_nonexistent_report_returns_404(
        self, client, study, admin_auth_headers
    ):
        payload = {**BASE_REPORT_PAYLOAD, "study_id": study.id}
        response = client.put(
            "/api/reports/99999",
            json=payload,
            headers=admin_auth_headers,
        )

        assert response.status_code == 404


class TestDeleteReport:
    """Tests pour DELETE /api/reports/{report_id}."""

    def test_super_admin_can_delete_report(
        self, client, report, admin_auth_headers
    ):
        response = client.delete(
            f"/api/reports/{report.id}",
            headers=admin_auth_headers,
        )

        assert response.status_code == 200
        data = response.json()
        assert "message" in data
        assert "supprim" in data["message"].lower()

    def test_deleted_report_no_longer_accessible(
        self, client, report, admin_auth_headers, auth_headers
    ):
        """Apres suppression, un GET sur le rapport doit retourner 404."""
        client.delete(f"/api/reports/{report.id}", headers=admin_auth_headers)

        get_response = client.get(
            f"/api/reports/{report.id}", headers=auth_headers
        )
        assert get_response.status_code == 404

    def test_regular_user_cannot_delete_report_returns_403(
        self, client, report, auth_headers
    ):
        response = client.delete(
            f"/api/reports/{report.id}",
            headers=auth_headers,
        )

        assert response.status_code == 403

    def test_delete_nonexistent_report_returns_404(
        self, client, admin_auth_headers
    ):
        response = client.delete(
            "/api/reports/99999",
            headers=admin_auth_headers,
        )

        assert response.status_code == 404

    def test_delete_report_without_token_returns_401(self, client, report):
        response = client.delete(f"/api/reports/{report.id}")

        assert response.status_code == 401


class TestDownloadReport:
    """Tests pour POST /api/reports/{report_id}/download."""

    def test_authenticated_user_can_track_download(
        self, client, report, auth_headers
    ):
        initial_count = report.download_count
        response = client.post(
            f"/api/reports/{report.id}/download",
            headers=auth_headers,
        )

        assert response.status_code == 200
        data = response.json()
        assert "message" in data
        assert "file_url" in data
        assert "download_count" in data

    def test_download_increments_counter(
        self, client, report, auth_headers, db
    ):
        """Chaque appel au endpoint download doit incrementer le compteur."""
        client.post(
            f"/api/reports/{report.id}/download",
            headers=auth_headers,
        )
        client.post(
            f"/api/reports/{report.id}/download",
            headers=auth_headers,
        )

        # Verifier que le compteur a ete incremente dans la DB
        from models import Report
        db.expire_all()
        updated_report = db.query(Report).filter(Report.id == report.id).first()
        assert updated_report.download_count >= 2

    def test_download_nonexistent_report_returns_404(
        self, client, auth_headers
    ):
        response = client.post(
            "/api/reports/99999/download",
            headers=auth_headers,
        )

        assert response.status_code == 404

    def test_download_without_token_returns_401(self, client, report):
        response = client.post(f"/api/reports/{report.id}/download")

        assert response.status_code == 401
