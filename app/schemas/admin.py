"""
Schemas Pydantic pour l'administration des utilisateurs.
"""
from pydantic import BaseModel, EmailStr
from typing import Optional
from datetime import datetime


class AdminUserCreate(BaseModel):
    email: EmailStr
    full_name: str
    password: Optional[str] = None
    plan: str = "basic"
    is_active: bool = True
    is_admin: bool = False
    admin_role: Optional[str] = None
    parent_user_id: Optional[int] = None


class AdminUserUpdate(BaseModel):
    email: Optional[EmailStr] = None
    full_name: Optional[str] = None
    plan: Optional[str] = None
    is_active: Optional[bool] = None
    is_admin: Optional[bool] = None
    admin_role: Optional[str] = None
    new_password: Optional[str] = None


class AdminUserResponse(BaseModel):
    id: int
    email: str
    full_name: str
    plan: str
    is_active: bool
    is_admin: bool
    admin_role: Optional[str] = None
    created_at: datetime

    class Config:
        from_attributes = True
