"""
Tests for the integrations router — /api/integrations/*
Covers: API key CRUD, embed data, embed widget.
"""
import pytest
from unittest.mock import patch, MagicMock

from app.models import ApiKey, Study, StudyDataset
from app.security import generate_api_key, hash_api_key
from app.auth import create_access_token


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def pro_user(db):
    """Create a user with plan=professionnel."""
    from app.auth import hash_password

    user = __import__("app.models", fromlist=["User"]).User(
        email="pro@example.com",
        full_name="Pro User",
        hashed_password=hash_password("ProPassword123!"),
        plan="professionnel",
        is_active=True,
        is_admin=False,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


@pytest.fixture()
def pro_auth_headers(pro_user):
    token = create_access_token(data={"sub": pro_user.email})
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture()
def api_key_for_pro(db, pro_user):
    """Create an active API key for the pro user and return (raw_key, db_object)."""
    raw_key, key_hash, key_prefix = generate_api_key()
    api_key = ApiKey(
        user_id=pro_user.id,
        key_hash=key_hash,
        key_prefix=key_prefix,
        name="Test Key",
        is_active=True,
        permissions=["read"],
    )
    db.add(api_key)
    db.commit()
    db.refresh(api_key)
    return raw_key, api_key


@pytest.fixture()
def study_with_dataset(db):
    """Create an active study with a dataset attached."""
    study = Study(
        title="Etude Embed Test",
        description="Test description",
        category="Finance",
        status="Ouvert",
        is_active=True,
    )
    db.add(study)
    db.flush()

    dataset = StudyDataset(
        study_id=study.id,
        data=[
            {"region": "Dakar", "revenue": 50000},
            {"region": "Abidjan", "revenue": 45000},
        ],
        columns=["region", "revenue"],
        row_count=2,
    )
    db.add(dataset)
    db.commit()
    db.refresh(study)
    return study


# ---------------------------------------------------------------------------
# POST /api/integrations/keys — Create API key
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestCreateApiKey:
    def test_create_api_key_success(self, client, pro_auth_headers):
        resp = client.post(
            "/api/integrations/keys",
            json={"name": "Mon site", "permissions": ["read"], "allowed_origins": []},
            headers=pro_auth_headers,
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["name"] == "Mon site"
        assert data["key"].startswith("ak_")
        assert len(data["key_prefix"]) == 8
        assert data["is_active"] is True

    def test_create_api_key_basic_user_forbidden(self, client, auth_headers):
        """Basic plan users cannot create API keys."""
        resp = client.post(
            "/api/integrations/keys",
            json={"name": "test", "permissions": ["read"], "allowed_origins": []},
            headers=auth_headers,
        )
        assert resp.status_code == 403
        assert "Professionnel" in resp.json()["detail"] or "professionnel" in resp.json()["detail"].lower()

    def test_create_api_key_enterprise_user(self, client, enterprise_auth_headers):
        """Enterprise plan users can create API keys."""
        resp = client.post(
            "/api/integrations/keys",
            json={"name": "Enterprise key", "permissions": ["read", "write"], "allowed_origins": []},
            headers=enterprise_auth_headers,
        )
        assert resp.status_code == 201

    def test_create_api_key_invalid_permission(self, client, pro_auth_headers):
        resp = client.post(
            "/api/integrations/keys",
            json={"name": "test", "permissions": ["admin"], "allowed_origins": []},
            headers=pro_auth_headers,
        )
        assert resp.status_code == 400
        assert "invalide" in resp.json()["detail"].lower()

    def test_create_api_key_max_limit(self, client, db, pro_user, pro_auth_headers):
        """Cannot create more than 10 API keys."""
        for i in range(10):
            _, kh, kp = generate_api_key()
            db.add(ApiKey(
                user_id=pro_user.id, key_hash=kh, key_prefix=kp,
                name=f"key_{i}", is_active=True, permissions=["read"],
            ))
        db.commit()

        resp = client.post(
            "/api/integrations/keys",
            json={"name": "11th key", "permissions": ["read"], "allowed_origins": []},
            headers=pro_auth_headers,
        )
        assert resp.status_code == 400
        assert "Limite" in resp.json()["detail"]

    def test_create_api_key_unauthorized(self, client):
        resp = client.post(
            "/api/integrations/keys",
            json={"name": "test", "permissions": ["read"], "allowed_origins": []},
        )
        assert resp.status_code == 401


# ---------------------------------------------------------------------------
# GET /api/integrations/keys — List API keys
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestListApiKeys:
    def test_list_keys_empty(self, client, pro_auth_headers):
        resp = client.get("/api/integrations/keys", headers=pro_auth_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["keys"] == []
        assert data["total"] == 0

    def test_list_keys_with_data(self, client, pro_auth_headers, api_key_for_pro):
        resp = client.get("/api/integrations/keys", headers=pro_auth_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 1
        key_data = data["keys"][0]
        assert key_data["name"] == "Test Key"
        assert len(key_data["key_prefix"]) == 8
        # Full key must NOT be returned in list
        assert "key" not in key_data or key_data.get("key") is None

    def test_list_keys_isolation(self, client, auth_headers, api_key_for_pro):
        """test_user (basic) should not see pro_user's keys."""
        resp = client.get("/api/integrations/keys", headers=auth_headers)
        assert resp.status_code == 200
        assert resp.json()["total"] == 0


# ---------------------------------------------------------------------------
# DELETE /api/integrations/keys/{key_id} — Revoke
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestRevokeApiKey:
    def test_revoke_key(self, client, pro_auth_headers, api_key_for_pro):
        _, api_key = api_key_for_pro
        resp = client.delete(
            f"/api/integrations/keys/{api_key.id}",
            headers=pro_auth_headers,
        )
        assert resp.status_code == 200
        assert "révoquée" in resp.json()["detail"] or "revoquee" in resp.json()["detail"].lower()

    def test_revoke_already_revoked(self, client, db, pro_auth_headers, api_key_for_pro):
        _, api_key = api_key_for_pro
        api_key.is_active = False
        db.commit()

        resp = client.delete(
            f"/api/integrations/keys/{api_key.id}",
            headers=pro_auth_headers,
        )
        assert resp.status_code == 400
        assert "déjà" in resp.json()["detail"] or "deja" in resp.json()["detail"].lower()

    def test_revoke_not_found(self, client, pro_auth_headers):
        resp = client.delete("/api/integrations/keys/99999", headers=pro_auth_headers)
        assert resp.status_code == 404

    def test_revoke_other_user_key(self, client, auth_headers, api_key_for_pro):
        """test_user cannot revoke pro_user's key."""
        _, api_key = api_key_for_pro
        resp = client.delete(
            f"/api/integrations/keys/{api_key.id}",
            headers=auth_headers,
        )
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# GET /api/integrations/embed/{study_id} — Embed data
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestEmbedData:
    def test_embed_data_success(self, client, api_key_for_pro, study_with_dataset):
        raw_key, _ = api_key_for_pro
        resp = client.get(
            f"/api/integrations/embed/{study_with_dataset.id}",
            headers={"X-Api-Key": raw_key},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["study_id"] == study_with_dataset.id
        assert data["title"] == "Etude Embed Test"
        assert data["data"] is not None

    def test_embed_data_missing_key(self, client, study_with_dataset):
        resp = client.get(f"/api/integrations/embed/{study_with_dataset.id}")
        assert resp.status_code == 401

    def test_embed_data_invalid_key(self, client, study_with_dataset):
        resp = client.get(
            f"/api/integrations/embed/{study_with_dataset.id}",
            headers={"X-Api-Key": "ak_invalid_key_12345"},
        )
        assert resp.status_code == 401

    def test_embed_data_study_not_found(self, client, api_key_for_pro):
        raw_key, _ = api_key_for_pro
        resp = client.get(
            "/api/integrations/embed/99999",
            headers={"X-Api-Key": raw_key},
        )
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# GET /api/integrations/embed/{study_id}/widget/{widget_type}
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestEmbedWidget:
    def test_widget_bar_json(self, client, api_key_for_pro, study_with_dataset):
        raw_key, _ = api_key_for_pro
        resp = client.get(
            f"/api/integrations/embed/{study_with_dataset.id}/widget/bar",
            headers={"X-Api-Key": raw_key},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["widget_type"] == "bar"
        assert data["study_id"] == study_with_dataset.id

    def test_widget_invalid_type(self, client, api_key_for_pro, study_with_dataset):
        raw_key, _ = api_key_for_pro
        resp = client.get(
            f"/api/integrations/embed/{study_with_dataset.id}/widget/invalid",
            headers={"X-Api-Key": raw_key},
        )
        assert resp.status_code == 400
        assert "invalide" in resp.json()["detail"].lower()

    def test_widget_html_response(self, client, api_key_for_pro, study_with_dataset):
        raw_key, _ = api_key_for_pro
        resp = client.get(
            f"/api/integrations/embed/{study_with_dataset.id}/widget/pie",
            headers={"X-Api-Key": raw_key, "Accept": "text/html"},
        )
        assert resp.status_code == 200
        assert "text/html" in resp.headers.get("content-type", "")
        assert "Afrikalytics" in resp.text

    def test_widget_theme_dark(self, client, api_key_for_pro, study_with_dataset):
        raw_key, _ = api_key_for_pro
        resp = client.get(
            f"/api/integrations/embed/{study_with_dataset.id}/widget/line?theme=dark",
            headers={"X-Api-Key": raw_key},
        )
        assert resp.status_code == 200
        assert resp.json()["config"]["theme"] == "dark"
