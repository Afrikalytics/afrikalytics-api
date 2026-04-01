"""
Shared Literal types aligned with database CHECK constraints.

These types ensure Pydantic validation matches the DB constraints,
catching invalid values before they hit the database.
"""

from typing import Literal

# Users
UserPlan = Literal["basic", "professionnel", "entreprise"]
AdminRole = Literal[
    "super_admin", "admin_content", "admin_studies", "admin_insights", "admin_reports"
]

# Studies
StudyStatus = Literal["Ouvert", "Ferme", "Bientot"]

# Subscriptions
SubscriptionStatus = Literal["active", "cancelled", "expired"]

# Payments
PaymentStatus = Literal["pending", "completed", "failed", "refunded"]

# Reports
ReportType = Literal["basic", "premium"]

# Blog
BlogPostStatus = Literal["draft", "published", "scheduled"]
