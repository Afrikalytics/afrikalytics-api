"""
Configuration centralisee avec pydantic-settings.

Toutes les variables d'environnement sont declarees ici.
Les autres modules importent `get_settings()` au lieu d'appeler `os.getenv()`.
"""

from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Application settings loaded from environment variables and .env file."""

    # --- Database ---
    database_url: str = Field(..., description="PostgreSQL connection URL")

    # --- Auth / JWT ---
    secret_key: str = Field(..., description="JWT signing key")
    algorithm: str = "HS256"
    access_token_expire_days: int = 7
    refresh_token_expire_days: int = 30

    # --- Email (Resend) ---
    resend_api_key: str = Field(default="", description="Resend API key")
    contact_email: str = Field(
        default="contact@afrikalytics.com",
        description="Contact email address",
    )

    # --- PayDunya ---
    paydunya_master_key: str = Field(default="")
    paydunya_private_key: str = Field(default="")
    paydunya_public_key: str = Field(default="")
    paydunya_token: str = Field(default="")
    paydunya_mode: str = Field(default="test")

    # --- External API URL (used for webhook callbacks) ---
    api_url: str = Field(
        default="https://web-production-ef657.up.railway.app",
        description="Public URL of this API (for webhook callbacks)",
    )

    # --- Sentry ---
    sentry_dsn: str = Field(default="")

    # --- App / Runtime ---
    environment: str = Field(default="production")
    port: int = Field(default=8000)
    railway_git_commit_sha: str = Field(default="local")

    # --- CORS ---
    allowed_origins: str = Field(
        default="",
        description="Comma-separated list of allowed CORS origins",
    )
    frontend_url: str = Field(default="")
    next_public_api_url: str = Field(default="")

    # --- Redis ---
    redis_url: str = Field(
        default="redis://localhost:6379/0",
        description="Redis connection URL",
    )

    # --- SSO Google ---
    google_client_id: str = Field(default="", description="Google OAuth2 Client ID")
    google_client_secret: str = Field(default="", description="Google OAuth2 Client Secret")

    # --- SSO Microsoft ---
    microsoft_client_id: str = Field(default="", description="Microsoft OAuth2 Client ID")
    microsoft_client_secret: str = Field(default="", description="Microsoft OAuth2 Client Secret")
    microsoft_tenant_id: str = Field(default="common", description="Microsoft tenant ID")

    # --- Integrations ---
    zapier_secret: str = Field(default="")
    cron_secret: str = Field(default="")

    model_config = {
        "env_file": ".env",
        "env_file_encoding": "utf-8",
        "extra": "ignore",
    }


@lru_cache
def get_settings() -> Settings:
    """Return cached Settings instance (singleton)."""
    return Settings()
