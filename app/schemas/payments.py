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


# -------------------------------------------------------------------------
# Payment History
# -------------------------------------------------------------------------


class PaymentHistoryItem(BaseModel):
    id: int
    amount: float
    currency: str = "XOF"
    status: str  # "completed", "pending", "failed"
    plan: str
    payment_method: str
    created_at: datetime
    reference: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)


class PaymentHistoryResponse(BaseModel):
    payments: list[PaymentHistoryItem]
    total: int
    current_page: int


# -------------------------------------------------------------------------
# Current Plan
# -------------------------------------------------------------------------


class PlanFeatures(BaseModel):
    max_studies: int
    max_team_members: int
    export_pdf: bool
    api_access: bool
    custom_branding: bool


class CurrentPlanResponse(BaseModel):
    plan: str
    is_active: bool
    expires_at: Optional[datetime] = None
    features: dict
