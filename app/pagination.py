"""
Reusable pagination utilities for all listing endpoints.

Usage in routers:
    from app.pagination import PaginationParams, paginate, PaginatedResponse

    @router.get("/api/items")
    async def list_items(
        pagination: PaginationParams = Depends(),
        db: Session = Depends(get_db),
    ):
        stmt = select(Item).order_by(Item.created_at.desc())
        return paginate(db, stmt, pagination)
"""
import math
from typing import Any, Generic, List, TypeVar

from fastapi import Query
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.orm import Session

T = TypeVar("T")


class PaginationParams:
    """FastAPI dependency that extracts and validates pagination query parameters."""

    def __init__(
        self,
        page: int = Query(1, ge=1, description="Page number (1-based)"),
        per_page: int = Query(20, ge=1, le=100, description="Items per page"),
    ):
        self.page = page
        self.per_page = per_page

    @property
    def skip(self) -> int:
        return (self.page - 1) * self.per_page

    @property
    def limit(self) -> int:
        return self.per_page


class PaginatedResponse(BaseModel):
    """Generic paginated response envelope."""
    items: List[Any]
    total: int
    page: int
    per_page: int
    pages: int


def paginate(
    db: Session,
    stmt,
    pagination: PaginationParams,
) -> dict:
    """
    Apply pagination to a SQLAlchemy 2.0 select() statement.

    Returns a dict matching the PaginatedResponse structure:
        {
            "items": [...],
            "total": 123,
            "page": 1,
            "per_page": 20,
            "pages": 7,
        }

    Args:
        db: SQLAlchemy Session
        stmt: A select() statement (before offset/limit)
        pagination: PaginationParams dependency instance
    """
    # Count total matching rows using a subquery
    count_stmt = select(func.count()).select_from(stmt.subquery())
    total = db.execute(count_stmt).scalar() or 0

    # Fetch paginated items
    items = (
        db.execute(stmt.offset(pagination.skip).limit(pagination.limit))
        .scalars()
        .all()
    )

    pages = math.ceil(total / pagination.per_page) if pagination.per_page > 0 else 0

    return {
        "items": items,
        "total": total,
        "page": pagination.page,
        "per_page": pagination.per_page,
        "pages": pages,
    }
