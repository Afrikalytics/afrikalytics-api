"""
Schemas Pydantic pour les rapports.
"""
from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field


class ReportCreate(BaseModel):
    study_id: int
    title: str = Field(..., max_length=200)
    description: Optional[str] = Field(None, max_length=5000)
    file_url: str = Field(..., max_length=2000)
    file_name: Optional[str] = Field(None, max_length=300)
    file_size: Optional[int] = None
    report_type: Optional[str] = Field("premium", max_length=50)
    is_available: Optional[bool] = True


class ReportResponse(BaseModel):
    id: int
    study_id: int
    title: str
    description: Optional[str]
    file_url: str
    file_name: Optional[str]
    file_size: Optional[int]
    report_type: Optional[str]
    download_count: int
    is_available: bool
    created_at: datetime

    class Config:
        from_attributes = True
