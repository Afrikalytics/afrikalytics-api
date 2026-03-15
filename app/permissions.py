"""
Shared admin permissions and helper functions.
"""
from fastapi import HTTPException
from sqlalchemy import select, func
from app.models import User


ADMIN_ROLES = {
    "super_admin": {
        "label": "Super Admin",
        "studies": True,
        "insights": True,
        "reports": True,
        "users": True
    },
    "admin_content": {
        "label": "Admin Contenu",
        "studies": True,
        "insights": True,
        "reports": True,
        "users": False
    },
    "admin_studies": {
        "label": "Admin Études",
        "studies": True,
        "insights": False,
        "reports": False,
        "users": False
    },
    "admin_insights": {
        "label": "Admin Insights",
        "studies": False,
        "insights": True,
        "reports": False,
        "users": False
    },
    "admin_reports": {
        "label": "Admin Rapports",
        "studies": False,
        "insights": False,
        "reports": True,
        "users": False
    }
}


def check_admin_permission(user, permission: str) -> bool:
    if not user.is_admin:
        return False
    role = user.admin_role
    if not role:
        return False
    if role not in ADMIN_ROLES:
        return False
    return ADMIN_ROLES[role].get(permission, False)


def require_admin_permission(permission: str):
    def check_permission(current_user: User):
        if not check_admin_permission(current_user, permission):
            raise HTTPException(
                status_code=403,
                detail=f"Vous n'avez pas la permission de gérer les {permission}"
            )
        return current_user
    return check_permission


def check_blog_permission(current_user: User):
    if not current_user.is_admin:
        raise HTTPException(status_code=403, detail="Permission refusée")
    if current_user.admin_role not in ["super_admin", "admin_content"]:
        raise HTTPException(
            status_code=403,
            detail="Seuls les Super Admin et Admin Content peuvent gérer le blog"
        )
    return True


def check_content_access(user: User, content_type: str = None, report_type: str = None):
    """
    Check if user's plan allows access to this content.
    Admins can see everything. Basic users cannot access premium reports.
    """
    if user.is_admin:
        return True
    if report_type == "premium" and user.plan == "basic":
        raise HTTPException(
            status_code=403,
            detail="Votre plan ne permet pas d'accéder à ce contenu premium. Passez au plan Professionnel."
        )
    return True


def get_paginated_results(query, page: int, per_page: int):
    """Legacy pagination helper — works with db.query() style queries."""
    total = query.count()
    items = query.offset((page - 1) * per_page).limit(per_page).all()
    total_pages = (total + per_page - 1) // per_page
    return {
        "items": items,
        "total": total,
        "page": page,
        "per_page": per_page,
        "total_pages": total_pages
    }


def get_paginated_results_stmt(db, stmt, page: int, per_page: int):
    """
    SQLAlchemy 2.0 pagination helper — works with select() statements.

    Args:
        db: SQLAlchemy Session
        stmt: A select() statement (before offset/limit)
        page: Page number (1-based)
        per_page: Items per page
    """
    # Count total matching rows
    count_stmt = select(func.count()).select_from(stmt.subquery())
    total = db.execute(count_stmt).scalar()

    # Fetch paginated items
    items = db.execute(
        stmt.offset((page - 1) * per_page).limit(per_page)
    ).scalars().all()

    total_pages = (total + per_page - 1) // per_page
    return {
        "items": items,
        "total": total,
        "page": page,
        "per_page": per_page,
        "total_pages": total_pages
    }
