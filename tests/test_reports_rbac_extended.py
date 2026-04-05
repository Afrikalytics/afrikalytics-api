"""
Extended RBAC, plan-gating, and new-endpoint tests for the reports module.

Covers gaps not addressed by test_reports.py, test_rbac.py, or test_validation.py:

1. Granular RBAC for UPDATE and DELETE:
   - admin_studies cannot update/delete reports
   - admin_insights cannot update/delete reports
   - admin_reports CAN update and delete reports
   - content_admin CAN update and delete reports

2. New endpoints not yet tested anywhere:
   - GET  /api/reports/study/{id}/type/{type}            — fetch by study + type
   - POST /api/reports/study/{id}/type/{type}/download   — track download by study + type

3. Unavailable report access:
   - GET /api/reports/{id} returns 404 to non-admin for unavailable report
   - GET /api/reports/{id} returns 200 to admin for unavailable report
   - POST /api/reports/{id}/download returns 404 to non-admin for unavailable report
   - POST /api/reports/{id}/download is blocked by plan for premium reports

4. Download counter correctness:
   - Counter starts at 0 and increments atomically
   - Counter is preserved across multiple calls
   - track_download_by_type endpoint also increments the same counter

5. Delete side-effects:
   - Deleting a basic report must null study.report_url_basic
   - Deleting a premium report must null study.report_url_premium

These are RED-phase tests written before verifying behavior against the
running implementation.  Run pytest to see failures; fix implementation to
make them pass.
"""
import os
os.environ.setdefault("SECRET_KEY", "test-secret-key-for-ci")
os.environ.setdefault("DATABASE_URL", "sqlite:///./test.db")

from app.auth import hash_password, create_access_token
from app.models import User, Report, Study


# ---------------------------------------------------------------------------
# Module-level helpers
# ---------------------------------------------------------------------------

def _make_user(db, *, email: str, role: str, is_admin: bool = True, plan: str = "entreprise"):
    user = User(
        email=email,
        full_name=f"Admin {role}",
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


def _headers(user: User) -> dict:
    token = create_access_token(data={"sub": user.email})
    return {"Authorization": f"Bearer {token}"}


BASE_REPORT_PAYLOAD = {
    "study_id": None,  # replaced per test
    "title": "Rapport RBAC Extended Test",
    "description": "Description pour test RBAC etendu.",
    "file_url": "https://cdn.example.com/reports/rbac-ext.pdf",
    "file_name": "rbac-ext.pdf",
    "file_size": 204800,
    "report_type": "basic",
    "is_available": True,
}


def _make_premium_report(db, study_id: int) -> Report:
    """Insert an available premium report and return it."""
    r = Report(
        study_id=study_id,
        title="Rapport Premium Test",
        description="Acces restreint au plan professionnel.",
        file_url="https://cdn.example.com/reports/premium-rbac.pdf",
        file_name="premium-rbac.pdf",
        file_size=512000,
        report_type="premium",
        download_count=0,
        is_available=True,
    )
    db.add(r)
    db.commit()
    db.refresh(r)
    return r


def _make_unavailable_report(db, study_id: int) -> Report:
    """Insert an unavailable (is_available=False) basic report and return it."""
    r = Report(
        study_id=study_id,
        title="Rapport Indisponible",
        description="Non accessible aux non-admins.",
        file_url="https://cdn.example.com/reports/unavailable.pdf",
        file_name="unavailable.pdf",
        file_size=102400,
        report_type="basic",
        download_count=0,
        is_available=False,
    )
    db.add(r)
    db.commit()
    db.refresh(r)
    return r


# ===========================================================================
# 1. Update RBAC — only reports-permitted roles may update
# ===========================================================================

class TestReportUpdateRBAC:
    """PUT /api/reports/{id} — role isolation for update operations."""

    def test_admin_reports_can_update_report(
        self, client, db, study, report
    ):
        """admin_reports must be able to update a report."""
        user = _make_user(db, email="rpt_update_ok@test.com", role="admin_reports")
        payload = {
            **BASE_REPORT_PAYLOAD,
            "study_id": study.id,
            "title": "Mis a Jour par admin_reports",
        }

        response = client.put(
            f"/api/reports/{report.id}",
            json=payload,
            headers=_headers(user),
        )

        assert response.status_code == 200
        assert response.json()["title"] == "Mis a Jour par admin_reports"

    def test_admin_studies_cannot_update_report(
        self, client, db, study, report
    ):
        """admin_studies lacks reports permission — must receive 403 on update."""
        user = _make_user(db, email="studies_upd_rpt@test.com", role="admin_studies")
        payload = {**BASE_REPORT_PAYLOAD, "study_id": study.id}

        response = client.put(
            f"/api/reports/{report.id}",
            json=payload,
            headers=_headers(user),
        )

        assert response.status_code == 403

    def test_admin_insights_cannot_update_report(
        self, client, db, study, report
    ):
        """admin_insights lacks reports permission — must receive 403 on update."""
        user = _make_user(db, email="insights_upd_rpt@test.com", role="admin_insights")
        payload = {**BASE_REPORT_PAYLOAD, "study_id": study.id}

        response = client.put(
            f"/api/reports/{report.id}",
            json=payload,
            headers=_headers(user),
        )

        assert response.status_code == 403

    def test_content_admin_can_update_report(
        self, client, study, report, content_admin_auth_headers
    ):
        """admin_content has reports permission — must be able to update."""
        payload = {
            **BASE_REPORT_PAYLOAD,
            "study_id": study.id,
            "title": "Mis a Jour par content admin",
        }

        response = client.put(
            f"/api/reports/{report.id}",
            json=payload,
            headers=content_admin_auth_headers,
        )

        assert response.status_code == 200
        assert response.json()["title"] == "Mis a Jour par content admin"

    def test_regular_user_cannot_update_report(
        self, client, study, report, auth_headers
    ):
        """Regular user must receive 403 on report update."""
        payload = {**BASE_REPORT_PAYLOAD, "study_id": study.id}

        response = client.put(
            f"/api/reports/{report.id}",
            json=payload,
            headers=auth_headers,
        )

        assert response.status_code == 403

    def test_update_report_without_token_returns_401(
        self, client, study, report
    ):
        """Unauthenticated update must be rejected with 401."""
        payload = {**BASE_REPORT_PAYLOAD, "study_id": study.id}

        response = client.put(f"/api/reports/{report.id}", json=payload)

        assert response.status_code == 401


# ===========================================================================
# 2. Delete RBAC — only reports-permitted roles may delete
# ===========================================================================

class TestReportDeleteRBAC:
    """DELETE /api/reports/{id} — role isolation for delete operations."""

    def test_admin_reports_can_delete_report(
        self, client, db, report
    ):
        """admin_reports must be able to delete a report."""
        user = _make_user(db, email="rpt_del_ok@test.com", role="admin_reports")

        response = client.delete(
            f"/api/reports/{report.id}",
            headers=_headers(user),
        )

        assert response.status_code == 200

    def test_admin_studies_cannot_delete_report(
        self, client, db, report
    ):
        """admin_studies lacks reports permission — must receive 403 on delete."""
        user = _make_user(db, email="studies_del_rpt@test.com", role="admin_studies")

        response = client.delete(
            f"/api/reports/{report.id}",
            headers=_headers(user),
        )

        assert response.status_code == 403

    def test_admin_insights_cannot_delete_report(
        self, client, db, report
    ):
        """admin_insights lacks reports permission — must receive 403 on delete."""
        user = _make_user(db, email="insights_del_rpt@test.com", role="admin_insights")

        response = client.delete(
            f"/api/reports/{report.id}",
            headers=_headers(user),
        )

        assert response.status_code == 403

    def test_content_admin_can_delete_report(
        self, client, report, content_admin_auth_headers
    ):
        """admin_content has reports permission — must be able to delete."""
        response = client.delete(
            f"/api/reports/{report.id}",
            headers=content_admin_auth_headers,
        )

        assert response.status_code == 200


# ===========================================================================
# 3. GET /api/reports/study/{id}/type/{type}
# ===========================================================================

class TestGetReportByStudyAndType:
    """
    GET /api/reports/study/{study_id}/type/{report_type}
    This endpoint is defined in the router but not tested in any existing file.
    """

    def test_get_basic_report_by_study_and_type(
        self, client, study, report, auth_headers
    ):
        """
        A basic user can retrieve a basic report by study ID and type.
        The fixture 'report' is of type 'basic'.
        """
        response = client.get(
            f"/api/reports/study/{study.id}/type/basic",
            headers=auth_headers,
        )

        assert response.status_code == 200
        data = response.json()
        assert data["study_id"] == study.id
        assert data["report_type"] == "basic"

    def test_get_nonexistent_type_for_study_returns_404(
        self, client, study, report, auth_headers
    ):
        """
        Requesting a report type that does not exist for this study must return 404.
        The fixture 'report' is basic, so requesting 'premium' should return 404.
        """
        response = client.get(
            f"/api/reports/study/{study.id}/type/premium",
            headers=auth_headers,
        )

        assert response.status_code == 404

    def test_get_report_by_type_nonexistent_study_returns_404(
        self, client, auth_headers
    ):
        """Requesting any type for a nonexistent study must return 404."""
        response = client.get(
            "/api/reports/study/99999/type/basic",
            headers=auth_headers,
        )

        assert response.status_code == 404

    def test_basic_user_blocked_from_premium_report_by_type(
        self, client, db, study, auth_headers
    ):
        """
        A basic-plan user trying to access a premium report via the
        study+type endpoint must receive 403.
        """
        _make_premium_report(db, study.id)

        response = client.get(
            f"/api/reports/study/{study.id}/type/premium",
            headers=auth_headers,
        )

        assert response.status_code == 403

    def test_enterprise_user_can_access_premium_report_by_type(
        self, client, db, study, enterprise_auth_headers
    ):
        """enterprise plan allows access to premium reports via study+type."""
        _make_premium_report(db, study.id)

        response = client.get(
            f"/api/reports/study/{study.id}/type/premium",
            headers=enterprise_auth_headers,
        )

        assert response.status_code == 200
        assert response.json()["report_type"] == "premium"

    def test_get_report_by_study_and_type_without_token_returns_401(
        self, client, study, report
    ):
        """Unauthenticated request must be rejected with 401."""
        response = client.get(f"/api/reports/study/{study.id}/type/basic")

        assert response.status_code == 401


# ===========================================================================
# 4. POST /api/reports/study/{id}/type/{type}/download
# ===========================================================================

class TestDownloadByStudyAndType:
    """
    POST /api/reports/study/{study_id}/type/{report_type}/download
    This endpoint is defined in the router but not tested in any existing file.
    """

    def test_download_by_study_and_type_increments_counter(
        self, client, db, study, report, auth_headers
    ):
        """
        Calling the download-by-type endpoint must increment download_count.
        The fixture 'report' is of type 'basic'.
        """
        initial_count = report.download_count

        response = client.post(
            f"/api/reports/study/{study.id}/type/basic/download",
            headers=auth_headers,
        )

        assert response.status_code == 200
        data = response.json()
        assert "download_count" in data
        assert "file_url" in data
        assert data["download_count"] > initial_count

    def test_download_by_type_counter_persisted_in_db(
        self, client, db, study, report, auth_headers
    ):
        """Counter increment via type endpoint must be persisted in the DB."""
        from sqlalchemy import select

        client.post(
            f"/api/reports/study/{study.id}/type/basic/download",
            headers=auth_headers,
        )
        client.post(
            f"/api/reports/study/{study.id}/type/basic/download",
            headers=auth_headers,
        )

        db.expire_all()
        updated = db.execute(
            select(Report).where(Report.id == report.id)
        ).scalar_one_or_none()

        assert updated is not None
        assert updated.download_count >= 2

    def test_download_by_type_nonexistent_study_returns_404(
        self, client, auth_headers
    ):
        """Download for a nonexistent study + type must return 404."""
        response = client.post(
            "/api/reports/study/99999/type/basic/download",
            headers=auth_headers,
        )

        assert response.status_code == 404

    def test_download_by_type_nonexistent_type_returns_404(
        self, client, study, report, auth_headers
    ):
        """
        Requesting download for a type that has no report for this study must
        return 404.  The fixture 'report' is basic, so 'premium' should 404.
        """
        response = client.post(
            f"/api/reports/study/{study.id}/type/premium/download",
            headers=auth_headers,
        )

        assert response.status_code == 404

    def test_basic_user_blocked_from_premium_download_by_type(
        self, client, db, study, auth_headers
    ):
        """
        A basic-plan user attempting to download a premium report via the
        type endpoint must be blocked with 403.
        """
        _make_premium_report(db, study.id)

        response = client.post(
            f"/api/reports/study/{study.id}/type/premium/download",
            headers=auth_headers,
        )

        assert response.status_code == 403

    def test_download_by_type_without_token_returns_401(
        self, client, study, report
    ):
        """Unauthenticated download must be rejected with 401."""
        response = client.post(
            f"/api/reports/study/{study.id}/type/basic/download"
        )

        assert response.status_code == 401

    def test_download_by_type_response_contains_message(
        self, client, study, report, auth_headers
    ):
        """The response envelope must contain a message field."""
        response = client.post(
            f"/api/reports/study/{study.id}/type/basic/download",
            headers=auth_headers,
        )

        assert response.status_code == 200
        assert "message" in response.json()


# ===========================================================================
# 5. Unavailable report access
# ===========================================================================

class TestUnavailableReportAccess:
    """
    Reports with is_available=False must be invisible to regular users
    but accessible to admin users.
    """

    def test_unavailable_report_get_returns_404_for_regular_user(
        self, client, db, study, auth_headers
    ):
        """GET /api/reports/{id} must return 404 to non-admin for unavailable report."""
        unavail = _make_unavailable_report(db, study.id)

        response = client.get(
            f"/api/reports/{unavail.id}", headers=auth_headers
        )

        assert response.status_code == 404

    def test_unavailable_report_get_returns_200_for_admin(
        self, client, db, study, admin_auth_headers
    ):
        """GET /api/reports/{id} must return 200 to admin for unavailable report."""
        unavail = _make_unavailable_report(db, study.id)

        response = client.get(
            f"/api/reports/{unavail.id}", headers=admin_auth_headers
        )

        assert response.status_code == 200
        assert response.json()["is_available"] is False

    def test_unavailable_report_download_returns_404_for_regular_user(
        self, client, db, study, auth_headers
    ):
        """POST /api/reports/{id}/download must return 404 to non-admin for unavailable."""
        unavail = _make_unavailable_report(db, study.id)

        response = client.post(
            f"/api/reports/{unavail.id}/download", headers=auth_headers
        )

        assert response.status_code == 404

    def test_unavailable_report_excluded_from_list(
        self, client, db, study, auth_headers
    ):
        """Unavailable reports must not appear in GET /api/reports items."""
        unavail = _make_unavailable_report(db, study.id)

        response = client.get("/api/reports", headers=auth_headers)

        assert response.status_code == 200
        data = response.json()
        items = data["items"] if isinstance(data, dict) and "items" in data else data
        ids = [r["id"] for r in items]
        assert unavail.id not in ids


# ===========================================================================
# 6. Delete side-effects on parent Study
# ===========================================================================

class TestReportDeleteSideEffects:
    """
    Deleting a report must null the corresponding report_url_* field on the
    parent Study.  This is handled at the end of the delete_report router.
    """

    def _make_study_with_urls(self, db) -> Study:
        """Create a study pre-populated with report URL columns."""
        s = Study(
            title="Etude Avec URLs",
            description="Pour tester les effets de bord de la suppression.",
            category="Test",
            status="Ouvert",
            is_active=True,
            report_url_basic="https://cdn.example.com/basic.pdf",
            report_url_premium="https://cdn.example.com/premium.pdf",
        )
        db.add(s)
        db.commit()
        db.refresh(s)
        return s

    def test_delete_basic_report_nulls_study_report_url_basic(
        self, client, db, admin_auth_headers
    ):
        """
        After deleting a basic report, the parent Study.report_url_basic
        column must be set to None.
        """
        from sqlalchemy import select

        s = self._make_study_with_urls(db)
        basic_report = Report(
            study_id=s.id,
            title="Basic Report Side Effect",
            description="For side effect test.",
            file_url="https://cdn.example.com/basic-side.pdf",
            file_name="basic-side.pdf",
            file_size=1024,
            report_type="basic",
            download_count=0,
            is_available=True,
        )
        db.add(basic_report)
        db.commit()
        db.refresh(basic_report)

        response = client.delete(
            f"/api/reports/{basic_report.id}",
            headers=admin_auth_headers,
        )

        assert response.status_code == 200

        db.expire_all()
        updated_study = db.execute(
            select(Study).where(Study.id == s.id)
        ).scalar_one_or_none()

        assert updated_study is not None
        assert updated_study.report_url_basic is None, (
            "Deleting a basic report must null study.report_url_basic"
        )

    def test_delete_premium_report_nulls_study_report_url_premium(
        self, client, db, admin_auth_headers
    ):
        """
        After deleting a premium report, the parent Study.report_url_premium
        column must be set to None.
        """
        from sqlalchemy import select

        s = self._make_study_with_urls(db)
        premium_report = Report(
            study_id=s.id,
            title="Premium Report Side Effect",
            description="For side effect test.",
            file_url="https://cdn.example.com/premium-side.pdf",
            file_name="premium-side.pdf",
            file_size=2048,
            report_type="premium",
            download_count=0,
            is_available=True,
        )
        db.add(premium_report)
        db.commit()
        db.refresh(premium_report)

        response = client.delete(
            f"/api/reports/{premium_report.id}",
            headers=admin_auth_headers,
        )

        assert response.status_code == 200

        db.expire_all()
        updated_study = db.execute(
            select(Study).where(Study.id == s.id)
        ).scalar_one_or_none()

        assert updated_study is not None
        assert updated_study.report_url_premium is None, (
            "Deleting a premium report must null study.report_url_premium"
        )

    def test_delete_report_without_study_link_does_not_fail(
        self, client, db, admin_auth_headers
    ):
        """
        Deleting a report whose study_id is None (orphaned) must not crash
        — the router guards with 'if report.study_id'.
        """
        orphan = Report(
            study_id=None,
            title="Orphan Report",
            description="No parent study.",
            file_url="https://cdn.example.com/orphan.pdf",
            file_name="orphan.pdf",
            file_size=512,
            report_type="basic",
            download_count=0,
            is_available=True,
        )
        db.add(orphan)
        db.commit()
        db.refresh(orphan)

        response = client.delete(
            f"/api/reports/{orphan.id}",
            headers=admin_auth_headers,
        )

        assert response.status_code == 200
