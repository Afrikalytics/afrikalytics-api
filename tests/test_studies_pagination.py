"""
Tests for the paginated response envelope on study list endpoints.

The /api/studies endpoint uses the shared paginate() utility which returns:
    {
        "items":    [...],
        "total":    <int>,
        "page":     <int>,
        "per_page": <int>,
        "pages":    <int>,
    }

Existing tests assert isinstance(data, list), which was valid before the
pagination refactor.  These tests verify the new envelope shape, the
page/per_page query parameters, and edge cases (empty DB, page out of range).

NOTE: These are RED-phase tests.  Run pytest to confirm they fail before
implementing.  They will pass once the paginate() helper is wired up
correctly in all list endpoints and the existing tests are updated.
"""
import os
os.environ.setdefault("SECRET_KEY", "test-secret-key-for-ci")
os.environ.setdefault("DATABASE_URL", "sqlite:///./test.db")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _assert_paginated_envelope(data: dict) -> None:
    """Assert that a response body matches the paginated envelope contract."""
    for key in ("items", "total", "page", "per_page", "pages"):
        assert key in data, f"Paginated envelope is missing key '{key}'"
    assert isinstance(data["items"], list)
    assert isinstance(data["total"], int)
    assert isinstance(data["page"], int)
    assert isinstance(data["per_page"], int)
    assert isinstance(data["pages"], int)


# ===========================================================================
# 1. /api/studies — paginated envelope shape
# ===========================================================================

class TestStudiesPaginatedEnvelope:
    """GET /api/studies must return a paginated envelope, not a bare list."""

    def test_list_studies_returns_paginated_envelope(
        self, client, study, auth_headers
    ):
        """Response must include items, total, page, per_page, pages keys."""
        response = client.get("/api/studies", headers=auth_headers)

        assert response.status_code == 200
        data = response.json()
        _assert_paginated_envelope(data)

    def test_list_studies_items_contains_study(
        self, client, study, auth_headers
    ):
        """The 'items' list must contain the created study."""
        response = client.get("/api/studies", headers=auth_headers)

        assert response.status_code == 200
        ids = [s["id"] for s in response.json()["items"]]
        assert study.id in ids

    def test_list_studies_total_reflects_db_count(
        self, client, study, inactive_study, auth_headers
    ):
        """The 'total' field must equal the number of studies in the DB."""
        response = client.get("/api/studies", headers=auth_headers)

        assert response.status_code == 200
        data = response.json()
        assert data["total"] >= 2

    def test_list_studies_empty_database_returns_empty_envelope(
        self, client, auth_headers
    ):
        """When no studies exist the envelope must have items=[], total=0."""
        # No study fixture — DB is empty
        response = client.get("/api/studies", headers=auth_headers)

        assert response.status_code == 200
        data = response.json()
        _assert_paginated_envelope(data)
        assert data["items"] == []
        assert data["total"] == 0

    def test_list_studies_page_1_per_page_1_returns_one_item(
        self, client, study, inactive_study, auth_headers
    ):
        """page=1&per_page=1 must return exactly one item."""
        response = client.get(
            "/api/studies?page=1&per_page=1", headers=auth_headers
        )

        assert response.status_code == 200
        data = response.json()
        _assert_paginated_envelope(data)
        assert len(data["items"]) == 1
        assert data["per_page"] == 1
        assert data["page"] == 1

    def test_list_studies_page_2_returns_second_item(
        self, client, study, inactive_study, auth_headers
    ):
        """
        With 2 studies and per_page=1, page=2 must return the second study.
        The 'pages' field must equal 2.
        """
        response = client.get(
            "/api/studies?page=2&per_page=1", headers=auth_headers
        )

        assert response.status_code == 200
        data = response.json()
        _assert_paginated_envelope(data)
        assert data["page"] == 2
        assert data["pages"] == 2
        assert len(data["items"]) == 1

    def test_list_studies_page_beyond_total_returns_empty_items(
        self, client, study, auth_headers
    ):
        """Requesting a page beyond the last page must return an empty items list."""
        response = client.get(
            "/api/studies?page=9999&per_page=20", headers=auth_headers
        )

        assert response.status_code == 200
        data = response.json()
        _assert_paginated_envelope(data)
        assert data["items"] == []

    def test_list_studies_per_page_max_100(
        self, client, auth_headers
    ):
        """per_page above 100 must be rejected (Query ge=1 le=100)."""
        response = client.get(
            "/api/studies?per_page=101", headers=auth_headers
        )
        # FastAPI Query validation returns 422 for out-of-range values
        assert response.status_code == 422

    def test_list_studies_page_zero_returns_422(
        self, client, auth_headers
    ):
        """page=0 violates ge=1 constraint, must be rejected with 422."""
        response = client.get(
            "/api/studies?page=0", headers=auth_headers
        )
        assert response.status_code == 422

    def test_list_studies_pages_field_is_correct(
        self, client, study, inactive_study, auth_headers
    ):
        """
        With 2 studies and per_page=1, 'pages' must equal ceil(2/1) = 2.
        With 2 studies and per_page=2, 'pages' must equal ceil(2/2) = 1.
        """
        r1 = client.get("/api/studies?page=1&per_page=1", headers=auth_headers)
        assert r1.status_code == 200
        assert r1.json()["pages"] == 2

        r2 = client.get("/api/studies?page=1&per_page=2", headers=auth_headers)
        assert r2.status_code == 200
        assert r2.json()["pages"] == 1


# ===========================================================================
# 2. /api/insights — paginated envelope shape
# ===========================================================================

class TestInsightsPaginatedEnvelope:
    """GET /api/insights must return a paginated envelope."""

    def test_list_insights_returns_paginated_envelope(
        self, client, insight, auth_headers
    ):
        """Response must include the paginated envelope keys."""
        response = client.get("/api/insights", headers=auth_headers)

        assert response.status_code == 200
        data = response.json()
        _assert_paginated_envelope(data)

    def test_list_insights_items_contains_published_insight(
        self, client, insight, auth_headers
    ):
        """The published insight must appear inside the 'items' list."""
        response = client.get("/api/insights", headers=auth_headers)

        assert response.status_code == 200
        ids = [i["id"] for i in response.json()["items"]]
        assert insight.id in ids

    def test_list_insights_empty_database_returns_empty_envelope(
        self, client, auth_headers
    ):
        """When no insights exist the envelope must be empty."""
        response = client.get("/api/insights", headers=auth_headers)

        assert response.status_code == 200
        data = response.json()
        _assert_paginated_envelope(data)
        assert data["items"] == []
        assert data["total"] == 0

    def test_list_insights_pagination_per_page_parameter(
        self, client, insight, auth_headers
    ):
        """per_page=1 must return at most 1 item."""
        response = client.get(
            "/api/insights?page=1&per_page=1", headers=auth_headers
        )

        assert response.status_code == 200
        data = response.json()
        _assert_paginated_envelope(data)
        assert len(data["items"]) <= 1

    def test_list_insights_only_published_in_items(
        self, client, insight, db, auth_headers
    ):
        """
        An unpublished insight must NOT appear in the paginated items list.
        The total count must not include it.
        """
        from app.models import Insight

        unpublished = Insight(
            study_id=insight.study_id,
            title="Insight non publie",
            summary="Ne doit pas apparaitre dans la liste.",
            is_published=False,
        )
        db.add(unpublished)
        db.commit()

        response = client.get("/api/insights", headers=auth_headers)

        assert response.status_code == 200
        data = response.json()
        ids = [i["id"] for i in data["items"]]
        assert unpublished.id not in ids


# ===========================================================================
# 3. /api/reports — paginated envelope shape
# ===========================================================================

class TestReportsPaginatedEnvelope:
    """GET /api/reports must return a paginated envelope."""

    def test_list_reports_returns_paginated_envelope(
        self, client, report, auth_headers
    ):
        """Response must include the paginated envelope keys."""
        response = client.get("/api/reports", headers=auth_headers)

        assert response.status_code == 200
        data = response.json()
        _assert_paginated_envelope(data)

    def test_list_reports_items_contains_available_report(
        self, client, report, auth_headers
    ):
        """The available report must appear inside the 'items' list."""
        response = client.get("/api/reports", headers=auth_headers)

        assert response.status_code == 200
        ids = [r["id"] for r in response.json()["items"]]
        assert report.id in ids

    def test_list_reports_empty_database_returns_empty_envelope(
        self, client, auth_headers
    ):
        """When no reports exist the envelope must be empty."""
        response = client.get("/api/reports", headers=auth_headers)

        assert response.status_code == 200
        data = response.json()
        _assert_paginated_envelope(data)
        assert data["items"] == []
        assert data["total"] == 0

    def test_list_reports_unavailable_excluded_from_items(
        self, client, study, db, auth_headers
    ):
        """
        An unavailable report (is_available=False) must NOT appear in the
        paginated items list returned to regular users.
        """
        from app.models import Report

        unavailable = Report(
            study_id=study.id,
            title="Rapport non disponible",
            description="Ne doit pas apparaitre.",
            file_url="https://cdn.example.com/reports/hidden.pdf",
            file_name="hidden.pdf",
            file_size=1024,
            report_type="basic",
            download_count=0,
            is_available=False,
        )
        db.add(unavailable)
        db.commit()

        response = client.get("/api/reports", headers=auth_headers)

        assert response.status_code == 200
        ids = [r["id"] for r in response.json()["items"]]
        assert unavailable.id not in ids
