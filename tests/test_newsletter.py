"""
Tests pour les endpoints de la newsletter — /api/newsletter/*

Couvre:
- POST /api/newsletter/subscribe          — abonnement (succes, doublon actif, reactivation)
- GET  /api/newsletter/confirm/{token}    — confirmation email
- GET  /api/newsletter/unsubscribe/{token}— desabonnement
- GET  /api/newsletter/subscribers        — liste des abonnes (admin only, user 403)
"""

import secrets


class TestNewsletterSubscribe:
    """Tests pour POST /api/newsletter/subscribe."""

    def test_new_subscriber_can_subscribe(self, client):
        response = client.post(
            "/api/newsletter/subscribe",
            json={"email": "nouveau@example.com", "source": "homepage"},
        )

        assert response.status_code == 201
        data = response.json()
        assert "message" in data
        # Un email de confirmation est requis
        assert data.get("confirmation_required") is True

    def test_subscribe_with_default_source(self, client):
        """Le champ source est optionnel (par defaut 'blog_footer')."""
        response = client.post(
            "/api/newsletter/subscribe",
            json={"email": "default_source@example.com"},
        )

        assert response.status_code == 201
        assert "message" in response.json()

    def test_duplicate_active_subscriber_returns_already_subscribed(self, client):
        """Un email deja abonne et actif doit recevoir un message informatif (200 ou 201)."""
        email = "doublon@example.com"
        # Premier abonnement
        client.post(
            "/api/newsletter/subscribe",
            json={"email": email},
        )

        # Deuxieme abonnement avec le meme email
        response = client.post(
            "/api/newsletter/subscribe",
            json={"email": email},
        )

        # Le comportement attendu : pas d'erreur, message informatif
        assert response.status_code in (200, 201)
        data = response.json()
        assert "message" in data

    def test_reactivate_unsubscribed_email(self, client, db):
        """Un email desabonne peut se reabonner."""
        from app.models import NewsletterSubscriber

        # Creer un abonne desabonne directement en DB
        subscriber = NewsletterSubscriber(
            email="reactiver@example.com",
            source="test",
            status="unsubscribed",
            is_confirmed=True,
            confirmation_token=secrets.token_urlsafe(32),
            unsubscribe_token=secrets.token_urlsafe(32),
        )
        db.add(subscriber)
        db.commit()

        # Tenter de se reabonner
        response = client.post(
            "/api/newsletter/subscribe",
            json={"email": "reactiver@example.com"},
        )

        assert response.status_code in (200, 201)
        data = response.json()
        assert "message" in data

    def test_subscribe_with_invalid_email_returns_422(self, client):
        response = client.post(
            "/api/newsletter/subscribe",
            json={"email": "pas-un-email"},
        )

        assert response.status_code == 422

    def test_subscribe_without_email_returns_422(self, client):
        response = client.post(
            "/api/newsletter/subscribe",
            json={},
        )

        assert response.status_code == 422


class TestNewsletterConfirm:
    """Tests pour GET /api/newsletter/confirm/{token}."""

    def test_valid_token_confirms_subscription(self, client, db):
        """Un token valide doit confirmer l'abonnement."""
        from app.models import NewsletterSubscriber

        token = secrets.token_urlsafe(32)
        subscriber = NewsletterSubscriber(
            email="aconfirmer@example.com",
            source="test",
            status="active",
            is_confirmed=False,
            confirmation_token=token,
            unsubscribe_token=secrets.token_urlsafe(32),
        )
        db.add(subscriber)
        db.commit()

        response = client.get(f"/api/newsletter/confirm/{token}")

        assert response.status_code == 200
        data = response.json()
        assert "message" in data

        # Verifier que l'abonne est bien confirme en DB
        db.expire_all()
        updated = db.query(NewsletterSubscriber).filter(
            NewsletterSubscriber.email == "aconfirmer@example.com"
        ).first()
        assert updated.is_confirmed is True
        assert updated.confirmed_at is not None

    def test_invalid_confirmation_token_returns_404(self, client):
        response = client.get("/api/newsletter/confirm/token-invalide-xyz")

        assert response.status_code == 404
        assert "detail" in response.json()

    def test_already_confirmed_token_returns_message(self, client, db):
        """Un token deja utilise doit retourner un message sans erreur."""
        from app.models import NewsletterSubscriber
        from datetime import datetime, timezone

        token = secrets.token_urlsafe(32)
        subscriber = NewsletterSubscriber(
            email="dejacf@example.com",
            source="test",
            status="active",
            is_confirmed=True,
            confirmed_at=datetime.now(timezone.utc),
            confirmation_token=token,
            unsubscribe_token=secrets.token_urlsafe(32),
        )
        db.add(subscriber)
        db.commit()

        response = client.get(f"/api/newsletter/confirm/{token}")

        assert response.status_code == 200
        data = response.json()
        assert "message" in data


class TestNewsletterUnsubscribe:
    """Tests pour GET /api/newsletter/unsubscribe/{token}."""

    def test_valid_token_unsubscribes_subscriber(self, client, db):
        """Un token de desabonnement valide doit desabonner l'utilisateur."""
        from app.models import NewsletterSubscriber

        unsubscribe_token = secrets.token_urlsafe(32)
        subscriber = NewsletterSubscriber(
            email="adesabonner@example.com",
            source="test",
            status="active",
            is_confirmed=True,
            confirmation_token=secrets.token_urlsafe(32),
            unsubscribe_token=unsubscribe_token,
        )
        db.add(subscriber)
        db.commit()

        response = client.get(f"/api/newsletter/unsubscribe/{unsubscribe_token}")

        assert response.status_code == 200
        data = response.json()
        assert "message" in data

        # Verifier le statut en DB
        db.expire_all()
        updated = db.query(NewsletterSubscriber).filter(
            NewsletterSubscriber.email == "adesabonner@example.com"
        ).first()
        assert updated.status == "unsubscribed"
        assert updated.unsubscribed_at is not None

    def test_invalid_unsubscribe_token_returns_404(self, client):
        response = client.get("/api/newsletter/unsubscribe/token-invalide-xyz")

        assert response.status_code == 404
        assert "detail" in response.json()

    def test_already_unsubscribed_returns_message(self, client, db):
        """Un token d'un abonne deja desabonne doit retourner un message sans erreur."""
        from app.models import NewsletterSubscriber

        unsubscribe_token = secrets.token_urlsafe(32)
        subscriber = NewsletterSubscriber(
            email="dejades@example.com",
            source="test",
            status="unsubscribed",
            is_confirmed=True,
            confirmation_token=secrets.token_urlsafe(32),
            unsubscribe_token=unsubscribe_token,
        )
        db.add(subscriber)
        db.commit()

        response = client.get(f"/api/newsletter/unsubscribe/{unsubscribe_token}")

        assert response.status_code == 200
        assert "message" in response.json()


class TestNewsletterSubscribers:
    """Tests pour GET /api/newsletter/subscribers."""

    def test_super_admin_can_list_subscribers(
        self, client, db, admin_auth_headers
    ):
        # Creer un abonne pour avoir des resultats
        from app.models import NewsletterSubscriber

        subscriber = NewsletterSubscriber(
            email="abonne_list@example.com",
            source="test",
            status="active",
            is_confirmed=True,
            confirmation_token=secrets.token_urlsafe(32),
            unsubscribe_token=secrets.token_urlsafe(32),
        )
        db.add(subscriber)
        db.commit()

        response = client.get(
            "/api/newsletter/subscribers", headers=admin_auth_headers
        )

        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        assert len(data) >= 1

    def test_subscribers_response_contains_expected_fields(
        self, client, db, admin_auth_headers
    ):
        from app.models import NewsletterSubscriber

        subscriber = NewsletterSubscriber(
            email="abonne_fields@example.com",
            source="homepage",
            status="active",
            is_confirmed=True,
            confirmation_token=secrets.token_urlsafe(32),
            unsubscribe_token=secrets.token_urlsafe(32),
        )
        db.add(subscriber)
        db.commit()

        response = client.get(
            "/api/newsletter/subscribers", headers=admin_auth_headers
        )

        assert response.status_code == 200
        data = response.json()
        if data:
            item = data[0]
            for field in ["id", "email", "status", "is_confirmed", "source", "subscribed_at"]:
                assert field in item, f"Champ '{field}' manquant dans la reponse subscribers"

    def test_regular_user_cannot_list_subscribers_returns_403(
        self, client, auth_headers
    ):
        response = client.get(
            "/api/newsletter/subscribers", headers=auth_headers
        )

        assert response.status_code == 403

    def test_list_subscribers_without_token_returns_401(self, client):
        response = client.get("/api/newsletter/subscribers")

        assert response.status_code == 401
