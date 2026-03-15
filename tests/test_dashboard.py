"""
Tests pour les endpoints du dashboard — /api/dashboard/* et /api/subscriptions/*

Couvre:
- GET /api/dashboard/stats            — statistiques (authentifie → stats, non-auth → 401)
- GET /api/subscriptions/my-subscription — detail de l'abonnement courant
- Validation des champs retournes selon le plan utilisateur
"""


class TestDashboardStats:
    """Tests pour GET /api/dashboard/stats."""

    def test_authenticated_user_can_get_stats(
        self, client, auth_headers
    ):
        response = client.get("/api/dashboard/stats", headers=auth_headers)

        assert response.status_code == 200

    def test_dashboard_stats_returns_expected_fields(
        self, client, auth_headers
    ):
        response = client.get("/api/dashboard/stats", headers=auth_headers)

        assert response.status_code == 200
        data = response.json()
        expected_fields = [
            "studies_accessible",
            "studies_total",
            "studies_open",
            "reports_available",
            "insights_available",
            "plan",
            "is_premium",
        ]
        for field in expected_fields:
            assert field in data, f"Champ '{field}' manquant dans la reponse stats"

    def test_dashboard_stats_without_token_returns_401(self, client):
        response = client.get("/api/dashboard/stats")

        assert response.status_code == 401

    def test_basic_user_is_not_premium(self, client, auth_headers):
        """Un utilisateur basic ne doit pas etre marque premium."""
        response = client.get("/api/dashboard/stats", headers=auth_headers)

        assert response.status_code == 200
        data = response.json()
        assert data["plan"] == "basic"
        assert data["is_premium"] is False

    def test_enterprise_user_is_premium(
        self, client, enterprise_auth_headers
    ):
        """Un utilisateur entreprise doit etre marque premium."""
        response = client.get(
            "/api/dashboard/stats", headers=enterprise_auth_headers
        )

        assert response.status_code == 200
        data = response.json()
        assert data["plan"] == "entreprise"
        assert data["is_premium"] is True

    def test_stats_with_content_counts_studies(
        self, client, study, auth_headers
    ):
        """Les stats doivent refleter les etudes presentes en DB."""
        response = client.get("/api/dashboard/stats", headers=auth_headers)

        assert response.status_code == 200
        data = response.json()
        # Il y a au moins une etude active de type "Ouvert" dans la fixture
        assert data["studies_accessible"] >= 1
        assert data["studies_open"] >= 1

    def test_stats_subscription_days_remaining_is_none_for_basic(
        self, client, auth_headers
    ):
        """Pour un plan basic, subscription_days_remaining doit etre null."""
        response = client.get("/api/dashboard/stats", headers=auth_headers)

        assert response.status_code == 200
        data = response.json()
        assert data["subscription_days_remaining"] is None


class TestMySubscription:
    """Tests pour GET /api/subscriptions/my-subscription."""

    def test_authenticated_user_can_get_subscription(
        self, client, auth_headers
    ):
        response = client.get(
            "/api/subscriptions/my-subscription", headers=auth_headers
        )

        assert response.status_code == 200

    def test_subscription_without_token_returns_401(self, client):
        response = client.get("/api/subscriptions/my-subscription")

        assert response.status_code == 401

    def test_user_without_subscription_returns_has_subscription_false(
        self, client, auth_headers
    ):
        """Un utilisateur sans abonnement actif doit avoir has_subscription=False."""
        response = client.get(
            "/api/subscriptions/my-subscription", headers=auth_headers
        )

        assert response.status_code == 200
        data = response.json()
        assert data["has_subscription"] is False
        assert "plan" in data

    def test_user_with_active_subscription_returns_details(
        self, client, db, enterprise_user, enterprise_auth_headers
    ):
        """Un utilisateur avec un abonnement actif doit obtenir ses details."""
        from app.models import Subscription
        from datetime import datetime, timedelta, timezone

        subscription = Subscription(
            user_id=enterprise_user.id,
            plan="entreprise",
            status="active",
            start_date=datetime.now(timezone.utc),
            end_date=datetime.now(timezone.utc) + timedelta(days=30),
        )
        db.add(subscription)
        db.commit()

        response = client.get(
            "/api/subscriptions/my-subscription", headers=enterprise_auth_headers
        )

        assert response.status_code == 200
        data = response.json()
        assert data["has_subscription"] is True
        assert data["plan"] == "entreprise"
        assert data["status"] == "active"
        assert "end_date" in data
        assert "days_remaining" in data
