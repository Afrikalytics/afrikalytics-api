"""
Schemas Pydantic pour les logs d'audit.
"""
from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel


class AuditLogResponse(BaseModel):
    id: int
    user_id: int
    user_email: Optional[str] = None
    action: str
    resource_type: str
    resource_id: Optional[int] = None
    details: Optional[str] = None
    ip_address: Optional[str] = None
    created_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class AuditLogListResponse(BaseModel):
    items: List[AuditLogResponse]
    total: int
