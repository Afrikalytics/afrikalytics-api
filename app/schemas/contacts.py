"""
Schemas Pydantic pour les contacts.
"""
from datetime import datetime
from typing import Optional
from pydantic import BaseModel, EmailStr


class ContactCreate(BaseModel):
    name: str
    email: EmailStr
    company: Optional[str] = None
    message: str


class ContactResponse(BaseModel):
    id: int
    name: str
    email: str
    company: Optional[str]
    message: str
    is_read: bool
    created_at: datetime

    class Config:
        from_attributes = True
