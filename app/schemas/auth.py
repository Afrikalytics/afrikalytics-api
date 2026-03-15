"""
Schemas Pydantic pour l'authentification.
Extrait de main.py — schemas: UserRegister, UserLogin, UserResponse, TokenResponse,
ForgotPassword, ResetPassword, VerifyCodeRequest, LoginPendingResponse.
"""
from pydantic import BaseModel, ConfigDict, EmailStr, Field
from typing import Optional
from datetime import datetime


class UserRegister(BaseModel):
    """Schema pour l'inscription d'un nouvel utilisateur."""
    email: EmailStr = Field(..., max_length=254)
    name: str = Field(..., max_length=100)
    password: str = Field(..., max_length=128)


class UserLogin(BaseModel):
    """Schema pour la connexion."""
    email: EmailStr = Field(..., max_length=254)
    password: str = Field(..., max_length=128)


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

    model_config = ConfigDict(from_attributes=True)


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
    email: EmailStr = Field(..., max_length=254)


class ResetPassword(BaseModel):
    """Schema pour la reinitialisation du mot de passe."""
    token: str = Field(..., max_length=500)
    new_password: str = Field(..., max_length=128)


class VerifyCodeRequest(BaseModel):
    """Schema pour la verification du code 2FA."""
    email: EmailStr = Field(..., max_length=254)
    code: str = Field(..., max_length=6)


class LoginPendingResponse(BaseModel):
    """Schema de reponse quand le login attend la verification 2FA."""
    status: str
    message: str
    email: str
    requires_verification: bool


class SSOAuthURL(BaseModel):
    """Schema de reponse avec l'URL d'autorisation SSO."""
    auth_url: str
    provider: str


class SSOCallbackRequest(BaseModel):
    """Schema pour le callback SSO."""
    code: str
    state: str | None = None


class SSOExchangeRequest(BaseModel):
    """
    Schema pour l'echange du code SSO contre un JWT.
    Le frontend envoie le code recu dans le parametre sso_code de la redirection.
    """
    sso_code: str = Field(..., min_length=43, max_length=64)


class SSOExchangeResponse(BaseModel):
    """Schema de reponse apres echange SSO reussi — equivalent a TokenResponse sans refresh token."""
    access_token: str
    token_type: str = "bearer"
    expires_at: str
    user: UserResponse
