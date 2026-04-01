"""
Schemas Pydantic pour l'administration des utilisateurs.
"""
from typing import Optional
from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr

from app.schemas.enums import AdminRole, UserPlan


class AdminUserCreate(BaseModel):
    email: EmailStr
    full_name: str
    password: Optional[str] = None
    plan: UserPlan = "basic"
    is_active: bool = True
    is_admin: bool = False
    admin_role: Optional[AdminRole] = None
    parent_user_id: Optional[int] = None


class AdminUserUpdate(BaseModel):
    email: Optional[EmailStr] = None
    full_name: Optional[str] = None
    plan: Optional[UserPlan] = None
    is_active: Optional[bool] = None
    is_admin: Optional[bool] = None
    admin_role: Optional[AdminRole] = None
    new_password: Optional[str] = None


class AdminUserResponse(BaseModel):
    id: int
    email: str
    full_name: str
    plan: UserPlan
    is_active: bool
    is_admin: bool
    admin_role: Optional[AdminRole] = None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)
