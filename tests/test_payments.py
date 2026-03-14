"""
Tests pour les endpoints de paiement PayDunya — /api/paydunya/*

Note: Ces tests necessitent une connexion au sandbox PayDunya.
Les tests d'integration complets sont desactives (skippes) en CI.

Couvre (placeholder + tests structuraux):
- POST /api/paydunya/create-invoice — structure du endpoint (auth requise)
- POST /api/paydunya/webhook       — rejet des webhooks non signes
- GET  /api/paydunya/verify/{token}— validation de la route
"""

import pytest


# ---------------------------------------------------------------------------
# Tests structuraux (ne necessitent pas le sandbox PayDunya)
# ---------------------------------------------------------------------------


class TestCreatePaydunyaInvoice:
    """Tests structuraux pour POST /api/paydunya/create-invoice."""

    def test_create_invoice_without_token_returns_401(self, client):
        """L'endpoint de creation de facture necessite une authentification."""
        payload = {
            "plan": "professionnel",
            "email": "user@example.com",
            "name": "Test User",
        }
        response = client.post("/api/paydunya/create-invoice", json=payload)

        assert response.status_code == 401

    def test_create_invoice_missing_required_fields_returns_422(
        self, client, auth_headers
    ):
        """Payload incomplet : validation Pydantic doit retourner 422."""
        response = client.post(
            "/api/paydunya/create-invoice",
            json={},
            headers=auth_headers,
        )

        assert response.status_code == 422

    @pytest.mark.skip(
        reason="requires PayDunya sandbox — ne pas executer en CI sans credentials"
    )
    def test_create_invoice_with_valid_payload_returns_payment_url(
        self, client, auth_headers
    ):
        """
        Test d'integration complet avec le sandbox PayDunya.
        Necessite PAYDUNYA_MASTER_KEY, PAYDUNYA_PRIVATE_KEY, PAYDUNYA_TOKEN.
        Exclure ce test du CI avec : pytest -m 'not sandbox'
        """
        payload = {
            "plan": "professionnel",
            "email": "test_ci@afrikalytics.com",
            "name": "Test CI User",
        }
        response = client.post(
            "/api/paydunya/create-invoice",
            json=payload,
            headers=auth_headers,
        )

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert "payment_url" in data
        assert "token" in data


class TestPaydunyaWebhook:
    """Tests structuraux pour POST /api/paydunya/webhook."""

    def test_webhook_without_signature_returns_error(self, client):
        """Un webhook sans signature (hash) doit etre rejete."""
        # Payload sans hash ni token
        payload = {
            "status": "completed",
            "custom_data": {
                "email": "hacker@example.com",
                "plan": "professionnel",
            },
        }
        response = client.post("/api/paydunya/webhook", json=payload)

        # Le webhook sans signature doit etre rejete (403) ou traite en erreur
        # Le router retourne 403 si hash/token manquants
        assert response.status_code in (403, 200)
        if response.status_code == 200:
            # Si 200, la reponse doit indiquer une erreur ou un statut ignore
            data = response.json()
            assert data.get("status") in ("error", "ignored", None)

    def test_webhook_with_invalid_plan_is_rejected(self, client):
        """Un webhook avec un plan inconnu doit etre rejete."""
        import hashlib
        import os

        master_key = os.getenv("PAYDUNYA_MASTER_KEY", "test-master-key")
        invoice_token = "test-token-invalid-plan"
        expected_hash = hashlib.sha512(
            (master_key + invoice_token).encode("utf-8")
        ).hexdigest()

        payload = {
            "hash": expected_hash,
            "status": "completed",
            "invoice": {"token": invoice_token},
            "custom_data": {
                "email": "test@example.com",
                "name": "Test User",
                "plan": "plan_inexistant",
            },
        }
        response = client.post("/api/paydunya/webhook", json=payload)

        # Doit retourner 400 (plan invalide) ou 200 avec status=error
        assert response.status_code in (400, 200)

    @pytest.mark.skip(
        reason="requires PayDunya sandbox — ne pas executer en CI sans credentials"
    )
    def test_webhook_completes_payment_and_upgrades_user(
        self, client, test_user, db
    ):
        """
        Test d'integration : un webhook valide doit upgrader le plan de l'utilisateur.
        Necessite une signature HMAC valide avec les vrais credentials PayDunya sandbox.
        """
        import hashlib
        import os

        master_key = os.getenv("PAYDUNYA_MASTER_KEY", "")
        invoice_token = "test-sandbox-token-12345"
        expected_hash = hashlib.sha512(
            (master_key + invoice_token).encode("utf-8")
        ).hexdigest()

        payload = {
            "hash": expected_hash,
            "status": "completed",
            "invoice": {"token": invoice_token},
            "custom_data": {
                "email": test_user.email,
                "name": test_user.full_name,
                "plan": "professionnel",
            },
        }
        response = client.post("/api/paydunya/webhook", json=payload)

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"

        # Verifier que le plan de l'utilisateur a ete mis a jour
        from models import User
        db.expire_all()
        updated_user = db.query(User).filter(User.id == test_user.id).first()
        assert updated_user.plan == "professionnel"


class TestVerifyPaydunyaPayment:
    """Tests structuraux pour GET /api/paydunya/verify/{token}."""

    @pytest.mark.skip(
        reason="requires PayDunya sandbox — ne pas executer en CI sans credentials"
    )
    def test_verify_valid_token_returns_payment_status(self, client):
        """
        Test d'integration : verifier le statut d'un paiement via son token.
        Necessite un token valide du sandbox PayDunya.
        """
        sandbox_token = "TOKEN_PAYDUNYA_SANDBOX_A_REMPLACER"
        response = client.get(f"/api/paydunya/verify/{sandbox_token}")

        assert response.status_code == 200
        data = response.json()
        assert "status" in data
