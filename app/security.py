"""
Cryptographic utilities for Afrikalytics API.

Centralises all hashing, token generation, and verification logic so that
the pattern is implemented once and reused across routers and services.

Design decisions
----------------
- API keys: SHA-256 hash + 8-char prefix for dashboard display.
  The raw key is returned ONCE at creation and never persisted.
- Newsletter tokens: same SHA-256 approach so confirmation/unsubscribe
  links remain short but the DB never holds revealable secrets.
- NEVER log raw tokens, raw API keys, or plaintext passwords anywhere in
  this module. Use the `mask_secret` helper when you need to log metadata.
"""

import hashlib
import hmac
import secrets
from typing import Optional


# ---------------------------------------------------------------------------
# Low-level primitives
# ---------------------------------------------------------------------------

def _sha256_hex(value: str) -> str:
    """Return the lowercase hex SHA-256 digest of a UTF-8 encoded string."""
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def constant_time_compare(val_a: str, val_b: str) -> bool:
    """Compare two strings in constant time to prevent timing side-channels."""
    return hmac.compare_digest(val_a.encode("utf-8"), val_b.encode("utf-8"))


# ---------------------------------------------------------------------------
# API Key utilities
# ---------------------------------------------------------------------------

API_KEY_PREFIX_LEN = 8   # chars kept in key_prefix column (safe to display)
API_KEY_TOKEN_BYTES = 48  # bytes of entropy for the secret portion


def generate_api_key() -> tuple[str, str, str]:
    """Generate a new API key.

    Returns
    -------
    tuple[str, str, str]
        (full_key, key_hash, key_prefix)

        - full_key   : the raw key shown ONCE to the user at creation time.
                       Never stored in the database.
        - key_hash   : SHA-256 hex digest — stored in `api_keys.key_hash`.
        - key_prefix : first ``API_KEY_PREFIX_LEN`` chars of the raw key —
                       stored in `api_keys.key_prefix` for display in the UI.

    Example
    -------
    >>> full_key, key_hash, key_prefix = generate_api_key()
    >>> assert full_key.startswith("ak_")
    >>> assert len(key_hash) == 64
    >>> assert len(key_prefix) == 8
    """
    # "ak_" prefix makes the key visually identifiable in logs and UIs
    raw = "ak_" + secrets.token_urlsafe(API_KEY_TOKEN_BYTES)
    key_hash = _sha256_hex(raw)
    key_prefix = raw[:API_KEY_PREFIX_LEN]
    return raw, key_hash, key_prefix


def hash_api_key(full_key: str) -> str:
    """Return the SHA-256 hash of an existing raw API key.

    Use this to verify an inbound key from the `X-Api-Key` header against
    the stored hash without touching the raw value.
    """
    return _sha256_hex(full_key)


def verify_api_key(full_key: str, stored_hash: str) -> bool:
    """Verify a raw API key against its stored SHA-256 hash.

    Uses constant-time comparison to prevent timing attacks.
    """
    candidate_hash = _sha256_hex(full_key)
    return constant_time_compare(candidate_hash, stored_hash)


# ---------------------------------------------------------------------------
# Newsletter token utilities
# ---------------------------------------------------------------------------

NEWSLETTER_TOKEN_BYTES = 32   # bytes of entropy
TOKEN_PREFIX_LEN = 8          # chars kept as prefix for log correlation


def generate_newsletter_token() -> tuple[str, str, str]:
    """Generate a newsletter confirmation or unsubscribe token.

    Returns
    -------
    tuple[str, str, str]
        (raw_token, token_hash, token_prefix)

        - raw_token    : the URL-safe token embedded in the email link.
                         Never stored in the database.
        - token_hash   : SHA-256 hex digest — stored in the DB column.
        - token_prefix : first ``TOKEN_PREFIX_LEN`` chars of the raw token —
                         stored for log correlation without leaking the secret.

    Example
    -------
    >>> token, tok_hash, tok_prefix = generate_newsletter_token()
    >>> assert len(token) > 30
    >>> assert len(tok_hash) == 64
    """
    raw = secrets.token_urlsafe(NEWSLETTER_TOKEN_BYTES)
    token_hash = _sha256_hex(raw)
    token_prefix = raw[:TOKEN_PREFIX_LEN]
    return raw, token_hash, token_prefix


def hash_newsletter_token(raw_token: str) -> str:
    """Return the SHA-256 hash of a raw newsletter token.

    Used to look up the subscriber row when processing a confirmation or
    unsubscribe request — the DB query uses the hash, never the raw token.
    """
    return _sha256_hex(raw_token)


def verify_newsletter_token(raw_token: str, stored_hash: str) -> bool:
    """Verify a raw newsletter token against its stored SHA-256 hash."""
    candidate_hash = _sha256_hex(raw_token)
    return constant_time_compare(candidate_hash, stored_hash)


# ---------------------------------------------------------------------------
# Log-safe masking helper
# ---------------------------------------------------------------------------

MASK_FIELDS: frozenset[str] = frozenset({
    "password",
    "hashed_password",
    "token",
    "key",
    "api_key",
    "secret",
    "access_token",
    "refresh_token",
    "authorization",
    "x-api-key",
    "confirmation_token",
    "unsubscribe_token",
    "reset_token",
    "verification_code",
    "code",
    "resend_api_key",
    "paydunya_master_key",
    "paydunya_private_key",
    "paydunya_token",
    "database_url",
    "secret_key",
})


def mask_secret(value: str, visible_chars: int = 4) -> str:
    """Mask a secret value for safe logging.

    Parameters
    ----------
    value:
        The raw secret string to mask.
    visible_chars:
        Number of leading characters to keep visible (default 4).

    Returns
    -------
    str
        A string like ``"ak_x...****"`` safe to include in log output.

    Example
    -------
    >>> mask_secret("ak_secrettoken123")
    'ak_s...****'
    """
    if not value:
        return "****"
    if len(value) <= visible_chars:
        return "****"
    return value[:visible_chars] + "...****"


def sanitize_log_dict(data: dict, visible_chars: int = 4) -> dict:
    """Return a copy of ``data`` with sensitive fields masked.

    Performs a shallow scan: only top-level keys are checked.  Nested dicts
    are replaced wholesale with ``"****"`` if their key is sensitive.

    Parameters
    ----------
    data:
        Arbitrary dict (e.g. request payload, log context).
    visible_chars:
        Passed through to :func:`mask_secret`.

    Returns
    -------
    dict
        A new dict safe to pass to logging functions.

    Example
    -------
    >>> sanitize_log_dict({"email": "a@b.com", "password": "s3cr3t!"})
    {'email': 'a@b.com', 'password': 'pass...****'}
    """
    sanitized: dict = {}
    for key, val in data.items():
        if key.lower() in MASK_FIELDS:
            sanitized[key] = mask_secret(str(val), visible_chars) if val else "****"
        else:
            sanitized[key] = val
    return sanitized
