"""
Unit tests for core auth functions — app/auth.py

Tests for:
- hash_password / verify_password (bcrypt)
- create_access_token / create_refresh_token (JWT creation)
- decode_access_token (JWT validation, expiry, invalid tokens)
- validate_password (password complexity rules)

TDD RED phase: these tests define the expected contract.
"""
import os

# Ensure env vars are set BEFORE importing app modules (standalone execution)
os.environ.setdefault("SECRET_KEY", "test-secret-key-for-ci")
os.environ.setdefault("DATABASE_URL", "sqlite:///./test.db")

import time
from datetime import timedelta, datetime, timezone

import pytest

from app.auth import (
    hash_password,
    verify_password,
    create_access_token,
    create_refresh_token,
    decode_access_token,
    ALGORITHM,
    SECRET_KEY,
)
from app.utils import validate_password


# ================================================================
# hash_password / verify_password
# ================================================================

class TestHashPassword:
    """Unit tests for bcrypt password hashing."""

    def test_hash_returns_string(self):
        result = hash_password("SomePassword123!")
        assert isinstance(result, str)

    def test_hash_is_not_plaintext(self):
        password = "SomePassword123!"
        hashed = hash_password(password)
        assert hashed != password

    def test_hash_starts_with_bcrypt_prefix(self):
        hashed = hash_password("SomePassword123!")
        assert hashed.startswith("$2b$") or hashed.startswith("$2a$")

    def test_same_password_produces_different_hashes(self):
        """bcrypt salt ensures unique hashes each time."""
        h1 = hash_password("SamePassword!")
        h2 = hash_password("SamePassword!")
        assert h1 != h2

    def test_hash_handles_unicode_password(self):
        hashed = hash_password("Mot2Passe!àéï")
        assert isinstance(hashed, str)
        assert len(hashed) > 0

    def test_hash_handles_empty_string(self):
        """Empty password should still produce a valid hash."""
        hashed = hash_password("")
        assert isinstance(hashed, str)


class TestVerifyPassword:
    """Unit tests for bcrypt password verification."""

    def test_correct_password_returns_true(self):
        password = "CorrectPass123!"
        hashed = hash_password(password)
        assert verify_password(password, hashed) is True

    def test_wrong_password_returns_false(self):
        hashed = hash_password("CorrectPass123!")
        assert verify_password("WrongPass456!", hashed) is False

    def test_empty_password_against_hash_returns_false(self):
        hashed = hash_password("SomePassword123!")
        assert verify_password("", hashed) is False

    def test_invalid_hash_returns_false(self):
        """verify_password with a non-bcrypt hash should return False, not crash."""
        assert verify_password("anything", "not-a-bcrypt-hash") is False

    def test_unicode_password_roundtrip(self):
        password = "PässwördÉ123!"
        hashed = hash_password(password)
        assert verify_password(password, hashed) is True

    def test_case_sensitive(self):
        password = "CaseSensitive1!"
        hashed = hash_password(password)
        assert verify_password("casesensitive1!", hashed) is False


# ================================================================
# create_access_token
# ================================================================

class TestCreateAccessToken:
    """Unit tests for JWT access token creation."""

    def test_returns_string(self):
        token = create_access_token(data={"sub": "user@test.com"})
        assert isinstance(token, str)

    def test_token_has_three_parts(self):
        """JWT must have header.payload.signature format."""
        token = create_access_token(data={"sub": "user@test.com"})
        assert len(token.split(".")) == 3

    def test_token_contains_sub_claim(self):
        token = create_access_token(data={"sub": "user@test.com"})
        payload = decode_access_token(token)
        assert payload["sub"] == "user@test.com"

    def test_token_contains_exp_claim(self):
        token = create_access_token(data={"sub": "user@test.com"})
        payload = decode_access_token(token)
        assert "exp" in payload

    def test_token_contains_jti_claim(self):
        """Each token must have a unique identifier for blacklisting."""
        token = create_access_token(data={"sub": "user@test.com"})
        payload = decode_access_token(token)
        assert "jti" in payload

    def test_token_type_is_access(self):
        token = create_access_token(data={"sub": "user@test.com"})
        payload = decode_access_token(token)
        assert payload["token_type"] == "access"

    def test_custom_expires_delta(self):
        token = create_access_token(
            data={"sub": "user@test.com"},
            expires_delta=timedelta(minutes=5),
        )
        payload = decode_access_token(token)
        exp = datetime.fromtimestamp(payload["exp"], tz=timezone.utc)
        now = datetime.now(timezone.utc)
        # Should expire within ~5 minutes (with some tolerance)
        diff = (exp - now).total_seconds()
        assert 200 < diff < 400

    def test_two_tokens_have_different_jti(self):
        t1 = create_access_token(data={"sub": "user@test.com"})
        t2 = create_access_token(data={"sub": "user@test.com"})
        p1 = decode_access_token(t1)
        p2 = decode_access_token(t2)
        assert p1["jti"] != p2["jti"]

    def test_preserves_extra_data(self):
        token = create_access_token(data={"sub": "user@test.com", "user_id": 42})
        payload = decode_access_token(token)
        assert payload["user_id"] == 42


# ================================================================
# create_refresh_token
# ================================================================

class TestCreateRefreshToken:
    """Unit tests for JWT refresh token creation."""

    def test_returns_string(self):
        token = create_refresh_token(data={"sub": "user@test.com"})
        assert isinstance(token, str)

    def test_token_type_is_refresh(self):
        token = create_refresh_token(data={"sub": "user@test.com"})
        payload = decode_access_token(token)
        assert payload["token_type"] == "refresh"

    def test_refresh_expires_later_than_access(self):
        access = create_access_token(data={"sub": "user@test.com"})
        refresh = create_refresh_token(data={"sub": "user@test.com"})
        a_payload = decode_access_token(access)
        r_payload = decode_access_token(refresh)
        assert r_payload["exp"] > a_payload["exp"]

    def test_has_jti(self):
        token = create_refresh_token(data={"sub": "user@test.com"})
        payload = decode_access_token(token)
        assert "jti" in payload


# ================================================================
# decode_access_token
# ================================================================

class TestDecodeAccessToken:
    """Unit tests for JWT decoding and validation."""

    def test_valid_token_returns_payload(self):
        token = create_access_token(data={"sub": "user@test.com"})
        payload = decode_access_token(token)
        assert payload is not None
        assert payload["sub"] == "user@test.com"

    def test_expired_token_raises_valueerror(self):
        token = create_access_token(
            data={"sub": "user@test.com"},
            expires_delta=timedelta(seconds=-1),
        )
        with pytest.raises(ValueError, match="expire"):
            decode_access_token(token)

    def test_invalid_token_returns_none(self):
        result = decode_access_token("not.a.valid.jwt.token")
        assert result is None

    def test_tampered_token_returns_none(self):
        token = create_access_token(data={"sub": "user@test.com"})
        # Tamper with the signature
        tampered = token[:-4] + "XXXX"
        result = decode_access_token(tampered)
        assert result is None

    def test_empty_string_returns_none(self):
        result = decode_access_token("")
        assert result is None

    def test_wrong_algorithm_token_returns_none(self):
        """A token signed with a different algorithm should be rejected."""
        import jwt
        payload = {"sub": "user@test.com", "exp": datetime.now(timezone.utc) + timedelta(hours=1)}
        token = jwt.encode(payload, "different-secret", algorithm="HS384")
        result = decode_access_token(token)
        assert result is None

    def test_hs256_expired_token_raises_valueerror(self):
        """An expired HS256 legacy token must raise ValueError (not return None)."""
        import jwt
        payload = {
            "sub": "legacy@test.com",
            "exp": datetime.now(timezone.utc) - timedelta(hours=1),
        }
        expired_legacy = jwt.encode(payload, SECRET_KEY, algorithm="HS256")
        with pytest.raises(ValueError, match="expire"):
            decode_access_token(expired_legacy)

    def test_different_rsa_key_returns_none(self):
        """A token signed with a different RSA private key must be rejected."""
        import jwt
        from cryptography.hazmat.primitives.asymmetric import rsa
        from cryptography.hazmat.primitives import serialization

        other_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        other_pem = other_key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption(),
        )
        payload = {
            "sub": "attacker@test.com",
            "exp": datetime.now(timezone.utc) + timedelta(hours=1),
        }
        forged_token = jwt.encode(payload, other_pem, algorithm="RS256")
        result = decode_access_token(forged_token)
        assert result is None

    def test_hs256_valid_fallback(self):
        """A valid HS256 token should be decoded via fallback."""
        import jwt
        payload = {
            "sub": "legacy@test.com",
            "exp": datetime.now(timezone.utc) + timedelta(hours=1),
        }
        legacy_token = jwt.encode(payload, SECRET_KEY, algorithm="HS256")
        decoded = decode_access_token(legacy_token)
        assert decoded is not None
        assert decoded["sub"] == "legacy@test.com"


# ================================================================
# _load_rsa_keys (env var path)
# ================================================================

class TestLoadRSAKeys:
    """Unit tests for RSA key loading from environment."""

    def test_load_keys_from_env_vars(self):
        """When JWT_PRIVATE_KEY and JWT_PUBLIC_KEY are set, they should be used."""
        import base64
        from cryptography.hazmat.primitives.asymmetric import rsa
        from cryptography.hazmat.primitives import serialization
        from unittest.mock import patch, MagicMock

        # Generate a test key pair
        key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        priv_pem = key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption(),
        )
        pub_pem = key.public_key().public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo,
        )
        priv_b64 = base64.b64encode(priv_pem).decode()
        pub_b64 = base64.b64encode(pub_pem).decode()

        # Mock settings to return our test keys
        mock_settings = MagicMock()
        mock_settings.jwt_private_key = priv_b64
        mock_settings.jwt_public_key = pub_b64

        from app.auth import _load_rsa_keys
        with patch("app.auth.settings", mock_settings):
            loaded_priv, loaded_pub = _load_rsa_keys()

        assert loaded_priv == priv_pem
        assert loaded_pub == pub_pem

    def test_auto_generates_keys_when_env_empty(self):
        """When env vars are empty, ephemeral keys should be generated."""
        from unittest.mock import patch, MagicMock

        mock_settings = MagicMock()
        mock_settings.jwt_private_key = ""
        mock_settings.jwt_public_key = ""

        from app.auth import _load_rsa_keys
        with patch("app.auth.settings", mock_settings):
            priv, pub = _load_rsa_keys()

        assert b"BEGIN PRIVATE KEY" in priv
        assert b"BEGIN PUBLIC KEY" in pub


# ================================================================
# validate_password
# ================================================================

class TestValidatePassword:
    """Unit tests for password complexity validation."""

    def test_valid_password(self):
        is_valid, msg = validate_password("StrongPass1!")
        assert is_valid is True
        assert msg == ""

    def test_too_short(self):
        is_valid, msg = validate_password("Ab1!")
        assert is_valid is False
        assert "8" in msg

    def test_no_uppercase(self):
        is_valid, msg = validate_password("nouppercase1!")
        assert is_valid is False
        assert "majuscule" in msg.lower()

    def test_no_lowercase(self):
        is_valid, msg = validate_password("NOLOWERCASE1!")
        assert is_valid is False
        assert "minuscule" in msg.lower()

    def test_no_digit(self):
        is_valid, msg = validate_password("NoDigitHere!")
        assert is_valid is False

    def test_no_special_char(self):
        is_valid, msg = validate_password("NoSpecialChar1")
        assert is_valid is False
        assert "spécial" in msg.lower() or "special" in msg.lower()

    def test_exactly_8_chars_valid(self):
        is_valid, _ = validate_password("Abcdef1!")
        assert is_valid is True

    def test_unicode_special_chars(self):
        """Password with unicode should still be validated for complexity."""
        is_valid, _ = validate_password("Motdépàsse1!")
        assert is_valid is True
