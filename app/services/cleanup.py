"""
Database cleanup service for the Afrikalytics API.

The tables ``verification_codes``, ``token_blacklist``, and
``sso_exchange_codes`` grow indefinitely because expired rows are never
purged.  Left unchecked this degrades query performance and wastes storage.

This module provides functions that can be called:
  - From a scheduled endpoint (admin-only, protected by ``cron_secret``).
  - From a Railway CRON job (via a one-off ``POST /api/admin/cleanup``).
  - Programmatically from tests or management scripts.

Security note
-------------
The cleanup endpoint is protected by a ``cron_secret`` header so that only
an authorised caller (Railway CRON) can trigger it, not arbitrary users.
The secret is configured via the ``CRON_SECRET`` environment variable.
"""

import logging
from datetime import datetime, timezone
from typing import TypedDict

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.models import SSOExchangeCode, TokenBlacklist, VerificationCode

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Result type
# ---------------------------------------------------------------------------

class CleanupResult(TypedDict):
    """Counts of rows deleted per table."""

    verification_codes_deleted: int
    token_blacklist_deleted: int
    sso_exchange_codes_deleted: int
    ran_at: str


# ---------------------------------------------------------------------------
# Individual table cleanups
# ---------------------------------------------------------------------------

def _delete_expired_verification_codes(db: Session) -> int:
    """Delete VerificationCode rows that have passed their ``expires_at``.

    Both used *and* unused expired codes are removed — an unused but expired
    code is worthless and should not remain in the database.
    """
    now = datetime.now(timezone.utc)
    result = db.execute(
        delete(VerificationCode).where(VerificationCode.expires_at < now)
    )
    deleted: int = result.rowcount
    if deleted:
        logger.info("cleanup: deleted %d expired verification_codes", deleted)
    return deleted


def _delete_expired_token_blacklist(db: Session) -> int:
    """Delete TokenBlacklist rows whose ``expires_at`` has passed.

    Once a JWT's expiry has passed the token would be rejected by signature
    validation alone, so the blacklist entry no longer serves a purpose.
    """
    now = datetime.now(timezone.utc)
    result = db.execute(
        delete(TokenBlacklist).where(TokenBlacklist.expires_at < now)
    )
    deleted: int = result.rowcount
    if deleted:
        logger.info("cleanup: deleted %d expired token_blacklist entries", deleted)
    return deleted


def _delete_expired_sso_exchange_codes(db: Session) -> int:
    """Delete SSOExchangeCode rows that have expired or have been used.

    SSO exchange codes have a 60-second TTL by design.  Any code that is
    either expired or already consumed is safe to delete.
    """
    now = datetime.now(timezone.utc)
    result = db.execute(
        delete(SSOExchangeCode).where(
            (SSOExchangeCode.expires_at < now) | (SSOExchangeCode.is_used.is_(True))
        )
    )
    deleted: int = result.rowcount
    if deleted:
        logger.info("cleanup: deleted %d expired/used sso_exchange_codes", deleted)
    return deleted


# ---------------------------------------------------------------------------
# Main cleanup function
# ---------------------------------------------------------------------------

def run_cleanup(db: Session) -> CleanupResult:
    """Delete all expired/consumed ephemeral rows from technical tables.

    This function performs three targeted DELETE statements in a single
    database round-trip (one per table).  It commits the deletions and
    returns counts of rows removed from each table.

    Parameters
    ----------
    db:
        An active SQLAlchemy session.  The function issues its own
        ``db.commit()`` so it can be called from a standalone scheduler
        context without an existing transaction.

    Returns
    -------
    CleanupResult
        Dict with ``verification_codes_deleted``, ``token_blacklist_deleted``,
        ``sso_exchange_codes_deleted``, and ``ran_at`` (ISO 8601 UTC timestamp).

    Raises
    ------
    Exception
        Any database error is propagated to the caller so it can decide
        whether to retry or report the failure.  The caller should roll back
        the session on error.
    """
    vc_deleted = _delete_expired_verification_codes(db)
    tb_deleted = _delete_expired_token_blacklist(db)
    sso_deleted = _delete_expired_sso_exchange_codes(db)

    db.commit()

    ran_at = datetime.now(timezone.utc).isoformat()

    logger.info(
        "cleanup_complete verification_codes=%d token_blacklist=%d sso_exchange_codes=%d",
        vc_deleted,
        tb_deleted,
        sso_deleted,
    )

    return CleanupResult(
        verification_codes_deleted=vc_deleted,
        token_blacklist_deleted=tb_deleted,
        sso_exchange_codes_deleted=sso_deleted,
        ran_at=ran_at,
    )


# ---------------------------------------------------------------------------
# Row-count helpers (for health dashboards / Grafana)
# ---------------------------------------------------------------------------

def count_expired_rows(db: Session) -> dict[str, int]:
    """Return counts of expired rows per table (non-destructive, read-only).

    Useful for monitoring dashboards to track table bloat before triggering
    a cleanup.
    """
    now = datetime.now(timezone.utc)

    vc_count = db.execute(
        select(func.count(VerificationCode.id)).where(
            VerificationCode.expires_at < now
        )
    ).scalar() or 0

    tb_count = db.execute(
        select(func.count(TokenBlacklist.id)).where(
            TokenBlacklist.expires_at < now
        )
    ).scalar() or 0

    sso_count = db.execute(
        select(func.count(SSOExchangeCode.id)).where(
            (SSOExchangeCode.expires_at < now) | (SSOExchangeCode.is_used.is_(True))
        )
    ).scalar() or 0

    return {
        "expired_verification_codes": vc_count,
        "expired_token_blacklist": tb_count,
        "expired_sso_exchange_codes": sso_count,
    }
