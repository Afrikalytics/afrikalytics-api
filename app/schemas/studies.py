"""
Schemas Pydantic pour les etudes de marche.
"""
from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime


class StudyCreate(BaseModel):
    title: str = Field(..., max_length=200)
    description: str = Field(..., max_length=5000)
    category: str = Field(..., max_length=100)
    duration: Optional[str] = Field("15-20 min", max_length=50)
    deadline: Optional[str] = Field(None, max_length=50)
    status: Optional[str] = Field("Ouvert", max_length=50)
    icon: Optional[str] = Field("users", max_length=50)
    embed_url_particulier: Optional[str] = Field(None, max_length=2000)
    embed_url_entreprise: Optional[str] = Field(None, max_length=2000)
    embed_url_results: Optional[str] = Field(None, max_length=2000)
    report_url_basic: Optional[str] = Field(None, max_length=2000)
    report_url_premium: Optional[str] = Field(None, max_length=2000)
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
