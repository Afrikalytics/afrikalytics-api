"""Pydantic schemas for the export module."""

from typing import Literal

from pydantic import BaseModel

ExportFormat = Literal["pdf", "xlsx", "csv"]


class ExportRequest(BaseModel):
    """Query parameters for export endpoints."""
    format: ExportFormat = "pdf"
