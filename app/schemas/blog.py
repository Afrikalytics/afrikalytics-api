"""
Schemas Pydantic pour le module Blog.
"""
import json
from datetime import datetime
from typing import Optional, List
from pydantic import BaseModel, Field, validator


class BlogPostCreate(BaseModel):
    title: str = Field(..., min_length=1, max_length=255)
    slug: Optional[str] = Field(None, max_length=255)
    excerpt: Optional[str] = None
    content: str = Field(..., min_length=1)
    featured_image: Optional[str] = None
    category: Optional[str] = None
    tags: Optional[List[str]] = []
    status: Optional[str] = "draft"
    scheduled_at: Optional[datetime] = None
    meta_title: Optional[str] = None
    meta_description: Optional[str] = None
    og_image: Optional[str] = None

    @validator('status')
    def validate_status(cls, v):
        allowed = ['draft', 'published', 'scheduled']
        if v not in allowed:
            raise ValueError(f'Status must be one of: {allowed}')
        return v

    @validator('tags', pre=True)
    def validate_tags(cls, v):
        if isinstance(v, str):
            try:
                return json.loads(v)
            except:
                return []
        return v if v else []


class BlogPostUpdate(BaseModel):
    title: Optional[str] = Field(None, min_length=1, max_length=255)
    slug: Optional[str] = Field(None, max_length=255)
    excerpt: Optional[str] = None
    content: Optional[str] = None
    featured_image: Optional[str] = None
    category: Optional[str] = None
    tags: Optional[List[str]] = None
    status: Optional[str] = None
    scheduled_at: Optional[datetime] = None
    meta_title: Optional[str] = None
    meta_description: Optional[str] = None
    og_image: Optional[str] = None

    @validator('status')
    def validate_status(cls, v):
        if v is not None:
            allowed = ['draft', 'published', 'scheduled']
            if v not in allowed:
                raise ValueError(f'Status must be one of: {allowed}')
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

    class Config:
        from_attributes = True

    @validator('tags', pre=True)
    def parse_tags(cls, v):
        if isinstance(v, str):
            try:
                return json.loads(v)
            except:
                return []
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

    class Config:
        from_attributes = True

    @validator('tags', pre=True)
    def parse_tags(cls, v):
        if isinstance(v, str):
            try:
                return json.loads(v)
            except:
                return []
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

    class Config:
        from_attributes = True


class SearchResponse(BaseModel):
    items: List[BlogPostPublic]
    total: int
    query: str


class MessageResponse(BaseModel):
    message: str
    detail: Optional[str] = None
