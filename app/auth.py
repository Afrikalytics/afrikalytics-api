import uuid

import bcrypt
import jwt
from jwt.exceptions import ExpiredSignatureError, PyJWTError
from datetime import datetime, timedelta, timezone

from app.config import get_settings

settings = get_settings()

# Configuration
SECRET_KEY = settings.secret_key
ALGORITHM = settings.algorithm
ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 24 * settings.access_token_expire_days
REFRESH_TOKEN_EXPIRE_DAYS = settings.refresh_token_expire_days


def hash_password(password: str) -> str:
    """
    Hasher un mot de passe
    """
    password_bytes = password.encode('utf-8')
    salt = bcrypt.gensalt()
    hashed = bcrypt.hashpw(password_bytes, salt)
    return hashed.decode('utf-8')


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """
    Vérifier un mot de passe
    """
    try:
        password_bytes = plain_password.encode('utf-8')
        hashed_bytes = hashed_password.encode('utf-8')
        return bcrypt.checkpw(password_bytes, hashed_bytes)
    except Exception:
        return False


def create_access_token(data: dict, expires_delta: timedelta = None) -> str:
    """
    Créer un token JWT d'accès.
    """
    to_encode = data.copy()

    if expires_delta:
        expire = datetime.now(timezone.utc) + expires_delta
    else:
        expire = datetime.now(timezone.utc) + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)

    to_encode.update({"exp": expire, "token_type": "access", "jti": str(uuid.uuid4())})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)

    return encoded_jwt


def create_refresh_token(data: dict) -> str:
    """
    Créer un refresh token JWT (longue durée, 30 jours).
    """
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS)
    to_encode.update({"exp": expire, "token_type": "refresh", "jti": str(uuid.uuid4())})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt


def decode_access_token(token: str) -> dict:
    """
    Décoder et vérifier un token JWT.
    Retourne le payload ou None si invalide.
    Lève une ValueError avec message descriptif pour les tokens expirés.
    """
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        return payload
    except ExpiredSignatureError:
        raise ValueError("Token expiré")
    except PyJWTError:
        return None
