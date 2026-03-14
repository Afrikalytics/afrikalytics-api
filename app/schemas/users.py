"""
Schemas Pydantic pour les utilisateurs.
Extrait de main.py — schemas: UserCreate, PasswordChange, EnterpriseUserAdd.
UserResponse et TokenResponse sont dans app/schemas/auth.py (partages).
"""
from pydantic import BaseModel, EmailStr, Field


class UserCreate(BaseModel):
    """Schema pour creation via Zapier (apres paiement WooCommerce)."""
    email: EmailStr = Field(..., max_length=254)
    name: str = Field(..., max_length=100)
    plan: str = Field(..., max_length=50)
    order_id: str = Field(..., max_length=100)


class PasswordChange(BaseModel):
    """Schema pour le changement de mot de passe."""
    current_password: str = Field(..., max_length=128)
    new_password: str = Field(..., max_length=128)


class EnterpriseUserAdd(BaseModel):
    """Schema pour ajouter un membre a l'equipe entreprise."""
    email: EmailStr = Field(..., max_length=254)
    full_name: str = Field(..., max_length=100)
