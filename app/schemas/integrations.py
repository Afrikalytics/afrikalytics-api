"""Schemas Pydantic pour les intégrations SDK et API keys.

Security contract
-----------------
- ``ApiKeyResponse`` (used for listing) exposes only ``key_prefix`` — the
  first 8 characters of the raw key, safe to display in the dashboard.
  The full key and its hash are never returned after creation.
- ``ApiKeyCreatedResponse`` extends ``ApiKeyResponse`` with a ``key`` field
  containing the full raw key.  This field is populated ONCE in the creation
  endpoint and is unrecoverable afterwards.
"""
from datetime import datetime
from typing import Any, List, Optional

from pydantic import BaseModel, Field


# -----------------------------------------------------------------------------
# API Key Schemas
# -----------------------------------------------------------------------------

class ApiKeyCreate(BaseModel):
    """Payload pour créer une nouvelle API key."""

    name: str = Field(..., min_length=1, max_length=100, examples=["Mon site web"])
    allowed_origins: Optional[List[str]] = Field(
        default=None,
        examples=[["https://monsite.com", "https://app.monsite.com"]],
    )
    permissions: List[str] = Field(
        default=["read"],
        examples=[["read"]],
    )


class ApiKeyResponse(BaseModel):
    """Réponse pour une API key listée.

    The full key is NEVER returned here.  Only the ``key_prefix`` (first 8
    chars of the raw key) is exposed so users can identify which key is which
    in the dashboard.
    """

    id: int
    name: str
    key_prefix: str = Field(
        description="Premiers 8 caractères de la clé — affichés pour identification.",
        examples=["ak_xK3mP9"],
    )
    is_active: bool
    allowed_origins: Optional[List[str]] = None
    permissions: List[str]
    last_used_at: Optional[datetime] = None
    created_at: datetime

    model_config = {"from_attributes": True}


class ApiKeyCreatedResponse(ApiKeyResponse):
    """Réponse à la création — contient la clé complète visible une seule fois.

    After this response is sent the full key is unrecoverable.  The user
    must save it immediately.
    """

    key: str = Field(
        description=(
            "Clé complète — visible uniquement à la création. "
            "Conservez-la immédiatement dans un gestionnaire de secrets."
        ),
        examples=["ak_xK3mP9AbCdEfGhIjKlMnOpQrStUvWxYz..."],
    )


class ApiKeyListResponse(BaseModel):
    """Liste des API keys de l'utilisateur."""

    keys: List[ApiKeyResponse]
    total: int


# -----------------------------------------------------------------------------
# Embed Data Schemas
# -----------------------------------------------------------------------------

class EmbedDataResponse(BaseModel):
    """Données d'une étude formatées pour l'embed SDK."""

    study_id: int
    title: str
    description: Optional[str] = None
    category: Optional[str] = None
    data: Optional[Any] = None        # imported_data
    columns: Optional[List[str]] = None  # imported_columns
    row_count: Optional[int] = None


class EmbedWidgetResponse(BaseModel):
    """Données formatées pour un widget spécifique."""

    study_id: int
    widget_type: str
    title: str
    data: Optional[Any] = None
    columns: Optional[List[str]] = None
    config: dict = Field(default_factory=dict)
    theme: str = "light"
