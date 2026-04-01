"""
Tests du module d'authentification RS256 + rotation des refresh tokens.

Couvre:
- Hachage et verification des mots de passe (bcrypt)
- Creation et decodage des tokens JWT RS256
- Fallback HS256 pour les tokens legacy
- Rotation des refresh tokens via POST /api/auth/refresh
- Detection de rejeu (replay detection) et revocation de famille
"""

import time
import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import jwt as pyjwt
import pytest

from app.auth import (
    _PRIVATE_KEY,
    _PUBLIC_KEY,
    SECRET_KEY,
    create_access_token,
    create_refresh_token,
    decode_access_token,
    hash_password,
    verify_password,
)


# =====================================================================
#  UNIT TESTS — app/auth.py
# =====================================================================


@pytest.mark.unit
class TestHashPassword:
    """Tests unitaires pour le hachage bcrypt."""

    def test_hash_password_returns_bcrypt_hash(self):
        """Le hash retourne doit commencer par $2b$ (bcrypt)."""
        hashed = hash_password("MonMotDePasse123!")
        assert hashed.startswith("$2b$")
        assert hashed != "MonMotDePasse123!"

    def test_verify_password_correct(self):
        """Un mot de passe correct doit etre verifie avec succes."""
        hashed = hash_password("Secret42")
        assert verify_password("Secret42", hashed) is True

    def test_verify_password_incorrect(self):
        """Un mot de passe incorrect doit etre rejete."""
        hashed = hash_password("Secret42")
        assert verify_password("MauvaisMotDePasse", hashed) is False


@pytest.mark.unit
class TestCreateAccessToken:
    """Tests unitaires pour la creation de tokens d'acces RS256."""

    def test_create_access_token_has_rs256_header(self):
        """Le token doit etre signe en RS256 et decodable avec la cle publique."""
        token = create_access_token(data={"sub": "user@test.com"})
        header = pyjwt.get_unverified_header(token)
        assert header["alg"] == "RS256"
        # Decodage avec la cle publique doit fonctionner
        payload = pyjwt.decode(token, _PUBLIC_KEY, algorithms=["RS256"])
        assert payload["sub"] == "user@test.com"

    def test_create_access_token_contains_jti(self):
        """Chaque token doit contenir un identifiant unique (jti)."""
        t1 = create_access_token(data={"sub": "a@b.com"})
        t2 = create_access_token(data={"sub": "a@b.com"})
        p1 = pyjwt.decode(t1, _PUBLIC_KEY, algorithms=["RS256"])
        p2 = pyjwt.decode(t2, _PUBLIC_KEY, algorithms=["RS256"])
        assert "jti" in p1
        assert p1["jti"] != p2["jti"]

    def test_create_access_token_contains_alg_version(self):
        """Le payload doit contenir alg_version='rs256_v1'."""
        token = create_access_token(data={"sub": "x@y.com"})
        payload = pyjwt.decode(token, _PUBLIC_KEY, algorithms=["RS256"])
        assert payload["alg_version"] == "rs256_v1"


@pytest.mark.unit
class TestCreateRefreshToken:
    """Tests unitaires pour la creation de refresh tokens."""

    def test_create_refresh_token_has_family_id(self):
        """Un refresh token sans family_id explicite doit en generer un."""
        token = create_refresh_token(data={"sub": "u@t.com"})
        payload = pyjwt.decode(token, _PUBLIC_KEY, algorithms=["RS256"])
        assert payload["token_type"] == "refresh"
        assert "family_id" in payload
        # family_id auto-genere = format UUID
        uuid.UUID(payload["family_id"])

    def test_create_refresh_token_custom_family_id(self):
        """Un family_id fourni doit etre preserve dans le token."""
        fid = "my-family-123"
        token = create_refresh_token(data={"sub": "u@t.com"}, family_id=fid)
        payload = pyjwt.decode(token, _PUBLIC_KEY, algorithms=["RS256"])
        assert payload["family_id"] == fid


@pytest.mark.unit
class TestDecodeAccessToken:
    """Tests unitaires pour le decodage de tokens (RS256 + fallback HS256)."""

    def test_decode_access_token_rs256_valid(self):
        """Un token RS256 valide doit etre decode correctement."""
        token = create_access_token(data={"sub": "ok@test.com"})
        payload = decode_access_token(token)
        assert payload is not None
        assert payload["sub"] == "ok@test.com"
        assert payload["token_type"] == "access"

    def test_decode_access_token_expired_raises_valueerror(self):
        """Un token expire doit lever ValueError."""
        token = create_access_token(
            data={"sub": "exp@test.com"},
            expires_delta=timedelta(seconds=-1),
        )
        with pytest.raises(ValueError, match="expire"):
            decode_access_token(token)

    def test_decode_access_token_invalid_returns_none(self):
        """Un token totalement invalide doit retourner None."""
        result = decode_access_token("ceci.nest.pas.un.token")
        assert result is None

    def test_decode_access_token_hs256_fallback(self):
        """Un token legacy HS256 doit etre decode via le fallback."""
        payload = {
            "sub": "legacy@test.com",
            "exp": datetime.now(timezone.utc) + timedelta(hours=1),
        }
        legacy_token = pyjwt.encode(payload, SECRET_KEY, algorithm="HS256")
        decoded = decode_access_token(legacy_token)
        assert decoded is not None
        assert decoded["sub"] == "legacy@test.com"


# =====================================================================
#  INTEGRATION TESTS — POST /api/auth/refresh
# =====================================================================


def _make_refresh_body(refresh_token: str) -> dict:
    """Helper pour construire le body de la requete /refresh."""
    return {"refresh_token": refresh_token}


@pytest.mark.integration
class TestRefreshEndpoint:
    """Tests d'integration pour la rotation des refresh tokens."""

    def test_refresh_returns_new_access_and_refresh_token(
        self, client, test_user
    ):
        """Un refresh valide doit retourner un nouveau couple de tokens."""
        rt = create_refresh_token(
            data={"sub": test_user.email, "user_id": test_user.id}
        )
        resp = client.post("/api/auth/refresh", json=_make_refresh_body(rt))
        assert resp.status_code == 200
        body = resp.json()
        assert "access_token" in body
        assert "refresh_token" in body
        assert body["token_type"] == "bearer"
        assert body["refresh_token"] != rt  # rotation: nouveau token

    def test_refresh_blacklists_old_token(self, client, test_user, db):
        """Apres utilisation, le jti du refresh token doit etre blackliste."""
        from app.models import TokenBlacklist

        rt = create_refresh_token(
            data={"sub": test_user.email, "user_id": test_user.id}
        )
        old_jti = pyjwt.decode(rt, _PUBLIC_KEY, algorithms=["RS256"])["jti"]

        resp = client.post("/api/auth/refresh", json=_make_refresh_body(rt))
        assert resp.status_code == 200

        from sqlalchemy import select

        entry = db.execute(
            select(TokenBlacklist).where(TokenBlacklist.jti == old_jti)
        ).scalar_one_or_none()
        assert entry is not None

    def test_refresh_replay_detection(self, client, test_user):
        """Rejouer un refresh token deja utilise doit echouer (vol detecte)."""
        rt = create_refresh_token(
            data={"sub": test_user.email, "user_id": test_user.id}
        )
        # Premier usage — succes
        resp1 = client.post("/api/auth/refresh", json=_make_refresh_body(rt))
        assert resp1.status_code == 200

        # Deuxieme usage du meme token — doit etre rejete (replay)
        resp2 = client.post("/api/auth/refresh", json=_make_refresh_body(rt))
        assert resp2.status_code == 401
        assert "utilisé" in resp2.json()["detail"].lower() or "reconnecter" in resp2.json()["detail"].lower()

    def test_refresh_with_access_token_rejected(self, client, test_user):
        """Passer un access token au lieu d'un refresh token doit echouer."""
        at = create_access_token(
            data={"sub": test_user.email, "user_id": test_user.id}
        )
        resp = client.post("/api/auth/refresh", json=_make_refresh_body(at))
        assert resp.status_code == 401
        assert "refresh" in resp.json()["detail"].lower()

    def test_refresh_expired_token_returns_401(self, client, test_user):
        """Un refresh token expire doit retourner 401."""
        expired_payload = {
            "sub": test_user.email,
            "user_id": test_user.id,
            "token_type": "refresh",
            "jti": str(uuid.uuid4()),
            "family_id": str(uuid.uuid4()),
            "exp": datetime.now(timezone.utc) - timedelta(seconds=10),
        }
        expired_rt = pyjwt.encode(expired_payload, _PRIVATE_KEY, algorithm="RS256")
        resp = client.post(
            "/api/auth/refresh", json=_make_refresh_body(expired_rt)
        )
        assert resp.status_code == 401
