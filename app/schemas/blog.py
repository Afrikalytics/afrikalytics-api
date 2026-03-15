"""
Schemas Pydantic v2 pour le module Blog.
"""
from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator


class BlogPostCreate(BaseModel):
    title: str = Field(..., min_length=1, max_length=255)
    slug: Optional[str] = Field(None, max_length=255)
    excerpt: Optional[str] = Field(None, max_length=2000)
    content: str = Field(..., min_length=1, max_length=50000)
    featured_image: Optional[str] = Field(None, max_length=2000)
    category: Optional[str] = Field(None, max_length=100)
    tags: Optional[List[str]] = []
    status: Optional[str] = Field("draft", max_length=20)
    scheduled_at: Optional[datetime] = None
    meta_title: Optional[str] = Field(None, max_length=200)
    meta_description: Optional[str] = Field(None, max_length=500)
    og_image: Optional[str] = Field(None, max_length=2000)

    @field_validator("status")
    @classmethod
    def validate_status(cls, v: str | None) -> str | None:
        allowed = ["draft", "published", "scheduled"]
        if v is not None and v not in allowed:
            raise ValueError(f"Status must be one of: {allowed}")
        return v

    @field_validator("tags", mode="before")
    @classmethod
    def validate_tags(cls, v: object) -> list:
        if isinstance(v, list):
            return v
        return v if v else []


class BlogPostUpdate(BaseModel):
    title: Optional[str] = Field(None, min_length=1, max_length=255)
    slug: Optional[str] = Field(None, max_length=255)
    excerpt: Optional[str] = Field(None, max_length=2000)
    content: Optional[str] = Field(None, max_length=50000)
    featured_image: Optional[str] = Field(None, max_length=2000)
    category: Optional[str] = Field(None, max_length=100)
    tags: Optional[List[str]] = None
    status: Optional[str] = Field(None, max_length=20)
    scheduled_at: Optional[datetime] = None
    meta_title: Optional[str] = Field(None, max_length=200)
    meta_description: Optional[str] = Field(None, max_length=500)
    og_image: Optional[str] = Field(None, max_length=2000)

    @field_validator("status")
    @classmethod
    def validate_status(cls, v: str | None) -> str | None:
        if v is not None:
            allowed = ["draft", "published", "scheduled"]
            if v not in allowed:
                raise ValueError(f"Status must be one of: {allowed}")
        return v


class BlogPostResponse(BaseModel):
    id: int
    title: str
    slug: str
    excerpt: Optional[str]
    content: str
    featured_image: Optional[str]
    category: Optional[str]
    tags: Optional[List[str]]
    author_id: int
    author_name: Optional[str] = None
    status: str
    published_at: Optional[datetime]
    scheduled_at: Optional[datetime]
    meta_title: Optional[str]
    meta_description: Optional[str]
    og_image: Optional[str]
    views: int
    reading_time: Optional[int]
    created_at: datetime
    updated_at: Optional[datetime]

    model_config = ConfigDict(from_attributes=True)

    @field_validator("tags", mode="before")
    @classmethod
    def parse_tags(cls, v: object) -> list:
        if isinstance(v, list):
            return v
        return v if v else []


class BlogPostPublic(BaseModel):
    id: int
    title: str
    slug: str
    excerpt: Optional[str]
    content: str
    featured_image: Optional[str]
    category: Optional[str]
    tags: Optional[List[str]]
    author_name: Optional[str]
    published_at: Optional[datetime]
    meta_title: Optional[str]
    meta_description: Optional[str]
    og_image: Optional[str]
    views: int
    reading_time: Optional[int]
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)

    @field_validator("tags", mode="before")
    @classmethod
    def parse_tags(cls, v: object) -> list:
        if isinstance(v, list):
            return v
        return v if v else []


class BlogPostListResponse(BaseModel):
    items: List[BlogPostResponse]
    total: int
    page: int
    per_page: int
    total_pages: int


class BlogPostPublicListResponse(BaseModel):
    items: List[BlogPostPublic]
    total: int
    page: int
    per_page: int
    total_pages: int


class CategoryResponse(BaseModel):
    name: str
    count: int


class PopularPostResponse(BaseModel):
    id: int
    title: str
    slug: str
    excerpt: Optional[str]
    featured_image: Optional[str]
    category: Optional[str]
    views: int
    published_at: Optional[datetime]

    model_config = ConfigDict(from_attributes=True)


class SearchResponse(BaseModel):
    items: List[BlogPostPublic]
    total: int
    query: str


class MessageResponse(BaseModel):
    message: str
    detail: Optional[str] = None
