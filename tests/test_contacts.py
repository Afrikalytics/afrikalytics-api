"""
Tests pour les endpoints des contacts — /api/contacts/*

Couvre:
- POST /api/contacts                    — creation (succes 201, champs manquants 422)
- GET  /api/contacts                    — liste (admin only, user 403)
- PUT  /api/contacts/{id}/read          — marquer comme lu (admin only)
- DELETE /api/contacts/{id}             — suppression (admin only)
"""

BASE_CONTACT_PAYLOAD = {
    "name": "Amadou Diallo",
    "email": "amadou.diallo@example.com",
    "company": "Marketym Dakar",
    "message": "Bonjour, je souhaite en savoir plus sur vos offres entreprise.",
}


class TestCreateContact:
    """Tests pour POST /api/contacts."""

    def test_anyone_can_submit_contact_form(self, client):
        """Le formulaire de contact est public, aucun token requis."""
        response = client.post(
            "/api/contacts",
            json=BASE_CONTACT_PAYLOAD,
        )

        assert response.status_code == 201
        data = response.json()
        assert data["name"] == BASE_CONTACT_PAYLOAD["name"]
        assert data["email"] == BASE_CONTACT_PAYLOAD["email"]
        assert data["message"] == BASE_CONTACT_PAYLOAD["message"]
        assert "id" in data
        assert "created_at" in data

    def test_contact_is_created_as_unread(self, client):
        """Un contact nouvellement cree doit avoir is_read=False."""
        response = client.post(
            "/api/contacts",
            json=BASE_CONTACT_PAYLOAD,
        )

        assert response.status_code == 201
        data = response.json()
        assert data["is_read"] is False

    def test_create_contact_without_company_succeeds(self, client):
        """Le champ company est optionnel."""
        payload = {
            "name": "Fatou Ndiaye",
            "email": "fatou@example.com",
            "message": "Message sans entreprise.",
        }
        response = client.post("/api/contacts", json=payload)

        assert response.status_code == 201
        data = response.json()
        assert data["company"] is None

    def test_create_contact_missing_name_returns_422(self, client):
        payload = {
            "email": "test@example.com",
            "message": "Message sans nom.",
        }
        response = client.post("/api/contacts", json=payload)

        assert response.status_code == 422

    def test_create_contact_missing_email_returns_422(self, client):
        payload = {
            "name": "Test User",
            "message": "Message sans email.",
        }
        response = client.post("/api/contacts", json=payload)

        assert response.status_code == 422

    def test_create_contact_missing_message_returns_422(self, client):
        payload = {
            "name": "Test User",
            "email": "test@example.com",
        }
        response = client.post("/api/contacts", json=payload)

        assert response.status_code == 422

    def test_create_contact_with_invalid_email_returns_422(self, client):
        payload = {
            "name": "Test User",
            "email": "pas-un-email",
            "message": "Test message.",
        }
        response = client.post("/api/contacts", json=payload)

        assert response.status_code == 422

    def test_create_contact_sends_email_notification(
        self, client, mock_send_email
    ):
        """La creation d'un contact doit declencher un email de notification."""
        client.post("/api/contacts", json=BASE_CONTACT_PAYLOAD)

        # Verifier que send_email a ete appele (via le mock injecte par conftest)
        assert mock_send_email.called


class TestListContacts:
    """Tests pour GET /api/contacts."""

    def test_super_admin_can_list_contacts(
        self, client, db, admin_auth_headers
    ):
        # Creer un contact en DB d'abord
        from models import Contact

        contact = Contact(
            name="Contact Test",
            email="contact_test@example.com",
            message="Message de test.",
        )
        db.add(contact)
        db.commit()

        response = client.get("/api/contacts", headers=admin_auth_headers)

        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        assert len(data) >= 1

    def test_list_contacts_response_contains_expected_fields(
        self, client, db, admin_auth_headers
    ):
        from models import Contact

        contact = Contact(
            name="Champs Test",
            email="champs@example.com",
            message="Verification des champs.",
        )
        db.add(contact)
        db.commit()

        response = client.get("/api/contacts", headers=admin_auth_headers)

        assert response.status_code == 200
        data = response.json()
        if data:
            item = data[0]
            for field in ["id", "name", "email", "message", "is_read", "created_at"]:
                assert field in item, f"Champ '{field}' manquant dans la reponse contacts"

    def test_list_contacts_supports_pagination(
        self, client, admin_auth_headers
    ):
        response = client.get(
            "/api/contacts?skip=0&limit=10", headers=admin_auth_headers
        )

        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        assert len(data) <= 10

    def test_regular_user_cannot_list_contacts_returns_403(
        self, client, auth_headers
    ):
        response = client.get("/api/contacts", headers=auth_headers)

        assert response.status_code == 403
        assert "detail" in response.json()

    def test_list_contacts_without_token_returns_401(self, client):
        response = client.get("/api/contacts")

        assert response.status_code == 401


class TestMarkContactAsRead:
    """Tests pour PUT /api/contacts/{contact_id}/read."""

    def test_super_admin_can_mark_contact_as_read(
        self, client, db, admin_auth_headers
    ):
        from models import Contact

        contact = Contact(
            name="A Lire",
            email="alire@example.com",
            message="Ce message doit etre marque comme lu.",
            is_read=False,
        )
        db.add(contact)
        db.commit()
        db.refresh(contact)

        response = client.put(
            f"/api/contacts/{contact.id}/read",
            headers=admin_auth_headers,
        )

        assert response.status_code == 200
        data = response.json()
        assert "message" in data

        # Verifier en DB que is_read est True
        db.expire_all()
        updated = db.query(Contact).filter(Contact.id == contact.id).first()
        assert updated.is_read is True

    def test_mark_nonexistent_contact_as_read_returns_404(
        self, client, admin_auth_headers
    ):
        response = client.put(
            "/api/contacts/99999/read",
            headers=admin_auth_headers,
        )

        assert response.status_code == 404
        assert "detail" in response.json()

    def test_regular_user_cannot_mark_contact_as_read_returns_403(
        self, client, db, auth_headers
    ):
        from models import Contact

        contact = Contact(
            name="Test",
            email="test_read@example.com",
            message="Test.",
        )
        db.add(contact)
        db.commit()
        db.refresh(contact)

        response = client.put(
            f"/api/contacts/{contact.id}/read",
            headers=auth_headers,
        )

        assert response.status_code == 403


class TestDeleteContact:
    """Tests pour DELETE /api/contacts/{contact_id}."""

    def test_super_admin_can_delete_contact(
        self, client, db, admin_auth_headers
    ):
        from models import Contact

        contact = Contact(
            name="A Supprimer",
            email="asupprimer@example.com",
            message="Ce contact sera supprime.",
        )
        db.add(contact)
        db.commit()
        db.refresh(contact)

        response = client.delete(
            f"/api/contacts/{contact.id}",
            headers=admin_auth_headers,
        )

        assert response.status_code == 200
        data = response.json()
        assert "message" in data
        assert "supprim" in data["message"].lower()

    def test_deleted_contact_no_longer_accessible(
        self, client, db, admin_auth_headers
    ):
        """Apres suppression, le contact ne doit plus apparaitre dans la liste."""
        from models import Contact

        contact = Contact(
            name="Verifie Suppression",
            email="verif_suppression@example.com",
            message="Test suppression.",
        )
        db.add(contact)
        db.commit()
        db.refresh(contact)
        contact_id = contact.id

        client.delete(
            f"/api/contacts/{contact_id}", headers=admin_auth_headers
        )

        # Verifier qu'il n'existe plus en DB
        deleted = db.query(Contact).filter(Contact.id == contact_id).first()
        assert deleted is None

    def test_delete_nonexistent_contact_returns_404(
        self, client, admin_auth_headers
    ):
        response = client.delete(
            "/api/contacts/99999",
            headers=admin_auth_headers,
        )

        assert response.status_code == 404
        assert "detail" in response.json()

    def test_regular_user_cannot_delete_contact_returns_403(
        self, client, db, auth_headers
    ):
        from models import Contact

        contact = Contact(
            name="Test Delete",
            email="test_delete@example.com",
            message="Test.",
        )
        db.add(contact)
        db.commit()
        db.refresh(contact)

        response = client.delete(
            f"/api/contacts/{contact.id}",
            headers=auth_headers,
        )

        assert response.status_code == 403

    def test_delete_contact_without_token_returns_401(self, client, db):
        from models import Contact

        contact = Contact(
            name="Test No Auth",
            email="test_noauth@example.com",
            message="Test.",
        )
        db.add(contact)
        db.commit()
        db.refresh(contact)

        response = client.delete(f"/api/contacts/{contact.id}")

        assert response.status_code == 401
