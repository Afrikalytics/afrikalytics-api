"""
Schemas Pydantic pour le module Paiements (PayDunya).
"""
from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, EmailStr

PlanType = Literal["basic", "professionnel", "entreprise"]


class PaymentCreate(BaseModel):
    email: EmailStr
    name: str
    plan: PlanType = "professionnel"


class PaymentResponse(BaseModel):
    id: int
    user_id: Optional[int]
    amount: int
    currency: str
    provider: str
    provider_ref: Optional[str]
    plan: str
    status: str
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)
