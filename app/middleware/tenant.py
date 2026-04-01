"""
Multi-tenancy middleware and dependencies for Row Level Security (RLS) enforcement.

PostgreSQL RLS uses session-level variables (app.current_user_id, app.current_user_role)
to filter rows automatically. This module provides FastAPI dependencies that inject
these variables into every database transaction.

Usage in routers:
    from app.middleware.tenant import get_tenant_db

    @router.get("/api/subscriptions")
    async def list_subscriptions(db: Session = Depends(get_tenant_db)):
        # RLS automatically filters by current user
        return db.execute(select(Subscription)).scalars().all()
"""
import logging
from typing import Generator

from fastapi import Depends
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import get_current_user
from app.models import User

logger = logging.getLogger(__name__)


def get_tenant_db(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Generator[Session, None, None]:
    """
    Database session with tenant context for RLS enforcement.

    Sets PostgreSQL session variables so that RLS policies can filter rows:
    - app.current_user_id: the authenticated user's ID
    - app.current_user_role: the user's admin role (or empty string for regular users)

    Uses SET (connection-scoped) instead of SET LOCAL (transaction-scoped)
    because SET LOCAL requires an active transaction to take effect.
    Variables are explicitly reset when the session is released to avoid
    leaking tenant context to the next request via pooled connections.
    """
    try:
        # Set tenant context for RLS policies (connection-scoped)
        # Using parameterized text() to prevent SQL injection
        db.execute(
            text("SET app.current_user_id = :user_id"),
            {"user_id": str(current_user.id)},
        )

        role = current_user.admin_role if current_user.is_admin and current_user.admin_role else ""
        db.execute(
            text("SET app.current_user_role = :role"),
            {"role": role},
        )

        logger.debug(
            "Tenant context set: user_id=%s, role=%s",
            current_user.id,
            current_user.admin_role or "user",
        )

        yield db

    except Exception:
        db.rollback()
        raise
    finally:
        # Reset tenant context to prevent leaking to the next request
        # via pooled connections. RESET restores the parameter to its default.
        try:
            db.execute(text("RESET app.current_user_id"))
            db.execute(text("RESET app.current_user_role"))
        except Exception:
            logger.warning("Failed to reset tenant context on connection", exc_info=True)


def get_admin_tenant_db(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Generator[Session, None, None]:
    """
    Database session with admin tenant context.

    Same as get_tenant_db but explicitly for admin endpoints.
    Sets the admin role so RLS admin bypass policies can take effect.
    Raises 403 if user is not an admin.
    """
    from fastapi import HTTPException

    if not current_user.is_admin:
        raise HTTPException(
            status_code=403,
            detail="Accès réservé aux administrateurs",
        )

    try:
        db.execute(
            text("SET app.current_user_id = :user_id"),
            {"user_id": str(current_user.id)},
        )
        db.execute(
            text("SET app.current_user_role = :role"),
            {"role": current_user.admin_role or "super_admin"},
        )

        yield db

    except Exception:
        db.rollback()
        raise
    finally:
        # Reset tenant context to prevent leaking to the next request
        try:
            db.execute(text("RESET app.current_user_id"))
            db.execute(text("RESET app.current_user_role"))
        except Exception:
            logger.warning("Failed to reset admin tenant context on connection", exc_info=True)
