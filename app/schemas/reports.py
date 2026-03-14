"""
Schemas Pydantic pour les rapports.
"""
from datetime import datetime
from typing import Optional
from pydantic import BaseModel


class ReportCreate(BaseModel):
    study_id: int
    title: str
    description: Optional[str] = None
    file_url: str
    file_name: Optional[str] = None
    file_size: Optional[int] = None
    report_type: Optional[str] = "premium"
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
