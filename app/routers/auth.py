"""
Router d'authentification — /api/auth/*
Extrait de main.py (lignes 1124-1455).

Endpoints:
    POST /api/auth/register       — Inscription (plan Basic gratuit)
    POST /api/auth/login          — Connexion step 1 (envoie code 2FA)
    POST /api/auth/verify-code    — Connexion step 2 (verifie code, retourne JWT)
    POST /api/auth/resend-code    — Renvoyer le code 2FA
    POST /api/auth/forgot-password — Demande de reset password
    POST /api/auth/reset-password  — Reset password avec token
    POST /api/auth/logout         — Deconnexion (blacklist le token)
    GET  /api/auth/sso/google     — URL d'autorisation Google
    GET  /api/auth/sso/google/callback   — Callback Google OAuth2
    GET  /api/auth/sso/microsoft  — URL d'autorisation Microsoft
    GET  /api/auth/sso/microsoft/callback — Callback Microsoft OAuth2
    POST /api/auth/sso/exchange   — Echange code SSO contre JWT (SEC-01 fix)
"""
import logging
import secrets
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from fastapi.responses import RedirectResponse
from sqlalchemy import select, delete, update
from sqlalchemy.orm import Session

from database import get_db
from models import User, Subscription, VerificationCode, TokenBlacklist, SSOExchangeCode
from app.dependencies import get_current_user
from auth import (
    hash_password,
    verify_password,
    create_access_token,
    create_refresh_token,
    decode_access_token,
    ACCESS_TOKEN_EXPIRE_MINUTES,
)
from app.schemas.auth import (
    UserRegister,
    UserLogin,
    TokenResponse,
    RefreshTokenRequest,
    RefreshTokenResponse,
    ForgotPassword,
    ResetPassword,
    VerifyCodeRequest,
    SSOExchangeRequest,
    SSOExchangeResponse,
)
from app.config import get_settings
from app.services.email import send_email
from app.services.email_templates import (
    welcome_email,
    verification_code_email,
    resend_verification_code_email,
    forgot_password_email,
    password_reset_confirmation_email,
)
from app.services.sso_service import (
    get_google_auth_url,
    exchange_google_code,
    get_google_user_info,
    get_microsoft_auth_url,
    exchange_microsoft_code,
    get_microsoft_user_info,
)
from app.rate_limit import limiter
from app.utils import validate_password

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/auth", tags=["Authentication"])


# ==================== REGISTER ====================

@router.post("/register", response_model=TokenResponse, status_code=201)
@limiter.limit("3/minute")
def register(request: Request, data: UserRegister, db: Session = Depends(get_db)):
    """
    Inscription d'un nouvel utilisateur (plan Basic gratuit).
    Limite a 3 tentatives par minute.
    """
    # Verifier si l'email existe deja
    existing_user = db.execute(
        select(User).where(User.email == data.email)
    ).scalar_one_or_none()
    if existing_user:
        raise HTTPException(status_code=400, detail="Cet email est déjà utilisé")

    # Valider le mot de passe
    is_valid, error_message = validate_password(data.password)
    if not is_valid:
        raise HTTPException(status_code=400, detail=error_message)

    # Creer l'utilisateur
    hashed_password = hash_password(data.password)

    new_user = User(
        email=data.email,
        full_name=data.name,
        hashed_password=hashed_password,
        plan="basic",
        is_active=True
    )

    db.add(new_user)
    db.commit()
    db.refresh(new_user)

    # Creer les tokens
    token_data = {"sub": new_user.email, "user_id": new_user.id}
    access_token = create_access_token(data=token_data)
    refresh_token = create_refresh_token(data=token_data)
    expires_at = (datetime.now(timezone.utc) + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)).isoformat()

    # Envoyer email de bienvenue
    send_email(
        to=new_user.email,
        subject="Bienvenue sur Afrikalytics AI !",
        html=welcome_email(new_user.full_name),
    )

    return {
        "access_token": access_token,
        "refresh_token": refresh_token,
        "token_type": "bearer",
        "expires_at": expires_at,
        "user": new_user
    }


# ==================== LOGIN (Step 1 — send 2FA code) ====================

@router.post("/login")
@limiter.limit("5/minute")
def login(request: Request, data: UserLogin, db: Session = Depends(get_db)):
    """
    Connexion utilisateur — Etape 1 : Verification email/mot de passe.
    Envoie un code de verification par email.
    Limite a 5 tentatives par minute.
    """
    user = db.execute(
        select(User).where(User.email == data.email)
    ).scalar_one_or_none()

    if not user or not verify_password(data.password, user.hashed_password):
        raise HTTPException(status_code=401, detail="Email ou mot de passe incorrect")

    if not user.is_active:
        raise HTTPException(status_code=403, detail="Compte désactivé")

    # Verifier si l'abonnement est expire (backup du cron job)
    if user.plan in ["professionnel", "entreprise"]:
        active_subscription = db.execute(
            select(Subscription).where(
                Subscription.user_id == user.id,
                Subscription.status == "active"
            )
        ).scalar_one_or_none()

        if active_subscription and active_subscription.end_date:
            end_date = (
                active_subscription.end_date.date()
                if hasattr(active_subscription.end_date, 'date')
                else active_subscription.end_date
            )
            if end_date < datetime.now(timezone.utc).date():
                # Abonnement expire — retrograder
                active_subscription.status = "expired"
                user.plan = "basic"
                db.commit()

    # Generer un code a 6 chiffres
    code = str(secrets.randbelow(900000) + 100000)

    # Supprimer les anciens codes non utilises de cet utilisateur
    db.execute(
        delete(VerificationCode).where(
            VerificationCode.user_id == user.id,
            VerificationCode.is_used.is_(False)
        )
    )

    # Creer le nouveau code (expire dans 10 minutes)
    verification = VerificationCode(
        user_id=user.id,
        code=code,
        expires_at=datetime.now(timezone.utc) + timedelta(minutes=10)
    )
    db.add(verification)
    db.commit()

    # Envoyer le code par email
    send_email(
        to=user.email,
        subject="🔐 Votre code de connexion Afrikalytics",
        html=verification_code_email(user.full_name, code),
    )

    return {
        "status": "pending_verification",
        "message": "Un code de vérification a été envoyé à votre email",
        "email": user.email,
        "requires_verification": True
    }


# ==================== VERIFY CODE (Step 2 — validate 2FA, return JWT) ====================

@router.post("/verify-code", response_model=TokenResponse)
@limiter.limit("5/minute")
def verify_code(request: Request, data: VerifyCodeRequest, db: Session = Depends(get_db)):
    """
    Connexion utilisateur — Etape 2 : Verification du code 2FA.
    Retourne le token JWT si le code est correct.
    """
    user = db.execute(
        select(User).where(User.email == data.email)
    ).scalar_one_or_none()

    if not user:
        raise HTTPException(status_code=401, detail="Code invalide")

    # Brute-force protection: count recently used (failed) codes for this user
    from sqlalchemy import func
    recent_failed = db.execute(
        select(func.count()).select_from(VerificationCode).where(
            VerificationCode.user_id == user.id,
            VerificationCode.is_used.is_(True),
            VerificationCode.created_at > datetime.now(timezone.utc) - timedelta(minutes=10)
        )
    ).scalar()

    if recent_failed >= 5:
        # Invalidate all remaining active codes
        db.execute(
            update(VerificationCode)
            .where(
                VerificationCode.user_id == user.id,
                VerificationCode.is_used.is_(False),
            )
            .values(is_used=True)
        )
        db.commit()
        raise HTTPException(
            status_code=429,
            detail="Trop de tentatives. Veuillez vous reconnecter pour recevoir un nouveau code."
        )

    # Chercher le code valide
    verification = db.execute(
        select(VerificationCode).where(
            VerificationCode.user_id == user.id,
            VerificationCode.code == data.code,
            VerificationCode.is_used.is_(False),
            VerificationCode.expires_at > datetime.now(timezone.utc)
        )
    ).scalar_one_or_none()

    if not verification:
        # Mark a failed attempt by creating a used verification code entry
        failed_entry = VerificationCode(
            user_id=user.id,
            code="000000",
            expires_at=datetime.now(timezone.utc),
            is_used=True,
        )
        db.add(failed_entry)
        db.commit()
        raise HTTPException(status_code=401, detail="Code invalide ou expiré")

    # Marquer le code comme utilise
    verification.is_used = True
    db.commit()

    # Creer les tokens JWT
    token_data = {"sub": user.email, "user_id": user.id}
    access_token = create_access_token(data=token_data)
    refresh_token = create_refresh_token(data=token_data)
    expires_at = (datetime.now(timezone.utc) + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)).isoformat()

    return {
        "access_token": access_token,
        "refresh_token": refresh_token,
        "token_type": "bearer",
        "expires_at": expires_at,
        "user": user
    }


# ==================== RESEND CODE ====================

@router.post("/resend-code")
@limiter.limit("3/minute")
def resend_code(request: Request, data: ForgotPassword, db: Session = Depends(get_db)):
    """
    Renvoyer un nouveau code de verification 2FA.
    """
    user = db.execute(
        select(User).where(User.email == data.email)
    ).scalar_one_or_none()

    if not user:
        # Ne pas reveler si l'email existe
        return {"message": "Si un compte existe, un nouveau code a été envoyé"}

    # Generer un nouveau code
    code = str(secrets.randbelow(900000) + 100000)

    # Supprimer les anciens codes
    db.execute(
        delete(VerificationCode).where(
            VerificationCode.user_id == user.id,
            VerificationCode.is_used.is_(False)
        )
    )

    # Creer le nouveau code
    verification = VerificationCode(
        user_id=user.id,
        code=code,
        expires_at=datetime.now(timezone.utc) + timedelta(minutes=10)
    )
    db.add(verification)
    db.commit()

    # Envoyer le code
    send_email(
        to=user.email,
        subject="🔐 Nouveau code de connexion Afrikalytics",
        html=resend_verification_code_email(user.full_name, code),
    )

    return {"message": "Un nouveau code a été envoyé"}


# ==================== FORGOT PASSWORD ====================

@router.post("/forgot-password")
@limiter.limit("3/minute")
def forgot_password(request: Request, data: ForgotPassword, db: Session = Depends(get_db)):
    """
    Envoyer un email de reinitialisation de mot de passe.
    Limite a 3 tentatives par minute.
    """
    user = db.execute(
        select(User).where(User.email == data.email)
    ).scalar_one_or_none()

    # Ne pas reveler si l'email existe ou non (securite)
    if not user:
        return {"message": "Si cet email existe, un lien de réinitialisation a été envoyé"}

    # Creer un token de reset (expire dans 1h)
    reset_token = create_access_token(
        data={"sub": user.email, "type": "reset"},
        expires_delta=timedelta(hours=1)
    )

    # URL de reset
    reset_url = f"https://dashboard.afrikalytics.com/reset-password?token={reset_token}"

    # Envoyer l'email
    send_email(
        to=user.email,
        subject="Réinitialisation de votre mot de passe - Afrikalytics",
        html=forgot_password_email(user.full_name, reset_url),
    )

    return {"message": "Si cet email existe, un lien de réinitialisation a été envoyé"}


# ==================== RESET PASSWORD ====================

@router.post("/reset-password")
@limiter.limit("5/minute")
def reset_password(request: Request, data: ResetPassword, db: Session = Depends(get_db)):
    """
    Reinitialiser le mot de passe avec le token.
    Limite a 5 tentatives par minute.
    """
    # Verifier le token
    try:
        payload = decode_access_token(data.token)
    except ValueError:
        raise HTTPException(status_code=400, detail="Lien expiré. Veuillez refaire la demande.")

    if not payload:
        raise HTTPException(status_code=400, detail="Lien invalide ou expiré")

    # Verifier que c'est bien un token de reset
    if payload.get("type") != "reset":
        raise HTTPException(status_code=400, detail="Lien invalide")

    # Verifier que le token n'a pas deja ete utilise
    reset_jti = payload.get("jti")
    if reset_jti:
        already_used = db.execute(
            select(TokenBlacklist).where(TokenBlacklist.jti == reset_jti)
        ).scalar_one_or_none()
        if already_used:
            raise HTTPException(status_code=400, detail="Ce lien a déjà été utilisé")

    email = payload.get("sub")
    if not email:
        raise HTTPException(status_code=400, detail="Lien invalide")

    # Trouver l'utilisateur
    user = db.execute(
        select(User).where(User.email == email)
    ).scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=400, detail="Utilisateur non trouvé")

    # Valider le nouveau mot de passe
    is_valid, error_message = validate_password(data.new_password)
    if not is_valid:
        raise HTTPException(status_code=400, detail=error_message)

    # Mettre a jour le mot de passe
    user.hashed_password = hash_password(data.new_password)

    # Blacklist the reset token to prevent reuse
    jti = payload.get("jti")
    if jti:
        blacklisted = TokenBlacklist(
            jti=jti,
            user_id=user.id,
            expires_at=datetime.fromtimestamp(payload.get("exp")),
        )
        db.add(blacklisted)

    db.commit()

    # Envoyer email de confirmation
    send_email(
        to=user.email,
        subject="Mot de passe modifié - Afrikalytics",
        html=password_reset_confirmation_email(user.full_name),
    )

    return {"message": "Mot de passe réinitialisé avec succès"}


# ==================== REFRESH TOKEN ====================

@router.post("/refresh", response_model=RefreshTokenResponse)
@limiter.limit("10/minute")
def refresh_access_token(
    request: Request,
    data: RefreshTokenRequest,
    db: Session = Depends(get_db),
):
    """
    Rafraichir le token d'acces a partir d'un refresh token valide.
    Retourne un nouveau access token.
    """
    try:
        payload = decode_access_token(data.refresh_token)
    except ValueError:
        raise HTTPException(status_code=401, detail="Refresh token expiré. Veuillez vous reconnecter.")

    if not payload:
        raise HTTPException(status_code=401, detail="Refresh token invalide")

    # Verify this is actually a refresh token
    if payload.get("token_type") != "refresh":
        raise HTTPException(status_code=401, detail="Token invalide. Un refresh token est requis.")

    email = payload.get("sub")
    if not email:
        raise HTTPException(status_code=401, detail="Refresh token invalide")

    # Verify user still exists and is active
    user = db.execute(
        select(User).where(User.email == email)
    ).scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=401, detail="Utilisateur non trouvé")
    if not user.is_active:
        raise HTTPException(status_code=403, detail="Compte désactivé")

    # Issue new access token
    new_access_token = create_access_token(
        data={"sub": user.email, "user_id": user.id}
    )
    expires_at = (datetime.now(timezone.utc) + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)).isoformat()

    return {
        "access_token": new_access_token,
        "token_type": "bearer",
        "expires_at": expires_at,
    }


# ==================== LOGOUT ====================

@router.post("/logout")
def logout(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    authorization: str = Header(None),
):
    """
    Deconnecter l'utilisateur en blacklistant son token JWT.
    Les anciens tokens sans jti restent compatibles (rien a blacklister).
    """
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Token manquant")

    token = authorization.replace("Bearer ", "")
    payload = decode_access_token(token)

    if not payload:
        raise HTTPException(status_code=401, detail="Token invalide")

    jti = payload.get("jti")
    if jti:
        # Verify token is not already blacklisted
        existing = db.execute(
            select(TokenBlacklist).where(TokenBlacklist.jti == jti)
        ).scalar_one_or_none()
        if not existing:
            blacklisted = TokenBlacklist(
                jti=jti,
                user_id=current_user.id,
                expires_at=datetime.fromtimestamp(payload.get("exp")),
            )
            db.add(blacklisted)
            db.commit()

    return {"message": "Déconnexion réussie"}


# ==================== SSO — GOOGLE ====================

@router.get("/sso/google")
async def sso_google_login(request: Request):
    """
    Retourne l'URL d'autorisation Google OAuth2.
    Le frontend redirige l'utilisateur vers cette URL.
    """
    settings = get_settings()
    if not settings.google_client_id or not settings.google_client_secret:
        raise HTTPException(status_code=501, detail="L'authentification Google n'est pas configurée")

    redirect_uri = f"{settings.api_url}/api/auth/sso/google/callback"
    state = secrets.token_urlsafe(32)

    auth_url = await get_google_auth_url(
        client_id=settings.google_client_id,
        redirect_uri=redirect_uri,
        state=state,
    )

    return {"auth_url": auth_url, "provider": "google"}


@router.get("/sso/google/callback")
async def sso_google_callback(
    request: Request,
    code: str,
    state: str | None = None,
    db: Session = Depends(get_db),
):
    """
    Callback Google OAuth2.
    Echange le code, cree ou lie l'utilisateur, redirige avec JWT.
    """
    settings = get_settings()
    redirect_uri = f"{settings.api_url}/api/auth/sso/google/callback"

    try:
        # 1. Exchange code for tokens
        token_data = await exchange_google_code(
            code=code,
            client_id=settings.google_client_id,
            client_secret=settings.google_client_secret,
            redirect_uri=redirect_uri,
        )

        # 2. Get user info from Google
        google_user = await get_google_user_info(token_data["access_token"])
        email = google_user.get("email")
        name = google_user.get("name", "")
        google_id = google_user.get("sub")  # Google unique user ID

        if not email:
            raise HTTPException(status_code=400, detail="Impossible de récupérer l'email depuis Google")

        # 3. Find or create user
        user = db.execute(
            select(User).where(User.email == email)
        ).scalar_one_or_none()

        if user:
            # Update SSO fields if not already linked
            if not user.sso_provider:
                user.sso_provider = "google"
                user.sso_id = google_id
                db.commit()
        else:
            # Create new user (no password needed for SSO)
            user = User(
                email=email,
                full_name=name or email.split("@")[0],
                hashed_password="",  # No password for SSO users
                plan="basic",
                is_active=True,
                sso_provider="google",
                sso_id=google_id,
            )
            db.add(user)
            db.commit()
            db.refresh(user)

            # Send welcome email
            try:
                send_email(
                    to=user.email,
                    subject="Bienvenue sur Afrikalytics AI !",
                    html=welcome_email(user.full_name),
                )
            except Exception:
                logger.warning("Failed to send welcome email to %s", user.email)

        # 4. Generate JWT
        token_payload = {"sub": user.email, "user_id": user.id}
        access_token = create_access_token(data=token_payload)

        # 5. Generate a short-lived exchange code so the JWT is never placed in a URL.
        #    The frontend will POST this code to POST /api/auth/sso/exchange to get the JWT.
        #    OWASP A02:2021 — prevents JWT exposure in server logs, browser history,
        #    and Referer headers.
        sso_code = secrets.token_urlsafe(32)
        exchange = SSOExchangeCode(
            code=sso_code,
            user_id=user.id,
            access_token=access_token,
            expires_at=datetime.now(timezone.utc) + timedelta(seconds=60),
        )
        db.add(exchange)
        db.commit()

        # 6. Redirect with only the opaque code — no JWT in the URL.
        frontend_url = settings.frontend_url or "http://localhost:3000"
        return RedirectResponse(
            url=f"{frontend_url}/login?sso_code={sso_code}&sso=true"
        )

    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("Google SSO callback error")
        frontend_url = settings.frontend_url or "http://localhost:3000"
        return RedirectResponse(
            url=f"{frontend_url}/login?sso_error=google"
        )


# ==================== SSO — MICROSOFT ====================

@router.get("/sso/microsoft")
async def sso_microsoft_login(request: Request):
    """
    Retourne l'URL d'autorisation Microsoft OAuth2.
    Le frontend redirige l'utilisateur vers cette URL.
    """
    settings = get_settings()
    if not settings.microsoft_client_id or not settings.microsoft_client_secret:
        raise HTTPException(status_code=501, detail="L'authentification Microsoft n'est pas configurée")

    redirect_uri = f"{settings.api_url}/api/auth/sso/microsoft/callback"
    state = secrets.token_urlsafe(32)

    auth_url = await get_microsoft_auth_url(
        client_id=settings.microsoft_client_id,
        tenant_id=settings.microsoft_tenant_id,
        redirect_uri=redirect_uri,
        state=state,
    )

    return {"auth_url": auth_url, "provider": "microsoft"}


@router.get("/sso/microsoft/callback")
async def sso_microsoft_callback(
    request: Request,
    code: str,
    state: str | None = None,
    db: Session = Depends(get_db),
):
    """
    Callback Microsoft OAuth2.
    Echange le code, cree ou lie l'utilisateur, redirige avec JWT.
    """
    settings = get_settings()
    redirect_uri = f"{settings.api_url}/api/auth/sso/microsoft/callback"

    try:
        # 1. Exchange code for tokens
        token_data = await exchange_microsoft_code(
            code=code,
            client_id=settings.microsoft_client_id,
            client_secret=settings.microsoft_client_secret,
            tenant_id=settings.microsoft_tenant_id,
            redirect_uri=redirect_uri,
        )

        # 2. Get user info from Microsoft Graph
        ms_user = await get_microsoft_user_info(token_data["access_token"])
        email = ms_user.get("mail") or ms_user.get("userPrincipalName")
        name = ms_user.get("displayName", "")
        microsoft_id = ms_user.get("id")  # Microsoft unique user ID

        if not email:
            raise HTTPException(status_code=400, detail="Impossible de récupérer l'email depuis Microsoft")

        # 3. Find or create user
        user = db.execute(
            select(User).where(User.email == email)
        ).scalar_one_or_none()

        if user:
            # Update SSO fields if not already linked
            if not user.sso_provider:
                user.sso_provider = "microsoft"
                user.sso_id = microsoft_id
                db.commit()
        else:
            # Create new user (no password needed for SSO)
            user = User(
                email=email,
                full_name=name or email.split("@")[0],
                hashed_password="",  # No password for SSO users
                plan="basic",
                is_active=True,
                sso_provider="microsoft",
                sso_id=microsoft_id,
            )
            db.add(user)
            db.commit()
            db.refresh(user)

            # Send welcome email
            try:
                send_email(
                    to=user.email,
                    subject="Bienvenue sur Afrikalytics AI !",
                    html=welcome_email(user.full_name),
                )
            except Exception:
                logger.warning("Failed to send welcome email to %s", user.email)

        # 4. Generate JWT
        token_payload = {"sub": user.email, "user_id": user.id}
        access_token = create_access_token(data=token_payload)

        # 5. Generate a short-lived exchange code so the JWT is never placed in a URL.
        #    The frontend will POST this code to POST /api/auth/sso/exchange to get the JWT.
        #    OWASP A02:2021 — prevents JWT exposure in server logs, browser history,
        #    and Referer headers.
        sso_code = secrets.token_urlsafe(32)
        exchange = SSOExchangeCode(
            code=sso_code,
            user_id=user.id,
            access_token=access_token,
            expires_at=datetime.now(timezone.utc) + timedelta(seconds=60),
        )
        db.add(exchange)
        db.commit()

        # 6. Redirect with only the opaque code — no JWT in the URL.
        frontend_url = settings.frontend_url or "http://localhost:3000"
        return RedirectResponse(
            url=f"{frontend_url}/login?sso_code={sso_code}&sso=true"
        )

    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("Microsoft SSO callback error")
        frontend_url = settings.frontend_url or "http://localhost:3000"
        return RedirectResponse(
            url=f"{frontend_url}/login?sso_error=microsoft"
        )


# ==================== SSO — EXCHANGE CODE ====================

@router.post("/sso/exchange", response_model=SSOExchangeResponse)
@limiter.limit("10/minute")
def sso_exchange(
    request: Request,
    data: SSOExchangeRequest,
    db: Session = Depends(get_db),
):
    """
    Exchange a short-lived SSO code for a JWT access token.

    The code is obtained from the ?sso_code= query parameter of the SSO redirect URL.
    It is valid for 60 seconds and can only be used once.

    Security guarantees:
    - The JWT is returned in the JSON response body, never in a URL.
    - The code is invalidated immediately after use (is_used=True).
    - Expired or already-used codes are rejected with HTTP 400.
    - The endpoint returns the same generic error message for all failure modes
      to prevent oracle attacks.
    """
    now = datetime.now(timezone.utc)

    # Look up the exchange record — reject if not found, expired, or already used.
    exchange = db.execute(
        select(SSOExchangeCode).where(
            SSOExchangeCode.code == data.sso_code,
            SSOExchangeCode.is_used.is_(False),
            SSOExchangeCode.expires_at > now,
        )
    ).scalar_one_or_none()

    if not exchange:
        # Do not distinguish between "not found", "expired", and "already used"
        # to prevent timing/oracle attacks.
        raise HTTPException(
            status_code=400,
            detail="Code SSO invalide ou expiré. Veuillez vous reconnecter.",
        )

    # Mark the code as consumed atomically before returning the token.
    exchange.is_used = True
    db.commit()

    # Retrieve the associated user to build the full response.
    user = db.execute(
        select(User).where(User.id == exchange.user_id)
    ).scalar_one_or_none()

    if not user or not user.is_active:
        raise HTTPException(
            status_code=403,
            detail="Compte introuvable ou désactivé.",
        )

    expires_at = (
        datetime.now(timezone.utc) + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    ).isoformat()

    return {
        "access_token": exchange.access_token,
        "token_type": "bearer",
        "expires_at": expires_at,
        "user": user,
    }
