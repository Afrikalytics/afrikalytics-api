"""
Schemas Pydantic pour les utilisateurs.
Extrait de main.py — schemas: UserCreate, PasswordChange, EnterpriseUserAdd.
UserResponse et TokenResponse sont dans app/schemas/auth.py (partages).
"""
from pydantic import BaseModel, EmailStr


class UserCreate(BaseModel):
    """Schema pour creation via Zapier (apres paiement WooCommerce)."""
    email: EmailStr
    name: str
    plan: str
    order_id: str


class PasswordChange(BaseModel):
    """Schema pour le changement de mot de passe."""
    current_password: str
    new_password: str


class EnterpriseUserAdd(BaseModel):
    """Schema pour ajouter un membre a l'equipe entreprise."""
    email: EmailStr
    full_name: str
