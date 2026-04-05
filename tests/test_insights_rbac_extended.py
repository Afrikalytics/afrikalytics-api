"""
Extended RBAC and visibility tests for the insights module.

Covers gaps not addressed in test_insights.py, test_rbac.py, or test_validation.py:

1. Granular RBAC for UPDATE and DELETE operations:
   - admin_studies cannot update/delete insights
   - admin_reports cannot update/delete insights
   - admin_insights CAN update and delete insights
   - content_admin CAN update and delete insights

2. Unpublished insight visibility:
   - Unpublished insight is NOT returned via GET /api/insights (list)
   - GET /api/insights/{id} returns 404 to a regular user for an unpublished insight
   - GET /api/insights/{id} returns the insight to an admin for an unpublished insight

3. Insight linked to a deleted/nonexistent study:
   - Creating an insight with a nonexistent study_id must fail
   - GET /api/insights/study/{id} returns 404 when the study has no published insight

These are RED-phase tests written before confirming behavior against the
running implementation.  Run pytest to see them fail, then verify/adjust
implementation to make them pass.
"""
import os
os.environ.setdefault("SECRET_KEY", "test-secret-key-for-ci")
os.environ.setdefault("DATABASE_URL", "sqlite:///./test.db")

from app.auth import hash_password, create_access_token
from app.models import User, Insight


# ---------------------------------------------------------------------------
# Helpers shared by this module
# ---------------------------------------------------------------------------

def _make_user(db, *, email: str, role: str):
    """Insert an admin user with a specific narrow role and return it."""
    user = User(
        email=email,
        full_name=f"Admin {role}",
        hashed_password=hash_password("Password123!"),
        plan="entreprise",
        is_active=True,
        is_admin=True,
        admin_role=role,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def _headers(user: User) -> dict:
    token = create_access_token(data={"sub": user.email})
    return {"Authorization": f"Bearer {token}"}


BASE_INSIGHT_PAYLOAD = {
    "study_id": None,  # replaced per test
    "title": "Insight Mise a Jour RBAC",
    "summary": "Resume.",
    "key_findings": "Resultat.",
    "recommendations": "Recommandation.",
    "author": "Equipe Test",
    "images": [],
    "is_published": True,
}


# ===========================================================================
# 1. Update RBAC — only insights-permitted roles may update
# ===========================================================================

class TestInsightUpdateRBAC:
    """PUT /api/insights/{id} — role isolation for update operations."""

    def test_admin_insights_can_update_insight(
        self, client, db, study, insight
    ):
        """admin_insights role must be able to update an insight."""
        user = _make_user(db, email="ins_update_ok@test.com", role="admin_insights")
        payload = {**BASE_INSIGHT_PAYLOAD, "study_id": study.id, "title": "Updated by admin_insights"}

        response = client.put(
            f"/api/insights/{insight.id}",
            json=payload,
            headers=_headers(user),
        )

        assert response.status_code == 200
        assert response.json()["title"] == "Updated by admin_insights"

    def test_admin_studies_cannot_update_insight(
        self, client, db, study, insight
    ):
        """admin_studies lacks insights permission — must receive 403 on update."""
        user = _make_user(db, email="studies_upd_ins@test.com", role="admin_studies")
        payload = {**BASE_INSIGHT_PAYLOAD, "study_id": study.id}

        response = client.put(
            f"/api/insights/{insight.id}",
            json=payload,
            headers=_headers(user),
        )

        assert response.status_code == 403

    def test_admin_reports_cannot_update_insight(
        self, client, db, study, insight
    ):
        """admin_reports lacks insights permission — must receive 403 on update."""
        user = _make_user(db, email="reports_upd_ins@test.com", role="admin_reports")
        payload = {**BASE_INSIGHT_PAYLOAD, "study_id": study.id}

        response = client.put(
            f"/api/insights/{insight.id}",
            json=payload,
            headers=_headers(user),
        )

        assert response.status_code == 403

    def test_content_admin_can_update_insight(
        self, client, study, insight, content_admin_auth_headers
    ):
        """admin_content has insights permission — must be able to update."""
        payload = {
            **BASE_INSIGHT_PAYLOAD,
            "study_id": study.id,
            "title": "Updated by content admin",
        }

        response = client.put(
            f"/api/insights/{insight.id}",
            json=payload,
            headers=content_admin_auth_headers,
        )

        assert response.status_code == 200
        assert response.json()["title"] == "Updated by content admin"

    def test_regular_user_cannot_update_insight(
        self, client, study, insight, auth_headers
    ):
        """Regular user must receive 403 on insight update (already in test_insights but verified here for completeness)."""
        payload = {**BASE_INSIGHT_PAYLOAD, "study_id": study.id}

        response = client.put(
            f"/api/insights/{insight.id}",
            json=payload,
            headers=auth_headers,
        )

        assert response.status_code == 403

    def test_update_insight_without_token_returns_401(
        self, client, study, insight
    ):
        """Unauthenticated update must be rejected with 401."""
        payload = {**BASE_INSIGHT_PAYLOAD, "study_id": study.id}

        response = client.put(f"/api/insights/{insight.id}", json=payload)

        assert response.status_code == 401


# ===========================================================================
# 2. Delete RBAC — only insights-permitted roles may delete
# ===========================================================================

class TestInsightDeleteRBAC:
    """DELETE /api/insights/{id} — role isolation for delete operations."""

    def test_admin_insights_can_delete_insight(
        self, client, db, insight
    ):
        """admin_insights must be able to delete an insight."""
        user = _make_user(db, email="ins_del_ok@test.com", role="admin_insights")

        response = client.delete(
            f"/api/insights/{insight.id}",
            headers=_headers(user),
        )

        assert response.status_code == 200

    def test_admin_studies_cannot_delete_insight(
        self, client, db, insight
    ):
        """admin_studies lacks insights permission — must receive 403 on delete."""
        user = _make_user(db, email="studies_del_ins@test.com", role="admin_studies")

        response = client.delete(
            f"/api/insights/{insight.id}",
            headers=_headers(user),
        )

        assert response.status_code == 403

    def test_admin_reports_cannot_delete_insight(
        self, client, db, insight
    ):
        """admin_reports lacks insights permission — must receive 403 on delete."""
        user = _make_user(db, email="reports_del_ins@test.com", role="admin_reports")

        response = client.delete(
            f"/api/insights/{insight.id}",
            headers=_headers(user),
        )

        assert response.status_code == 403

    def test_content_admin_can_delete_insight(
        self, client, insight, content_admin_auth_headers
    ):
        """admin_content has insights permission — must be able to delete."""
        response = client.delete(
            f"/api/insights/{insight.id}",
            headers=content_admin_auth_headers,
        )

        assert response.status_code == 200


# ===========================================================================
# 3. Unpublished insight visibility
# ===========================================================================

class TestUnpublishedInsightVisibility:
    """
    The router contains:
        if not insight.is_published and not check_admin_permission(user, "insights"):
            raise HTTPException(404)

    These tests verify this gate is actually enforced.
    """

    def _create_unpublished(self, db, study_id: int) -> Insight:
        """Insert an unpublished insight directly into the DB."""
        unpublished = Insight(
            study_id=study_id,
            title="Insight Non Publie",
            summary="Ce insight ne doit pas etre visible.",
            key_findings="Aucun.",
            recommendations="Aucune.",
            author="Equipe Test",
            is_published=False,
        )
        db.add(unpublished)
        db.commit()
        db.refresh(unpublished)
        return unpublished

    def test_unpublished_insight_excluded_from_list_for_regular_user(
        self, client, db, study, auth_headers
    ):
        """
        GET /api/insights must NOT include unpublished insights in the items
        list for regular users.
        """
        unpublished = self._create_unpublished(db, study.id)

        response = client.get("/api/insights", headers=auth_headers)

        assert response.status_code == 200
        data = response.json()
        # Support both plain list and paginated envelope
        items = data["items"] if isinstance(data, dict) and "items" in data else data
        ids = [i["id"] for i in items]
        assert unpublished.id not in ids

    def test_unpublished_insight_get_by_id_returns_404_for_regular_user(
        self, client, db, study, auth_headers
    ):
        """
        GET /api/insights/{id} must return 404 when the insight is unpublished
        and the caller is a regular user.
        """
        unpublished = self._create_unpublished(db, study.id)

        response = client.get(
            f"/api/insights/{unpublished.id}", headers=auth_headers
        )

        assert response.status_code == 404

    def test_unpublished_insight_get_by_id_visible_to_admin(
        self, client, db, study, admin_auth_headers
    ):
        """
        GET /api/insights/{id} must return the insight to an admin even when
        is_published=False.
        """
        unpublished = self._create_unpublished(db, study.id)

        response = client.get(
            f"/api/insights/{unpublished.id}", headers=admin_auth_headers
        )

        assert response.status_code == 200
        data = response.json()
        assert data["id"] == unpublished.id
        assert data["is_published"] is False

    def test_unpublished_insight_get_by_id_visible_to_insights_admin(
        self, client, db, study
    ):
        """
        admin_insights can also see unpublished insights via GET /api/insights/{id}.
        """
        user = _make_user(db, email="ins_see_draft@test.com", role="admin_insights")
        unpublished = self._create_unpublished(db, study.id)

        response = client.get(
            f"/api/insights/{unpublished.id}", headers=_headers(user)
        )

        assert response.status_code == 200
        assert response.json()["is_published"] is False

    def test_get_insight_by_study_returns_404_when_no_published_insight(
        self, client, db, study, auth_headers
    ):
        """
        GET /api/insights/study/{id} must return 404 when the study exists
        but has no published insight (only unpublished ones).
        """
        self._create_unpublished(db, study.id)

        response = client.get(
            f"/api/insights/study/{study.id}", headers=auth_headers
        )

        assert response.status_code == 404

    def test_admin_can_publish_insight_then_visible_to_user(
        self, client, db, study, auth_headers, admin_auth_headers
    ):
        """
        After an admin publishes an insight (sets is_published=True), a
        regular user must be able to retrieve it.
        """
        unpublished = self._create_unpublished(db, study.id)

        # Admin publishes it
        update_payload = {
            "study_id": study.id,
            "title": unpublished.title,
            "summary": unpublished.summary,
            "key_findings": unpublished.key_findings,
            "recommendations": unpublished.recommendations,
            "author": unpublished.author,
            "images": [],
            "is_published": True,
        }
        pub_response = client.put(
            f"/api/insights/{unpublished.id}",
            json=update_payload,
            headers=admin_auth_headers,
        )
        assert pub_response.status_code == 200

        # Now the regular user should see it
        user_response = client.get(
            f"/api/insights/{unpublished.id}", headers=auth_headers
        )
        assert user_response.status_code == 200
        assert user_response.json()["is_published"] is True


# ===========================================================================
# 4. Insight linked to nonexistent study
# ===========================================================================

class TestInsightStudyLinkage:
    """
    Insights must be correctly associated with their parent study.
    Creating an insight referencing a nonexistent study should fail or
    return an integrity error.
    """

    def test_create_insight_with_nonexistent_study_id_fails(
        self, client, admin_auth_headers
    ):
        """
        Posting an insight with a study_id that does not exist in the DB
        must not succeed with 201.  Acceptable codes are 400, 404, or 422.
        """
        payload = {
            **BASE_INSIGHT_PAYLOAD,
            "study_id": 99999,
        }

        response = client.post(
            "/api/insights",
            json=payload,
            headers=admin_auth_headers,
        )

        # Must not silently create an orphaned insight
        assert response.status_code not in (200, 201), (
            "Creating an insight with a nonexistent study_id must fail"
        )

    def test_get_insight_by_nonexistent_study_returns_404(
        self, client, auth_headers
    ):
        """GET /api/insights/study/99999 must return 404 (no study, no insight)."""
        response = client.get(
            "/api/insights/study/99999", headers=auth_headers
        )

        assert response.status_code == 404

    def test_images_field_returns_as_list_not_json_string(
        self, client, insight, auth_headers
    ):
        """
        The images field is stored as JSON text in the DB but the router's
        convert_insight_images() helper must return it as a Python list,
        not a raw JSON string.
        """
        response = client.get(
            f"/api/insights/{insight.id}", headers=auth_headers
        )

        assert response.status_code == 200
        data = response.json()
        assert "images" in data
        assert isinstance(data["images"], list), (
            "images must be deserialized from JSON string to list by the router"
        )
