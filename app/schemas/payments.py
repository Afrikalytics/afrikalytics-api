"""
Schemas Pydantic pour le module Paiements (PayDunya).
"""
from pydantic import BaseModel, EmailStr


class PaymentCreate(BaseModel):
    email: EmailStr
    name: str
    plan: str = "professionnel"
