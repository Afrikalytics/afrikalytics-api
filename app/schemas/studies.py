"""
Schemas Pydantic pour les etudes de marche.
"""
from pydantic import BaseModel
from typing import Optional
from datetime import datetime


class StudyCreate(BaseModel):
    title: str
    description: str
    category: str
    duration: Optional[str] = "15-20 min"
    deadline: Optional[str] = None
    status: Optional[str] = "Ouvert"
    icon: Optional[str] = "users"
    embed_url_particulier: Optional[str] = None
    embed_url_entreprise: Optional[str] = None
    embed_url_results: Optional[str] = None
    report_url_basic: Optional[str] = None
    report_url_premium: Optional[str] = None
    is_active: Optional[bool] = True


class StudyResponse(BaseModel):
    id: int
    title: str
    description: Optional[str]
    category: Optional[str]
    duration: Optional[str]
    deadline: Optional[str]
    status: Optional[str]
    icon: Optional[str]
    embed_url_particulier: Optional[str]
    embed_url_entreprise: Optional[str]
    embed_url_results: Optional[str]
    report_url_basic: Optional[str]
    report_url_premium: Optional[str]
    is_active: bool
    created_at: datetime

    class Config:
        from_attributes = True
