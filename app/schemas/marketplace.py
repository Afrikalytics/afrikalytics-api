"""
Schemas Pydantic pour la Marketplace de templates.
"""
from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field


class MarketplaceTemplateResponse(BaseModel):
    """Template listing — excludes layout_json and demo_data for performance."""

    id: int
    name: str
    description: str
    category: str
    tags: list[str] = []
    preview_image_url: Optional[str] = None
    author_id: Optional[int] = None
    is_published: bool
    is_free: bool
    price: int = 0
    plan_required: str = "basic"
    install_count: int = 0
    rating: float = 0.0
    rating_count: int = 0
    widget_count: int = 0
    created_at: datetime
    updated_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)


class MarketplaceTemplateDetail(BaseModel):
    """Full template detail — includes layout_json and demo_data."""

    id: int
    name: str
    description: str
    category: str
    tags: list[str] = []
    preview_image_url: Optional[str] = None
    layout_json: dict[str, Any]
    demo_data: Optional[dict[str, Any]] = None
    author_id: Optional[int] = None
    is_published: bool
    is_free: bool
    price: int = 0
    plan_required: str = "basic"
    install_count: int = 0
    rating: float = 0.0
    rating_count: int = 0
    widget_count: int = 0
    created_at: datetime
    updated_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)


class MarketplaceTemplateCreate(BaseModel):
    """Schema for creating a new marketplace template (admin only)."""

    name: str = Field(..., min_length=1, max_length=200)
    description: str = Field(..., min_length=1)
    category: str = Field(..., min_length=1, max_length=50)
    tags: list[str] = []
    preview_image_url: Optional[str] = Field(None, max_length=500)
    layout_json: dict[str, Any]
    demo_data: Optional[dict[str, Any]] = None
    is_free: bool = True
    price: int = Field(0, ge=0)
    plan_required: str = Field("basic", pattern="^(basic|professionnel|entreprise)$")
    widget_count: int = Field(0, ge=0)


class MarketplaceTemplateUpdate(BaseModel):
    """Schema for updating a marketplace template (admin only)."""

    name: Optional[str] = Field(None, min_length=1, max_length=200)
    description: Optional[str] = Field(None, min_length=1)
    category: Optional[str] = Field(None, min_length=1, max_length=50)
    tags: Optional[list[str]] = None
    preview_image_url: Optional[str] = Field(None, max_length=500)
    layout_json: Optional[dict[str, Any]] = None
    demo_data: Optional[dict[str, Any]] = None
    is_free: Optional[bool] = None
    price: Optional[int] = Field(None, ge=0)
    plan_required: Optional[str] = Field(None, pattern="^(basic|professionnel|entreprise)$")
    widget_count: Optional[int] = Field(None, ge=0)


class MarketplaceListResponse(BaseModel):
    """Paginated marketplace template list."""

    templates: list[MarketplaceTemplateResponse]
    total: int
    categories: list[dict[str, Any]]  # [{"name": "retail", "count": 5}, ...]


class MarketplaceInstallResponse(BaseModel):
    """Response after installing a template."""

    dashboard_id: str
    message: str


class MarketplaceRateRequest(BaseModel):
    """Schema for rating a template."""

    rating: int = Field(..., ge=1, le=5)


class MarketplaceCategoryResponse(BaseModel):
    """Category with template count."""

    name: str
    count: int
