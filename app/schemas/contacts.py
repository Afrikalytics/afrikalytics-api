"""
Schemas Pydantic pour les contacts.
"""
from datetime import datetime
from typing import Optional
from pydantic import BaseModel, EmailStr, Field


class ContactCreate(BaseModel):
    name: str = Field(..., max_length=100)
    email: EmailStr = Field(..., max_length=254)
    company: Optional[str] = Field(None, max_length=200)
    message: str = Field(..., max_length=5000)


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
