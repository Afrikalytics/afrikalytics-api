"""
Automatic audit logging via SQLAlchemy ORM events.

Listens to after_insert, after_update, and after_delete on auditable models
and creates AuditLog entries automatically. This supplements (not replaces)
the manual log_audit() calls in routers which capture request context (IP, UA).

Event-based logs capture the user_id from the model's own user_id or
author_id FK, and record which columns changed for updates.

Usage:
    from app.services.audit_events import register_audit_listeners
    register_audit_listeners()  # call once at startup (e.g. in main.py)
"""

import logging
from typing import Any

from sqlalchemy import event, inspect
from sqlalchemy.orm import Session

from app.models import (
    AuditLog,
    Study,
    Insight,
    Report,
    BlogPost,
    Subscription,
    Payment,
    Contact,
    ApiKey,
    Notification,
)

logger = logging.getLogger(__name__)

# Models to auto-audit and how to extract the actor (user_id)
_AUDITABLE_MODELS: dict[type, str] = {
    Study: "user_id",         # studies don't have user_id — use None
    Insight: "user_id",
    Report: "user_id",
    BlogPost: "author_id",
    Subscription: "user_id",
    Payment: "user_id",
    Contact: "user_id",
    ApiKey: "user_id",
    Notification: "user_id",
}


def _get_user_id(instance: Any) -> int | None:
    """Extract the acting user_id from a model instance."""
    for attr in ("user_id", "author_id"):
        uid = getattr(instance, attr, None)
        if uid is not None:
            return uid
    return None


def _get_resource_type(instance: Any) -> str:
    """Derive a human-readable resource type from the model class."""
    return instance.__class__.__tablename__.rstrip("s")


def _get_changed_columns(instance: Any) -> dict[str, Any] | None:
    """For updates, return a dict of {column: new_value} for modified attrs."""
    state = inspect(instance)
    changes = {}
    for attr in state.attrs:
        hist = attr.history
        if hist.has_changes():
            key = attr.key
            # Skip sensitive fields
            if key in ("hashed_password", "key_hash", "confirmation_token_hash"):
                continue
            changes[key] = getattr(instance, key)
    return changes if changes else None


def _after_insert(mapper: Any, connection: Any, target: Any) -> None:
    """Create an audit log entry after a new row is inserted."""
    try:
        session = Session.object_session(target)
        if session is None:
            return
        entry = AuditLog(
            user_id=_get_user_id(target),
            action="create",
            resource_type=_get_resource_type(target),
            resource_id=getattr(target, "id", None),
            details={"source": "orm_event"},
        )
        session.add(entry)
    except Exception:
        logger.exception("Audit event (insert) failed for %s", type(target).__name__)


def _after_update(mapper: Any, connection: Any, target: Any) -> None:
    """Create an audit log entry after a row is updated."""
    try:
        changes = _get_changed_columns(target)
        if not changes:
            return
        session = Session.object_session(target)
        if session is None:
            return

        # Detect soft-delete
        action = "soft_delete" if "deleted_at" in changes and changes["deleted_at"] is not None else "update"

        entry = AuditLog(
            user_id=_get_user_id(target),
            action=action,
            resource_type=_get_resource_type(target),
            resource_id=getattr(target, "id", None),
            details={"changed": list(changes.keys()), "source": "orm_event"},
        )
        session.add(entry)
    except Exception:
        logger.exception("Audit event (update) failed for %s", type(target).__name__)


def _after_delete(mapper: Any, connection: Any, target: Any) -> None:
    """Create an audit log entry after a row is hard-deleted."""
    try:
        session = Session.object_session(target)
        if session is None:
            return
        entry = AuditLog(
            user_id=_get_user_id(target),
            action="hard_delete",
            resource_type=_get_resource_type(target),
            resource_id=getattr(target, "id", None),
            details={"source": "orm_event"},
        )
        session.add(entry)
    except Exception:
        logger.exception("Audit event (delete) failed for %s", type(target).__name__)


def register_audit_listeners() -> None:
    """Register SQLAlchemy ORM event listeners for all auditable models."""
    for model_cls in _AUDITABLE_MODELS:
        event.listen(model_cls, "after_insert", _after_insert)
        event.listen(model_cls, "after_update", _after_update)
        event.listen(model_cls, "after_delete", _after_delete)
    logger.info("Audit event listeners registered for %d models", len(_AUDITABLE_MODELS))
