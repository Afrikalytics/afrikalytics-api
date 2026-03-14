"""
Schemas Pydantic pour l'authentification.
Extrait de main.py — schemas: UserRegister, UserLogin, UserResponse, TokenResponse,
ForgotPassword, ResetPassword, VerifyCodeRequest, LoginPendingResponse.
"""
from pydantic import BaseModel, EmailStr
from typing import Optional
from datetime import datetime


class UserRegister(BaseModel):
    """Schema pour l'inscription d'un nouvel utilisateur."""
    email: EmailStr
    name: str
    password: str


class UserLogin(BaseModel):
    """Schema pour la connexion."""
    email: EmailStr
    password: str


class UserResponse(BaseModel):
    """Schema de reponse utilisateur (utilise dans TokenResponse et ailleurs)."""
    id: int
    email: str
    full_name: str
    plan: str
    is_active: bool
    is_admin: bool = False
    admin_role: Optional[str] = None
    parent_user_id: Optional[int] = None
    created_at: datetime

    class Config:
        from_attributes = True


class TokenResponse(BaseModel):
    """Schema de reponse apres authentification reussie."""
    access_token: str
    refresh_token: Optional[str] = None
    token_type: str
    expires_at: Optional[str] = None
    user: UserResponse


class RefreshTokenRequest(BaseModel):
    """Schema pour la demande de rafraichissement de token."""
    refresh_token: str


class RefreshTokenResponse(BaseModel):
    """Schema de reponse apres rafraichissement de token."""
    access_token: str
    token_type: str = "bearer"
    expires_at: str


class ForgotPassword(BaseModel):
    """Schema pour la demande de reset de mot de passe."""
    email: EmailStr


class ResetPassword(BaseModel):
    """Schema pour la reinitialisation du mot de passe."""
    token: str
    new_password: str


class VerifyCodeRequest(BaseModel):
    """Schema pour la verification du code 2FA."""
    email: EmailStr
    code: str


class LoginPendingResponse(BaseModel):
    """Schema de reponse quand le login attend la verification 2FA."""
    status: str
    message: str
    email: str
    requires_verification: bool
