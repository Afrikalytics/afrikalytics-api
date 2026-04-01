"""
JWT authentication module — RS256 (primary) with HS256 fallback for migration.

Key management:
  - Production: set JWT_PRIVATE_KEY and JWT_PUBLIC_KEY env vars (base64-encoded PEM).
  - Development: keys are auto-generated at startup if not provided.
  - Migration: existing HS256 tokens are still accepted during decode (fallback).
"""

import base64
import logging
import uuid

import bcrypt
import jwt
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from jwt.exceptions import ExpiredSignatureError, PyJWTError
from datetime import datetime, timedelta, timezone

from app.config import get_settings

logger = logging.getLogger(__name__)

settings = get_settings()

# Configuration
SECRET_KEY = settings.secret_key  # kept for HS256 fallback decode
ALGORITHM = settings.algorithm
ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 24 * settings.access_token_expire_days
REFRESH_TOKEN_EXPIRE_DAYS = settings.refresh_token_expire_days


def _load_rsa_keys() -> tuple:
    """Load or generate RSA key pair for RS256 signing."""
    private_key_b64 = settings.jwt_private_key
    public_key_b64 = settings.jwt_public_key

    if private_key_b64 and public_key_b64:
        private_pem = base64.b64decode(private_key_b64)
        public_pem = base64.b64decode(public_key_b64)
        logger.info("RS256 keys loaded from environment")
        return private_pem, public_pem

    # Dev mode: auto-generate ephemeral RSA keys
    logger.warning(
        "JWT_PRIVATE_KEY / JWT_PUBLIC_KEY not set — generating ephemeral RSA keys. "
        "DO NOT use this in production."
    )
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    private_pem = key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )
    public_pem = key.public_key().public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    )
    return private_pem, public_pem


_PRIVATE_KEY, _PUBLIC_KEY = _load_rsa_keys()


def hash_password(password: str) -> str:
    """Hash a password with bcrypt."""
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify a password against its bcrypt hash."""
    try:
        return bcrypt.checkpw(
            plain_password.encode("utf-8"),
            hashed_password.encode("utf-8"),
        )
    except Exception:
        return False


def create_access_token(data: dict, expires_delta: timedelta | None = None) -> str:
    """Create a JWT access token signed with RS256."""
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + (
        expires_delta or timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    )
    to_encode.update({
        "exp": expire,
        "token_type": "access",
        "jti": str(uuid.uuid4()),
        "alg_version": "rs256_v1",
    })
    return jwt.encode(to_encode, _PRIVATE_KEY, algorithm="RS256")


def create_refresh_token(data: dict, family_id: str | None = None) -> str:
    """
    Create a refresh token with rotation support.

    Args:
        data: Token payload (must include 'sub').
        family_id: Reuse existing family for rotation; None creates a new family.
    """
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS)
    to_encode.update({
        "exp": expire,
        "token_type": "refresh",
        "jti": str(uuid.uuid4()),
        "family_id": family_id or str(uuid.uuid4()),
        "alg_version": "rs256_v1",
    })
    return jwt.encode(to_encode, _PRIVATE_KEY, algorithm="RS256")


def decode_access_token(token: str) -> dict | None:
    """
    Decode and verify a JWT token.

    Tries RS256 first, then falls back to HS256 for tokens issued before migration.
    Returns the payload dict, or None if invalid.
    Raises ValueError for expired tokens (caller should return 401).
    """
    # Try RS256 first (new tokens)
    try:
        return jwt.decode(token, _PUBLIC_KEY, algorithms=["RS256"])
    except ExpiredSignatureError:
        raise ValueError("Token expire")
    except PyJWTError:
        pass

    # Fallback: HS256 (legacy tokens issued before migration)
    try:
        return jwt.decode(token, SECRET_KEY, algorithms=["HS256"])
    except ExpiredSignatureError:
        raise ValueError("Token expire")
    except PyJWTError:
        return None
