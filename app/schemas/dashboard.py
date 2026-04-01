"""
Schemas Pydantic pour le dashboard et les statistiques.
"""
from datetime import datetime
from pydantic import BaseModel, Field
from typing import Any, Optional


class DashboardStats(BaseModel):
    studies_accessible: int
    studies_participated: int
    reports_downloaded: int
    insights_viewed: int
    subscription_days_remaining: Optional[int]
    plan: str


# --- Dashboard Layouts ---

class LayoutCreate(BaseModel):
    name: str = Field(..., max_length=255)
    description: Optional[str] = None
    layout: dict[str, Any]


class LayoutUpdate(BaseModel):
    name: Optional[str] = Field(None, max_length=255)
    description: Optional[str] = None
    layout: Optional[dict[str, Any]] = None


class LayoutResponse(BaseModel):
    id: int
    name: str
    description: Optional[str]
    layout: dict[str, Any]
    is_template: bool
    created_at: datetime
    updated_at: Optional[datetime]


class LayoutListItem(BaseModel):
    id: int
    name: str
    description: Optional[str]
    is_template: bool
    widget_count: int
    created_at: datetime
    updated_at: Optional[datetime]
