"""
Schemas Pydantic pour les insights.
"""
from datetime import datetime
from typing import List, Optional
from pydantic import BaseModel, Field


class InsightCreate(BaseModel):
    study_id: int
    title: str = Field(..., max_length=200)
    summary: Optional[str] = Field(None, max_length=2000)
    key_findings: Optional[str] = Field(None, max_length=50000)
    recommendations: Optional[str] = Field(None, max_length=50000)
    author: Optional[str] = Field(None, max_length=100)
    images: Optional[List[str]] = None
    is_published: Optional[bool] = False


class InsightResponse(BaseModel):
    id: int
    study_id: int
    title: str
    summary: Optional[str]
    key_findings: Optional[str]
    recommendations: Optional[str]
    author: Optional[str]
    images: Optional[List[str]]
    is_published: bool
    created_at: datetime

    class Config:
        from_attributes = True
