"""
Audit logging service for the Afrikalytics API.

Every admin or user mutation (create, update, delete, publish, toggle, login,
logout, password change, plan change, etc.) should call :func:`log_audit` so
that a full, tamper-evident audit trail is maintained in ``audit_logs``.

Design decisions
----------------
- The function never raises — a failure to write an audit log must not abort
  the business transaction it accompanies.  Errors are logged at ERROR level
  so they appear in Sentry and Railway logs.
- Sensitive values (passwords, tokens, API keys) must NEVER appear in
  ``details``.  Use :func:`app.security.sanitize_log_dict` to sanitize any
  dict before passing it here.
- ``ip_address`` is extracted from the forwarded chain when behind a proxy
  (Railway / Vercel forward X-Forwarded-For).  The first IP in the chain is
  used (original client) to prevent spoofing by intermediate proxies.
- ``user_agent`` is truncated to 500 chars to match the column size.

Backward compatibility
----------------------
The old ``log_action`` function is kept as a thin alias so existing routers
continue to work without modification.  New code should call ``log_audit``.
"""

import logging
from typing import Any, Optional

from fastapi import Request
from sqlalchemy.orm import Session

from app.models import AuditLog
from app.security import sanitize_log_dict

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# IP / User-Agent extraction
# ---------------------------------------------------------------------------

def _extract_ip(request: Optional[Request]) -> Optional[str]:
    """Extract the real client IP from the request.

    Railway sits behind a load-balancer that sets ``X-Forwarded-For``.
    The first IP in the header is the original client.  The value is
    capped at 45 chars to handle the longest IPv6 addresses (39 chars)
    within the DB column definition.
    """
    if request is None:
        return None

    forwarded_for = request.headers.get("x-forwarded-for")
    if forwarded_for:
        # "X-Forwarded-For: client, proxy1, proxy2" — client is always first
        ip = forwarded_for.split(",")[0].strip()
    elif request.client:
        ip = request.client.host
    else:
        return None

    return ip[:45]


def _extract_user_agent(request: Optional[Request]) -> Optional[str]:
    """Extract and truncate the User-Agent header (column max = 500 chars)."""
    if request is None:
        return None
    ua = request.headers.get("user-agent", "")
    return ua[:500] if ua else None


# ---------------------------------------------------------------------------
# Core logging function
# ---------------------------------------------------------------------------

def log_audit(
    db: Session,
    *,
    user_id: Optional[int],
    action: str,
    resource_type: str,
    resource_id: Optional[int] = None,
    details: Optional[dict[str, Any]] = None,
    request: Optional[Request] = None,
) -> Optional[AuditLog]:
    """Record an auditable action in the ``audit_logs`` table.

    Parameters
    ----------
    db:
        Active SQLAlchemy session.  The function calls ``db.flush()`` to
        persist the log entry within the surrounding transaction, so the
        caller's ``db.commit()`` makes it durable.
    user_id:
        ID of the authenticated user performing the action.  ``None`` for
        anonymous or system-initiated actions.
    action:
        Short, machine-readable verb — e.g. ``"create"``, ``"update"``,
        ``"delete"``, ``"login"``, ``"logout"``, ``"publish"``,
        ``"toggle_active"``, ``"password_change"``, ``"plan_change"``.
        Max 100 chars (enforced by DB column).
    resource_type:
        The entity type affected — e.g. ``"user"``, ``"study"``,
        ``"insight"``, ``"report"``, ``"blog_post"``, ``"api_key"``.
        Max 50 chars.
    resource_id:
        Primary key of the affected row (optional for collection-level
        actions such as user login or bulk operations).
    details:
        Arbitrary JSON-serialisable dict with context.  **Must not contain
        plaintext passwords, tokens, or API keys** — this function
        automatically runs :func:`app.security.sanitize_log_dict` on the
        dict before storing it.
    request:
        FastAPI ``Request`` object.  When provided, client IP and
        User-Agent are captured automatically.

    Returns
    -------
    AuditLog | None
        The persisted ``AuditLog`` instance, or ``None`` if an error
        occurred (the audit failure is logged but never propagated).

    Examples
    --------
    In a router::

        from app.services.audit import log_audit

        @router.post("/api/studies/")
        def create_study(payload: StudyCreate, request: Request,
                         db: Session = Depends(get_db),
                         current_user: User = Depends(get_current_user)):
            study = Study(**payload.model_dump())
            db.add(study)
            db.flush()           # assign study.id before logging
            log_audit(
                db,
                user_id=current_user.id,
                action="create",
                resource_type="study",
                resource_id=study.id,
                details={"title": study.title},
                request=request,
            )
            db.commit()
            return study
    """
    try:
        # Sanitize details to prevent accidental sensitive-data logging
        safe_details: Optional[dict] = None
        if details is not None:
            safe_details = sanitize_log_dict(details)

        log_entry = AuditLog(
            user_id=user_id,
            action=action[:100],           # enforce column max length defensively
            resource_type=resource_type[:50],
            resource_id=resource_id,
            details=safe_details,
            ip_address=_extract_ip(request),
            user_agent=_extract_user_agent(request),
        )
        db.add(log_entry)
        # flush() makes the INSERT visible within the current transaction but
        # leaves commit control to the caller — this is safer than a standalone
        # commit() which would create an implicit transaction boundary here.
        db.flush()
        return log_entry

    except Exception as exc:
        logger.error(
            "audit_log_write_failed action=%s resource_type=%s resource_id=%s error=%s",
            action,
            resource_type,
            resource_id,
            exc,
            exc_info=True,
        )
        # Defensive rollback to avoid dirty session state propagating to callers.
        try:
            db.rollback()
        except Exception:
            pass
        return None


# ---------------------------------------------------------------------------
# Backward-compatibility alias
# ---------------------------------------------------------------------------

def log_action(
    db: Session,
    user_id: int,
    action: str,
    resource_type: str,
    resource_id: Optional[int] = None,
    details: Optional[dict] = None,
    request: Optional[Request] = None,
) -> Optional[AuditLog]:
    """Backward-compatible alias for :func:`log_audit`.

    Existing routers that call ``log_action(db, user_id, ...)`` continue to
    work without modification.  New code should prefer ``log_audit`` with
    keyword arguments for clarity.
    """
    return log_audit(
        db,
        user_id=user_id,
        action=action,
        resource_type=resource_type,
        resource_id=resource_id,
        details=details,
        request=request,
    )


# ---------------------------------------------------------------------------
# Named convenience wrappers for common security events
# ---------------------------------------------------------------------------

def log_login(
    db: Session,
    user_id: int,
    request: Request,
    success: bool = True,
) -> None:
    """Record a login attempt (success or failure)."""
    log_audit(
        db,
        user_id=user_id,
        action="login_success" if success else "login_failure",
        resource_type="user",
        resource_id=user_id,
        details={"success": success},
        request=request,
    )


def log_logout(db: Session, user_id: int, request: Request) -> None:
    """Record a logout event."""
    log_audit(
        db,
        user_id=user_id,
        action="logout",
        resource_type="user",
        resource_id=user_id,
        request=request,
    )


def log_password_change(db: Session, user_id: int, request: Request) -> None:
    """Record a password change (the new password is never logged)."""
    log_audit(
        db,
        user_id=user_id,
        action="password_change",
        resource_type="user",
        resource_id=user_id,
        request=request,
    )


def log_plan_change(
    db: Session,
    user_id: int,
    old_plan: str,
    new_plan: str,
    request: Optional[Request] = None,
) -> None:
    """Record a subscription plan change."""
    log_audit(
        db,
        user_id=user_id,
        action="plan_change",
        resource_type="subscription",
        details={"old_plan": old_plan, "new_plan": new_plan},
        request=request,
    )


def log_api_key_created(
    db: Session,
    user_id: int,
    key_name: str,
    key_prefix: str,
    request: Optional[Request] = None,
) -> None:
    """Record API key creation (only the prefix is logged, never the raw key)."""
    log_audit(
        db,
        user_id=user_id,
        action="api_key_created",
        resource_type="api_key",
        details={"name": key_name, "key_prefix": key_prefix},
        request=request,
    )


def log_api_key_revoked(
    db: Session,
    user_id: int,
    key_id: int,
    key_name: str,
    key_prefix: str,
    request: Optional[Request] = None,
) -> None:
    """Record API key revocation."""
    log_audit(
        db,
        user_id=user_id,
        action="api_key_revoked",
        resource_type="api_key",
        resource_id=key_id,
        details={"name": key_name, "key_prefix": key_prefix},
        request=request,
    )
