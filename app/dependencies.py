"""
Dependencies FastAPI partagees entre les routers.
Extrait de main.py pour eviter les imports circulaires.
"""
from fastapi import Depends, HTTPException, Header
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import User, TokenBlacklist
from app.auth import decode_access_token


def get_current_user(
    authorization: str = Header(None),
    db: Session = Depends(get_db)
) -> User:
    """
    Dependency FastAPI pour recuperer l'utilisateur courant depuis le token JWT.

    Usage:
        @router.get("/endpoint")
        async def endpoint(current_user: User = Depends(get_current_user)):
            ...
    """
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Token manquant")

    token = authorization.replace("Bearer ", "")

    try:
        payload = decode_access_token(token)
    except ValueError:
        # Token expired — clear 401 with descriptive message
        raise HTTPException(
            status_code=401,
            detail="Token expiré. Veuillez vous reconnecter ou utiliser le refresh token."
        )

    if not payload:
        raise HTTPException(status_code=401, detail="Token invalide")

    # Check if token has been revoked (blacklisted)
    jti = payload.get("jti")
    if jti:
        blacklisted = db.execute(
            select(TokenBlacklist).where(TokenBlacklist.jti == jti)
        ).scalar_one_or_none()
        if blacklisted:
            raise HTTPException(status_code=401, detail="Token has been revoked")

    # Reject refresh tokens and reset tokens used as access tokens
    if payload.get("token_type") == "refresh":
        raise HTTPException(status_code=401, detail="Token invalide. Utilisez un access token.")
    if payload.get("type") == "reset":
        raise HTTPException(status_code=401, detail="Token invalide. Utilisez un access token.")

    user = db.execute(
        select(User).where(User.email == payload.get("sub"))
    ).scalar_one_or_none()

    if not user:
        raise HTTPException(status_code=401, detail="Utilisateur non trouvé")

    if not user.is_active:
        raise HTTPException(status_code=403, detail="Compte désactivé")

    return user
