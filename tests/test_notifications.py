"""
Tests for the notifications router — /api/notifications/*
Covers: list, unread-count, mark-read, mark-all-read, delete.
"""
import pytest
from app.models import Notification


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def notification(db, test_user):
    """Create an unread notification for test_user."""
    n = Notification(
        user_id=test_user.id,
        notification_type="study_created",
        title="Nouvelle etude disponible",
        message="L'etude Marche Dakar est maintenant ouverte.",
        is_read=False,
    )
    db.add(n)
    db.commit()
    db.refresh(n)
    return n


@pytest.fixture()
def read_notification(db, test_user):
    """Create an already-read notification for test_user."""
    from datetime import datetime, timezone

    n = Notification(
        user_id=test_user.id,
        notification_type="payment_confirmed",
        title="Paiement confirme",
        message="Votre abonnement Professionnel est actif.",
        is_read=True,
        read_at=datetime.now(timezone.utc),
    )
    db.add(n)
    db.commit()
    db.refresh(n)
    return n


@pytest.fixture()
def other_user_notification(db, admin_user):
    """Create a notification belonging to admin_user (different user)."""
    n = Notification(
        user_id=admin_user.id,
        notification_type="info",
        title="Admin notification",
        message="This belongs to admin.",
        is_read=False,
    )
    db.add(n)
    db.commit()
    db.refresh(n)
    return n


@pytest.fixture()
def multiple_notifications(db, test_user):
    """Create 5 notifications for test_user (3 unread, 2 read)."""
    from datetime import datetime, timezone

    notifs = []
    for i in range(5):
        n = Notification(
            user_id=test_user.id,
            notification_type="info",
            title=f"Notification {i}",
            message=f"Message {i}",
            is_read=i >= 3,
            read_at=datetime.now(timezone.utc) if i >= 3 else None,
        )
        db.add(n)
        notifs.append(n)
    db.commit()
    for n in notifs:
        db.refresh(n)
    return notifs


# ---------------------------------------------------------------------------
# GET /api/notifications — List
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestListNotifications:
    def test_list_empty(self, client, auth_headers):
        resp = client.get("/api/notifications", headers=auth_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 0
        assert data["items"] == []
        assert data["unread_count"] == 0

    def test_list_with_notifications(self, client, auth_headers, multiple_notifications):
        resp = client.get("/api/notifications", headers=auth_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 5
        assert data["unread_count"] == 3

    def test_list_filter_unread(self, client, auth_headers, multiple_notifications):
        resp = client.get("/api/notifications?status=unread", headers=auth_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 3

    def test_list_filter_read(self, client, auth_headers, multiple_notifications):
        resp = client.get("/api/notifications?status=read", headers=auth_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 2

    def test_list_pagination(self, client, auth_headers, multiple_notifications):
        resp = client.get("/api/notifications?page=1&per_page=2", headers=auth_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["per_page"] == 2
        assert data["page"] == 1
        assert data["pages"] == 3  # 5 items / 2 per_page = 3 pages

    def test_list_unauthorized(self, client):
        resp = client.get("/api/notifications")
        assert resp.status_code == 401

    def test_list_isolation(self, client, auth_headers, other_user_notification):
        """test_user should not see admin_user's notifications."""
        resp = client.get("/api/notifications", headers=auth_headers)
        assert resp.status_code == 200
        assert resp.json()["total"] == 0


# ---------------------------------------------------------------------------
# GET /api/notifications/unread-count
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestUnreadCount:
    def test_unread_count_zero(self, client, auth_headers):
        resp = client.get("/api/notifications/unread-count", headers=auth_headers)
        assert resp.status_code == 200
        assert resp.json()["unread_count"] == 0

    def test_unread_count_with_notifications(self, client, auth_headers, multiple_notifications):
        resp = client.get("/api/notifications/unread-count", headers=auth_headers)
        assert resp.status_code == 200
        assert resp.json()["unread_count"] == 3

    def test_unread_count_unauthorized(self, client):
        resp = client.get("/api/notifications/unread-count")
        assert resp.status_code == 401


# ---------------------------------------------------------------------------
# PUT /api/notifications/{id}/read
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestMarkAsRead:
    def test_mark_as_read(self, client, auth_headers, notification):
        resp = client.put(
            f"/api/notifications/{notification.id}/read",
            headers=auth_headers,
        )
        assert resp.status_code == 200
        assert "lue" in resp.json()["message"].lower()

    def test_mark_already_read(self, client, auth_headers, read_notification):
        """Marking an already-read notification should succeed (idempotent)."""
        resp = client.put(
            f"/api/notifications/{read_notification.id}/read",
            headers=auth_headers,
        )
        assert resp.status_code == 200

    def test_mark_not_found(self, client, auth_headers):
        resp = client.put("/api/notifications/99999/read", headers=auth_headers)
        assert resp.status_code == 404

    def test_mark_other_user(self, client, auth_headers, other_user_notification):
        """test_user cannot mark admin_user's notification as read."""
        resp = client.put(
            f"/api/notifications/{other_user_notification.id}/read",
            headers=auth_headers,
        )
        assert resp.status_code == 404

    def test_mark_unauthorized(self, client, notification):
        resp = client.put(f"/api/notifications/{notification.id}/read")
        assert resp.status_code == 401


# ---------------------------------------------------------------------------
# PUT /api/notifications/read-all
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestMarkAllAsRead:
    def test_mark_all_read(self, client, auth_headers, multiple_notifications):
        resp = client.put("/api/notifications/read-all", headers=auth_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["updated_count"] == 3  # 3 unread notifications

    def test_mark_all_read_empty(self, client, auth_headers):
        resp = client.put("/api/notifications/read-all", headers=auth_headers)
        assert resp.status_code == 200
        assert resp.json()["updated_count"] == 0

    def test_mark_all_read_unauthorized(self, client):
        resp = client.put("/api/notifications/read-all")
        assert resp.status_code == 401


# ---------------------------------------------------------------------------
# DELETE /api/notifications/{id}
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestDeleteNotification:
    def test_delete_notification(self, client, auth_headers, notification):
        resp = client.delete(
            f"/api/notifications/{notification.id}",
            headers=auth_headers,
        )
        assert resp.status_code == 200
        assert "supprimee" in resp.json()["message"].lower()

    def test_delete_not_found(self, client, auth_headers):
        resp = client.delete("/api/notifications/99999", headers=auth_headers)
        assert resp.status_code == 404

    def test_delete_other_user(self, client, auth_headers, other_user_notification):
        """test_user cannot delete admin_user's notification."""
        resp = client.delete(
            f"/api/notifications/{other_user_notification.id}",
            headers=auth_headers,
        )
        assert resp.status_code == 404

    def test_delete_unauthorized(self, client, notification):
        resp = client.delete(f"/api/notifications/{notification.id}")
        assert resp.status_code == 401
