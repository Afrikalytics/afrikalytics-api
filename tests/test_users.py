"""
Tests pour les endpoints utilisateurs — /api/users/*

Couvre:
- GET  /api/users/me           — profil utilisateur courant
- GET  /api/users/quota        — quotas par plan
- PUT  /api/users/change-password — changement de mot de passe
- GET  /api/users/{id}         — detail utilisateur (admin only pour tiers)
"""


CSRF = {"X-Requested-With": "XMLHttpRequest"}


class TestGetMe:
    """Tests pour GET /api/users/me."""

    def test_get_me_authenticated_returns_user_profile(self, client, test_user, auth_headers):
        response = client.get("/api/users/me", headers=auth_headers)

        assert response.status_code == 200
        data = response.json()
        assert data["email"] == test_user.email
        assert data["full_name"] == test_user.full_name
        assert data["plan"] == "basic"
        assert "id" in data

    def test_get_me_without_token_returns_401(self, client):
        response = client.get("/api/users/me")

        assert response.status_code == 401

    def test_get_me_with_invalid_token_returns_401(self, client):
        headers = {"Authorization": "Bearer token-invalide-xyz"}
        response = client.get("/api/users/me", headers=headers)

        assert response.status_code == 401

    def test_get_me_returns_no_hashed_password(self, client, auth_headers):
        """Le mot de passe hache ne doit jamais etre expose dans la reponse."""
        response = client.get("/api/users/me", headers=auth_headers)

        assert response.status_code == 200
        data = response.json()
        assert "hashed_password" not in data
        assert "password" not in data

    def test_get_me_admin_user_has_admin_fields(self, client, admin_user, admin_auth_headers):
        response = client.get("/api/users/me", headers=admin_auth_headers)

        assert response.status_code == 200
        data = response.json()
        assert data["is_admin"] is True
        assert data["email"] == admin_user.email


class TestGetQuota:
    """Tests pour GET /api/users/quota."""

    def test_get_quota_basic_plan_returns_correct_limits(self, client, test_user, auth_headers):
        response = client.get("/api/users/quota", headers=auth_headers)

        assert response.status_code == 200
        data = response.json()
        assert data["plan"] == "basic"
        assert "tokens" in data
        assert isinstance(data["tokens"], list)
        assert len(data["tokens"]) > 0

        # Verifier que les tokens contiennent les champs attendus
        token = data["tokens"][0]
        assert "name" in token
        assert "limit" in token
        assert "used" in token

    def test_get_quota_basic_plan_has_limited_reports_downloads(self, client, auth_headers):
        response = client.get("/api/users/quota", headers=auth_headers)

        assert response.status_code == 200
        data = response.json()
        tokens_by_name = {t["name"]: t for t in data["tokens"]}
        reports_token = tokens_by_name.get("reports_downloads")

        assert reports_token is not None
        assert reports_token["limit"] == 3
        assert reports_token["unlimited"] is False

    def test_get_quota_entreprise_plan_has_unlimited_access(
        self, client, enterprise_user, enterprise_auth_headers
    ):
        response = client.get("/api/users/quota", headers=enterprise_auth_headers)

        assert response.status_code == 200
        data = response.json()
        assert data["plan"] == "entreprise"
        tokens_by_name = {t["name"]: t for t in data["tokens"]}

        # Tous les tokens entreprise sont illimites
        for name, token in tokens_by_name.items():
            assert token["unlimited"] is True, f"Token '{name}' devrait etre illimite pour le plan entreprise"

    def test_get_quota_without_token_returns_401(self, client):
        response = client.get("/api/users/quota")

        assert response.status_code == 401

    def test_get_quota_returns_billing_period_start(self, client, auth_headers):
        response = client.get("/api/users/quota", headers=auth_headers)

        assert response.status_code == 200
        data = response.json()
        assert "billing_period_start" in data


class TestChangePassword:
    """Tests pour PUT /api/users/change-password."""

    def test_change_password_success(self, client, test_user, auth_headers):
        payload = {
            "current_password": "TestPassword123!",
            "new_password": "NewPassword456!",
        }
        response = client.put(
            "/api/users/change-password",
            json=payload,
            headers=auth_headers,
        )

        assert response.status_code == 200
        data = response.json()
        assert "message" in data
        assert "modifi" in data["message"].lower()

    def test_change_password_wrong_current_password_returns_400(
        self, client, auth_headers
    ):
        payload = {
            "current_password": "MauvaisMotDePasse!",
            "new_password": "NewPassword456!",
        }
        response = client.put(
            "/api/users/change-password",
            json=payload,
            headers=auth_headers,
        )

        assert response.status_code == 400
        data = response.json()
        assert "detail" in data

    def test_change_password_too_short_new_password_returns_400(
        self, client, auth_headers
    ):
        payload = {
            "current_password": "TestPassword123!",
            "new_password": "court",
        }
        response = client.put(
            "/api/users/change-password",
            json=payload,
            headers=auth_headers,
        )

        assert response.status_code == 400

    def test_change_password_without_token_returns_401(self, client):
        payload = {
            "current_password": "TestPassword123!",
            "new_password": "NewPassword456!",
        }
        response = client.put("/api/users/change-password", json=payload)

        assert response.status_code == 401

    def test_change_password_triggers_email_notification(
        self, client, auth_headers, mock_send_email
    ):
        """Verifier que l'email de confirmation est bien appele apres changement."""
        payload = {
            "current_password": "TestPassword123!",
            "new_password": "NewPassword456!",
        }
        response = client.put(
            "/api/users/change-password",
            json=payload,
            headers=auth_headers,
        )

        assert response.status_code == 200
        mock_send_email.assert_called_once()


class TestGetUserById:
    """Tests pour GET /api/users/{user_id}."""

    def test_user_can_access_own_profile(self, client, test_user, auth_headers):
        response = client.get(f"/api/users/{test_user.id}", headers=auth_headers)

        assert response.status_code == 200
        data = response.json()
        assert data["id"] == test_user.id
        assert data["email"] == test_user.email

    def test_user_cannot_access_other_user_profile_returns_403(
        self, client, test_user, admin_user, auth_headers
    ):
        """Un utilisateur non-admin ne peut pas voir le profil d'un autre utilisateur."""
        response = client.get(f"/api/users/{admin_user.id}", headers=auth_headers)

        assert response.status_code == 403
        data = response.json()
        assert "detail" in data

    def test_admin_can_access_any_user_profile(
        self, client, test_user, admin_auth_headers
    ):
        response = client.get(f"/api/users/{test_user.id}", headers=admin_auth_headers)

        assert response.status_code == 200
        data = response.json()
        assert data["id"] == test_user.id

    def test_get_user_nonexistent_id_returns_404(self, client, admin_auth_headers):
        response = client.get("/api/users/99999", headers=admin_auth_headers)

        assert response.status_code == 404
        data = response.json()
        assert "detail" in data

    def test_get_user_without_token_returns_401(self, client, test_user):
        response = client.get(f"/api/users/{test_user.id}")

        assert response.status_code == 401
