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
"""
import secrets
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from sqlalchemy import select, delete, update
from sqlalchemy.orm import Session

from database import get_db
from models import User, Subscription, VerificationCode, TokenBlacklist
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
)
from app.services.email import send_email
from app.services.email_templates import (
    welcome_email,
    verification_code_email,
    resend_verification_code_email,
    forgot_password_email,
    password_reset_confirmation_email,
)
from app.rate_limit import limiter
from app.utils import validate_password

router = APIRouter(prefix="/api/auth", tags=["Authentication"])


# ==================== REGISTER ====================

@router.post("/register", response_model=TokenResponse, status_code=201)
@limiter.limit("3/minute")
async def register(request: Request, data: UserRegister, db: Session = Depends(get_db)):
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
async def login(request: Request, data: UserLogin, db: Session = Depends(get_db)):
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
async def verify_code(request: Request, data: VerifyCodeRequest, db: Session = Depends(get_db)):
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
async def resend_code(request: Request, data: ForgotPassword, db: Session = Depends(get_db)):
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
async def forgot_password(request: Request, data: ForgotPassword, db: Session = Depends(get_db)):
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
async def reset_password(request: Request, data: ResetPassword, db: Session = Depends(get_db)):
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
async def refresh_access_token(
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
async def logout(
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
