"""
Schemas Pydantic pour les insights.
"""
from datetime import datetime
from typing import Any, List, Optional
from pydantic import BaseModel, ConfigDict, Field


class InsightCreate(BaseModel):
    study_id: int
    title: str = Field(..., max_length=200)
    summary: Optional[str] = Field(None, max_length=2000)
    key_findings: Optional[List[Any]] = None
    recommendations: Optional[List[Any]] = None
    author: Optional[str] = Field(None, max_length=100)
    images: Optional[List[str]] = None
    is_published: Optional[bool] = False


class InsightUpdate(BaseModel):
    study_id: Optional[int] = None
    title: Optional[str] = Field(None, max_length=200)
    summary: Optional[str] = Field(None, max_length=2000)
    key_findings: Optional[List[Any]] = None
    recommendations: Optional[List[Any]] = None
    author: Optional[str] = Field(None, max_length=100)
    images: Optional[List[str]] = None
    is_published: Optional[bool] = None

    model_config = ConfigDict(from_attributes=True)


class InsightResponse(BaseModel):
    id: int
    study_id: int
    title: str
    summary: Optional[str]
    key_findings: Optional[List[Any]]
    recommendations: Optional[List[Any]]
    author: Optional[str]
    images: Optional[List[str]]
    is_published: bool
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)
