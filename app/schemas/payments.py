"""
Schemas Pydantic pour le module Paiements (PayDunya).
"""
from typing import Literal

from pydantic import BaseModel, EmailStr

PlanType = Literal["basic", "professionnel", "entreprise"]


class PaymentCreate(BaseModel):
    email: EmailStr
    name: str
    plan: PlanType = "professionnel"
