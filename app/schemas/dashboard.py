"""
Schemas Pydantic pour le dashboard et les statistiques.
"""
from pydantic import BaseModel
from typing import Optional


class DashboardStats(BaseModel):
    studies_accessible: int
    studies_participated: int
    reports_downloaded: int
    insights_viewed: int
    subscription_days_remaining: Optional[int]
    plan: str
