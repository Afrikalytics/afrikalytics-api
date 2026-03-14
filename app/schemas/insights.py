"""
Schemas Pydantic pour les insights.
"""
from datetime import datetime
from typing import List, Optional
from pydantic import BaseModel


class InsightCreate(BaseModel):
    study_id: int
    title: str
    summary: Optional[str] = None
    key_findings: Optional[str] = None
    recommendations: Optional[str] = None
    author: Optional[str] = None
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
