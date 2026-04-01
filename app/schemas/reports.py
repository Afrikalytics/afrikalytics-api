"""
Schemas Pydantic pour les rapports.
"""
from datetime import datetime
from typing import Optional
from pydantic import BaseModel, ConfigDict, Field

from app.schemas.enums import ReportType


class ReportCreate(BaseModel):
    study_id: int
    title: str = Field(..., max_length=200)
    description: Optional[str] = Field(None, max_length=5000)
    file_url: str = Field(..., max_length=2000)
    file_name: Optional[str] = Field(None, max_length=300)
    file_size: Optional[int] = None
    report_type: Optional[ReportType] = "premium"
    is_available: Optional[bool] = True


class ReportUpdate(BaseModel):
    study_id: Optional[int] = None
    title: Optional[str] = Field(None, max_length=200)
    description: Optional[str] = Field(None, max_length=5000)
    file_url: Optional[str] = Field(None, max_length=2000)
    file_name: Optional[str] = Field(None, max_length=300)
    file_size: Optional[int] = None
    report_type: Optional[ReportType] = None
    is_available: Optional[bool] = None

    model_config = ConfigDict(from_attributes=True)


class ReportResponse(BaseModel):
    id: int
    study_id: int
    title: str
    description: Optional[str]
    file_url: str
    file_name: Optional[str]
    file_size: Optional[int]
    report_type: Optional[ReportType]
    download_count: int
    is_available: bool
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)
