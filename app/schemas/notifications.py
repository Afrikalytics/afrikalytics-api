"""
Schemas Pydantic pour les notifications in-app.
"""
from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field


class NotificationResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True, populate_by_name=True)

    id: int
    # The ORM attribute is "notification_type" (Column name in DB is still "type").
    # We expose it as "type" in the JSON response for API backward compatibility.
    type: str = Field(validation_alias="notification_type")
    title: str
    message: str
    is_read: bool
    metadata: Optional[dict[str, Any]] = Field(None, validation_alias="metadata_json")
    created_at: datetime
    read_at: Optional[datetime] = None


class NotificationListResponse(BaseModel):
    notifications: list[NotificationResponse]
    unread_count: int
    total: int


class NotificationMarkReadRequest(BaseModel):
    notification_ids: list[int] = Field(..., min_length=1, max_length=100)


class UnreadCountResponse(BaseModel):
    unread_count: int
