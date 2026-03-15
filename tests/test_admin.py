"""
Tests pour les endpoints d'administration — /api/admin/*

Couvre:
- GET    /api/admin/roles                      — liste des roles
- GET    /api/admin/users                      — liste utilisateurs (paginee)
- POST   /api/admin/users                      — creer un admin
- PUT    /api/admin/users/{id}                 — modifier un utilisateur
- DELETE /api/admin/users/{id}                 — supprimer un utilisateur
- PUT    /api/admin/users/{id}/toggle-active   — activer/desactiver
"""


class TestGetAdminRoles:
    """Tests pour GET /api/admin/roles."""

    def test_admin_can_get_roles_list(self, client, admin_auth_headers):
        response = client.get("/api/admin/roles", headers=admin_auth_headers)

        assert response.status_code == 200
        data = response.json()
        assert "roles" in data
        assert isinstance(data["roles"], list)
        assert len(data["roles"]) > 0

        # Verifier la structure d'un role
        role = data["roles"][0]
        assert "code" in role
        assert "label" in role

    def test_admin_roles_contains_all_expected_roles(self, client, admin_auth_headers):
        response = client.get("/api/admin/roles", headers=admin_auth_headers)

        assert response.status_code == 200
        codes = [r["code"] for r in response.json()["roles"]]
        for expected in ["super_admin", "admin_content", "admin_studies", "admin_insights", "admin_reports"]:
            assert expected in codes

    def test_non_admin_user_cannot_get_roles_returns_403(self, client, auth_headers):
        response = client.get("/api/admin/roles", headers=auth_headers)

        assert response.status_code == 403
        data = response.json()
        assert "detail" in data

    def test_unauthenticated_request_returns_401(self, client):
        response = client.get("/api/admin/roles")

        assert response.status_code == 401


class TestGetAdminUsers:
    """Tests pour GET /api/admin/users."""

    def test_super_admin_gets_all_users(
        self, client, test_user, admin_user, admin_auth_headers
    ):
        response = client.get("/api/admin/users", headers=admin_auth_headers)

        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        # Au moins test_user et admin_user existent
        assert len(data) >= 2

    def test_admin_users_response_contains_expected_fields(
        self, client, test_user, admin_auth_headers
    ):
        response = client.get("/api/admin/users", headers=admin_auth_headers)

        assert response.status_code == 200
        user_data = response.json()[0]
        for field in ["id", "email", "full_name", "plan", "is_active", "is_admin"]:
            assert field in user_data, f"Champ '{field}' manquant dans la reponse"

    def test_non_admin_user_cannot_list_users_returns_403(self, client, auth_headers):
        response = client.get("/api/admin/users", headers=auth_headers)

        assert response.status_code == 403

    def test_content_admin_cannot_list_users_returns_403(
        self, client, content_admin_auth_headers
    ):
        """admin_content n'a pas la permission 'users'."""
        response = client.get("/api/admin/users", headers=content_admin_auth_headers)

        assert response.status_code == 403

    def test_pagination_skip_limit_parameters(self, client, admin_auth_headers):
        response = client.get("/api/admin/users?skip=0&limit=5", headers=admin_auth_headers)

        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        assert len(data) <= 5


class TestCreateAdminUser:
    """Tests pour POST /api/admin/users."""

    def test_super_admin_can_create_user(self, client, admin_auth_headers):
        payload = {
            "email": "newadmin@example.com",
            "full_name": "Nouvel Admin",
            "plan": "basic",
            "is_active": True,
            "is_admin": False,
        }
        response = client.post(
            "/api/admin/users",
            json=payload,
            headers=admin_auth_headers,
        )

        assert response.status_code == 201
        data = response.json()
        assert data["email"] == "newadmin@example.com"
        assert data["full_name"] == "Nouvel Admin"
        assert "id" in data

    def test_create_user_sends_welcome_email(
        self, client, admin_auth_headers, mock_send_email
    ):
        payload = {
            "email": "emailtest@example.com",
            "full_name": "Email Test User",
            "plan": "basic",
            "is_active": True,
            "is_admin": False,
        }
        response = client.post(
            "/api/admin/users",
            json=payload,
            headers=admin_auth_headers,
        )

        assert response.status_code == 201
        mock_send_email.assert_called_once()

    def test_create_user_duplicate_email_returns_400(
        self, client, test_user, admin_auth_headers
    ):
        payload = {
            "email": test_user.email,
            "full_name": "Doublon",
            "plan": "basic",
            "is_active": True,
            "is_admin": False,
        }
        response = client.post(
            "/api/admin/users",
            json=payload,
            headers=admin_auth_headers,
        )

        assert response.status_code == 400
        data = response.json()
        assert "detail" in data

    def test_non_admin_cannot_create_user_returns_403(self, client, auth_headers):
        payload = {
            "email": "tentative@example.com",
            "full_name": "Unauthorized",
            "plan": "basic",
        }
        response = client.post(
            "/api/admin/users",
            json=payload,
            headers=auth_headers,
        )

        assert response.status_code == 403


class TestUpdateAdminUser:
    """Tests pour PUT /api/admin/users/{id}."""

    def test_admin_can_update_user_role(
        self, client, test_user, admin_auth_headers
    ):
        payload = {
            "is_admin": True,
            "admin_role": "admin_studies",
        }
        response = client.put(
            f"/api/admin/users/{test_user.id}",
            json=payload,
            headers=admin_auth_headers,
        )

        assert response.status_code == 200
        data = response.json()
        assert data["is_admin"] is True
        assert data["admin_role"] == "admin_studies"

    def test_admin_can_update_user_plan(
        self, client, test_user, admin_auth_headers
    ):
        payload = {"plan": "professionnel"}
        response = client.put(
            f"/api/admin/users/{test_user.id}",
            json=payload,
            headers=admin_auth_headers,
        )

        assert response.status_code == 200
        data = response.json()
        assert data["plan"] == "professionnel"

    def test_update_nonexistent_user_returns_404(self, client, admin_auth_headers):
        payload = {"full_name": "Fantome"}
        response = client.put(
            "/api/admin/users/99999",
            json=payload,
            headers=admin_auth_headers,
        )

        assert response.status_code == 404
        data = response.json()
        assert "detail" in data

    def test_non_admin_cannot_update_user_returns_403(
        self, client, test_user, auth_headers
    ):
        payload = {"full_name": "Hacker"}
        response = client.put(
            f"/api/admin/users/{test_user.id}",
            json=payload,
            headers=auth_headers,
        )

        assert response.status_code == 403


class TestDeleteAdminUser:
    """Tests pour DELETE /api/admin/users/{id}."""

    def test_admin_can_delete_other_user(
        self, client, test_user, admin_auth_headers
    ):
        response = client.delete(
            f"/api/admin/users/{test_user.id}",
            headers=admin_auth_headers,
        )

        assert response.status_code == 200
        data = response.json()
        assert "message" in data
        assert "supprim" in data["message"].lower()

    def test_admin_cannot_delete_own_account_returns_400(
        self, client, admin_user, admin_auth_headers
    ):
        """Un admin ne peut pas supprimer son propre compte."""
        response = client.delete(
            f"/api/admin/users/{admin_user.id}",
            headers=admin_auth_headers,
        )

        assert response.status_code == 400
        data = response.json()
        assert "detail" in data

    def test_delete_nonexistent_user_returns_404(self, client, admin_auth_headers):
        response = client.delete(
            "/api/admin/users/99999",
            headers=admin_auth_headers,
        )

        assert response.status_code == 404

    def test_non_admin_cannot_delete_user_returns_403(
        self, client, test_user, auth_headers
    ):
        """Un utilisateur lambda ne peut pas supprimer un compte."""
        # On cree un second utilisateur a supprimer pour eviter les conflits
        response = client.delete(
            f"/api/admin/users/{test_user.id}",
            headers=auth_headers,
        )

        assert response.status_code == 403


class TestToggleUserActive:
    """Tests pour PUT /api/admin/users/{id}/toggle-active."""

    def test_admin_can_deactivate_user(
        self, client, test_user, admin_auth_headers
    ):
        # test_user est actif par defaut
        response = client.put(
            f"/api/admin/users/{test_user.id}/toggle-active",
            headers=admin_auth_headers,
        )

        assert response.status_code == 200
        data = response.json()
        assert "is_active" in data
        assert data["is_active"] is False

    def test_admin_can_reactivate_user(
        self, client, test_user, db, admin_auth_headers
    ):
        # Desactiver d'abord via la BDD directement
        test_user.is_active = False
        db.commit()

        response = client.put(
            f"/api/admin/users/{test_user.id}/toggle-active",
            headers=admin_auth_headers,
        )

        assert response.status_code == 200
        data = response.json()
        assert data["is_active"] is True

    def test_toggle_nonexistent_user_returns_404(self, client, admin_auth_headers):
        response = client.put(
            "/api/admin/users/99999/toggle-active",
            headers=admin_auth_headers,
        )

        assert response.status_code == 404

    def test_non_admin_cannot_toggle_active_returns_403(
        self, client, test_user, auth_headers
    ):
        response = client.put(
            f"/api/admin/users/{test_user.id}/toggle-active",
            headers=auth_headers,
        )

        assert response.status_code == 403
