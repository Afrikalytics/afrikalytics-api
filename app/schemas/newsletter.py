"""
Schemas Pydantic pour le module Newsletter.
"""
from datetime import datetime
from typing import Optional
from pydantic import BaseModel, EmailStr, Field


class NewsletterSubscribe(BaseModel):
    email: EmailStr
    source: Optional[str] = "blog_footer"


class NewsletterSubscriberResponse(BaseModel):
    id: int
    email: str
    status: str
    is_confirmed: bool
    source: str
    subscribed_at: datetime
    confirmed_at: Optional[datetime]

    class Config:
        from_attributes = True


class NewsletterCampaignCreate(BaseModel):
    blog_post_id: Optional[int] = None
    subject: str = Field(..., min_length=1, max_length=255)
    preview_text: Optional[str] = None
    status: Optional[str] = "draft"
    scheduled_at: Optional[datetime] = None


class NewsletterCampaignResponse(BaseModel):
    id: int
    blog_post_id: Optional[int]
    subject: str
    preview_text: Optional[str]
    status: str
    sent_at: Optional[datetime]
    scheduled_at: Optional[datetime]
    recipients_count: int
    opened_count: int
    clicked_count: int
    created_at: datetime

    class Config:
        from_attributes = True
