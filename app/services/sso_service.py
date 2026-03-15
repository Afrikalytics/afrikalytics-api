"""Service SSO pour Google et Microsoft OAuth2."""
import logging
from urllib.parse import urlencode

import httpx

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Google OAuth2 endpoints
# ---------------------------------------------------------------------------
GOOGLE_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
GOOGLE_USERINFO_URL = "https://www.googleapis.com/oauth2/v3/userinfo"

# ---------------------------------------------------------------------------
# Microsoft OAuth2 endpoints
# ---------------------------------------------------------------------------
MICROSOFT_AUTH_URL = "https://login.microsoftonline.com/{tenant}/oauth2/v2.0/authorize"
MICROSOFT_TOKEN_URL = "https://login.microsoftonline.com/{tenant}/oauth2/v2.0/token"
MICROSOFT_USERINFO_URL = "https://graph.microsoft.com/v1.0/me"


# ============================= GOOGLE =====================================


async def get_google_auth_url(
    client_id: str, redirect_uri: str, state: str
) -> str:
    """Generate the Google OAuth2 authorization URL."""
    params = {
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "scope": "openid email profile",
        "state": state,
        "access_type": "offline",
        "prompt": "consent",
    }
    return f"{GOOGLE_AUTH_URL}?{urlencode(params)}"


async def exchange_google_code(
    code: str, client_id: str, client_secret: str, redirect_uri: str
) -> dict:
    """Exchange the Google authorization code for tokens."""
    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.post(
            GOOGLE_TOKEN_URL,
            data={
                "code": code,
                "client_id": client_id,
                "client_secret": client_secret,
                "redirect_uri": redirect_uri,
                "grant_type": "authorization_code",
            },
        )
        response.raise_for_status()
        return response.json()


async def get_google_user_info(access_token: str) -> dict:
    """Fetch user info from Google using the access token."""
    async with httpx.AsyncClient(timeout=15.0) as client:
        response = await client.get(
            GOOGLE_USERINFO_URL,
            headers={"Authorization": f"Bearer {access_token}"},
        )
        response.raise_for_status()
        return response.json()


# ============================= MICROSOFT ==================================


async def get_microsoft_auth_url(
    client_id: str, tenant_id: str, redirect_uri: str, state: str
) -> str:
    """Generate the Microsoft OAuth2 authorization URL."""
    base = MICROSOFT_AUTH_URL.format(tenant=tenant_id)
    params = {
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "scope": "openid email profile User.Read",
        "state": state,
        "response_mode": "query",
    }
    return f"{base}?{urlencode(params)}"


async def exchange_microsoft_code(
    code: str,
    client_id: str,
    client_secret: str,
    tenant_id: str,
    redirect_uri: str,
) -> dict:
    """Exchange the Microsoft authorization code for tokens."""
    token_url = MICROSOFT_TOKEN_URL.format(tenant=tenant_id)
    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.post(
            token_url,
            data={
                "code": code,
                "client_id": client_id,
                "client_secret": client_secret,
                "redirect_uri": redirect_uri,
                "grant_type": "authorization_code",
                "scope": "openid email profile User.Read",
            },
        )
        response.raise_for_status()
        return response.json()


async def get_microsoft_user_info(access_token: str) -> dict:
    """Fetch user info from Microsoft Graph API."""
    async with httpx.AsyncClient(timeout=15.0) as client:
        response = await client.get(
            MICROSOFT_USERINFO_URL,
            headers={"Authorization": f"Bearer {access_token}"},
        )
        response.raise_for_status()
        return response.json()
