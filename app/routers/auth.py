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
"""
import html
import secrets
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from database import get_db
from models import User, Subscription, VerificationCode
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
from app.rate_limit import limiter

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
    existing_user = db.query(User).filter(User.email == data.email).first()
    if existing_user:
        raise HTTPException(status_code=400, detail="Cet email est déjà utilisé")

    # Valider le mot de passe
    if len(data.password) < 8:
        raise HTTPException(
            status_code=400,
            detail="Le mot de passe doit contenir au moins 8 caractères"
        )

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
    expires_at = (datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)).isoformat()

    # Envoyer email de bienvenue
    send_email(
        to=new_user.email,
        subject="Bienvenue sur Afrikalytics AI !",
        html=f"""
            <h2>Bienvenue {html.escape(new_user.full_name)} !</h2>
            <p>Votre compte Afrikalytics a été créé avec succès.</p>
            <p><strong>Plan :</strong> Basic (Gratuit)</p>
            <hr>
            <p>Avec votre compte Basic, vous pouvez :</p>
            <ul>
                <li>✅ Participer à toutes nos études</li>
                <li>✅ Voir un aperçu des insights</li>
                <li>✅ Accéder au dashboard basic</li>
            </ul>
            <p>Pour accéder aux résultats complets, insights détaillés et rapports PDF, passez à <strong>Premium</strong> !</p>
            <hr>
            <p><a href="https://dashboard.afrikalytics.com">Accéder à mon dashboard →</a></p>
            <p><a href="https://afrikalytics.com/premium">Découvrir les offres Premium →</a></p>
            <hr>
            <p><em>L'équipe Afrikalytics AI by Marketym</em></p>
        """
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
    user = db.query(User).filter(User.email == data.email).first()

    if not user or not verify_password(data.password, user.hashed_password):
        raise HTTPException(status_code=401, detail="Email ou mot de passe incorrect")

    if not user.is_active:
        raise HTTPException(status_code=403, detail="Compte désactivé")

    # Verifier si l'abonnement est expire (backup du cron job)
    if user.plan in ["professionnel", "entreprise"]:
        active_subscription = db.query(Subscription).filter(
            Subscription.user_id == user.id,
            Subscription.status == "active"
        ).first()

        if active_subscription and active_subscription.end_date:
            end_date = (
                active_subscription.end_date.date()
                if hasattr(active_subscription.end_date, 'date')
                else active_subscription.end_date
            )
            if end_date < datetime.utcnow().date():
                # Abonnement expire — retrograder
                active_subscription.status = "expired"
                user.plan = "basic"
                db.commit()

    # Generer un code a 6 chiffres
    code = str(secrets.randbelow(900000) + 100000)

    # Supprimer les anciens codes non utilises de cet utilisateur
    db.query(VerificationCode).filter(
        VerificationCode.user_id == user.id,
        VerificationCode.is_used == False
    ).delete()

    # Creer le nouveau code (expire dans 10 minutes)
    verification = VerificationCode(
        user_id=user.id,
        code=code,
        expires_at=datetime.utcnow() + timedelta(minutes=10)
    )
    db.add(verification)
    db.commit()

    # Envoyer le code par email
    send_email(
        to=user.email,
        subject="🔐 Votre code de connexion Afrikalytics",
        html=f"""
            <h2>Code de vérification</h2>
            <p>Bonjour {html.escape(user.full_name)},</p>
            <p>Voici votre code de connexion :</p>
            <div style="background-color: #f3f4f6; padding: 20px; text-align: center; margin: 20px 0; border-radius: 8px;">
                <span style="font-size: 32px; font-weight: bold; letter-spacing: 8px; color: #1f2937;">{code}</span>
            </div>
            <p style="color: #666; font-size: 14px;">Ce code expire dans <strong>10 minutes</strong>.</p>
            <p style="color: #e74c3c; font-size: 14px;">Si vous n'avez pas demandé ce code, ignorez cet email.</p>
            <hr>
            <p><em>L'équipe Afrikalytics AI by Marketym</em></p>
        """
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
    user = db.query(User).filter(User.email == data.email).first()

    if not user:
        raise HTTPException(status_code=401, detail="Code invalide")

    # Chercher le code valide
    verification = db.query(VerificationCode).filter(
        VerificationCode.user_id == user.id,
        VerificationCode.code == data.code,
        VerificationCode.is_used == False,
        VerificationCode.expires_at > datetime.utcnow()
    ).first()

    if not verification:
        raise HTTPException(status_code=401, detail="Code invalide ou expiré")

    # Marquer le code comme utilise
    verification.is_used = True
    db.commit()

    # Creer les tokens JWT
    token_data = {"sub": user.email, "user_id": user.id}
    access_token = create_access_token(data=token_data)
    refresh_token = create_refresh_token(data=token_data)
    expires_at = (datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)).isoformat()

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
    user = db.query(User).filter(User.email == data.email).first()

    if not user:
        # Ne pas reveler si l'email existe
        return {"message": "Si un compte existe, un nouveau code a été envoyé"}

    # Generer un nouveau code
    code = str(secrets.randbelow(900000) + 100000)

    # Supprimer les anciens codes
    db.query(VerificationCode).filter(
        VerificationCode.user_id == user.id,
        VerificationCode.is_used == False
    ).delete()

    # Creer le nouveau code
    verification = VerificationCode(
        user_id=user.id,
        code=code,
        expires_at=datetime.utcnow() + timedelta(minutes=10)
    )
    db.add(verification)
    db.commit()

    # Envoyer le code
    send_email(
        to=user.email,
        subject="🔐 Nouveau code de connexion Afrikalytics",
        html=f"""
            <h2>Nouveau code de vérification</h2>
            <p>Bonjour {html.escape(user.full_name)},</p>
            <p>Voici votre nouveau code de connexion :</p>
            <div style="background-color: #f3f4f6; padding: 20px; text-align: center; margin: 20px 0; border-radius: 8px;">
                <span style="font-size: 32px; font-weight: bold; letter-spacing: 8px; color: #1f2937;">{code}</span>
            </div>
            <p style="color: #666; font-size: 14px;">Ce code expire dans <strong>10 minutes</strong>.</p>
            <hr>
            <p><em>L'équipe Afrikalytics AI by Marketym</em></p>
        """
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
    user = db.query(User).filter(User.email == data.email).first()

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
        html=f"""
            <h2>Réinitialisation de mot de passe</h2>
            <p>Bonjour {html.escape(user.full_name)},</p>
            <p>Vous avez demandé à réinitialiser votre mot de passe Afrikalytics.</p>
            <p>Cliquez sur le bouton ci-dessous pour définir un nouveau mot de passe :</p>
            <p style="margin: 30px 0;">
                <a href="{reset_url}"
                   style="background-color: #2563eb; color: white; padding: 12px 24px; text-decoration: none; border-radius: 8px; font-weight: bold;">
                    Réinitialiser mon mot de passe
                </a>
            </p>
            <p style="color: #666; font-size: 14px;">Ce lien expire dans <strong>1 heure</strong>.</p>
            <p style="color: #666; font-size: 14px;">Si vous n'avez pas demandé cette réinitialisation, ignorez cet email.</p>
            <hr>
            <p><em>L'équipe Afrikalytics AI by Marketym</em></p>
        """
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
        raise HTTPException(status_code=400, detail="Lien expir\u00e9. Veuillez refaire la demande.")

    if not payload:
        raise HTTPException(status_code=400, detail="Lien invalide ou expir\u00e9")

    # Verifier que c'est bien un token de reset
    if payload.get("type") != "reset":
        raise HTTPException(status_code=400, detail="Lien invalide")

    email = payload.get("sub")
    if not email:
        raise HTTPException(status_code=400, detail="Lien invalide")

    # Trouver l'utilisateur
    user = db.query(User).filter(User.email == email).first()
    if not user:
        raise HTTPException(status_code=400, detail="Utilisateur non trouvé")

    # Valider le nouveau mot de passe
    if len(data.new_password) < 8:
        raise HTTPException(
            status_code=400,
            detail="Le mot de passe doit contenir au moins 8 caractères"
        )

    # Mettre a jour le mot de passe
    user.hashed_password = hash_password(data.new_password)
    db.commit()

    # Envoyer email de confirmation
    send_email(
        to=user.email,
        subject="Mot de passe modifié - Afrikalytics",
        html=f"""
            <h2>Mot de passe modifié</h2>
            <p>Bonjour {html.escape(user.full_name)},</p>
            <p>Votre mot de passe Afrikalytics a été réinitialisé avec succès.</p>
            <p>Vous pouvez maintenant vous connecter avec votre nouveau mot de passe.</p>
            <p style="margin: 30px 0;">
                <a href="https://dashboard.afrikalytics.com/login"
                   style="background-color: #2563eb; color: white; padding: 12px 24px; text-decoration: none; border-radius: 8px; font-weight: bold;">
                    Se connecter
                </a>
            </p>
            <p style="color: #e74c3c; font-size: 14px;">Si vous n'êtes pas à l'origine de cette modification, contactez-nous immédiatement.</p>
            <hr>
            <p><em>L'équipe Afrikalytics AI by Marketym</em></p>
        """
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
        raise HTTPException(status_code=401, detail="Refresh token expir\u00e9. Veuillez vous reconnecter.")

    if not payload:
        raise HTTPException(status_code=401, detail="Refresh token invalide")

    # Verify this is actually a refresh token
    if payload.get("token_type") != "refresh":
        raise HTTPException(status_code=401, detail="Token invalide. Un refresh token est requis.")

    email = payload.get("sub")
    if not email:
        raise HTTPException(status_code=401, detail="Refresh token invalide")

    # Verify user still exists and is active
    user = db.query(User).filter(User.email == email).first()
    if not user:
        raise HTTPException(status_code=401, detail="Utilisateur non trouv\u00e9")
    if not user.is_active:
        raise HTTPException(status_code=403, detail="Compte d\u00e9sactiv\u00e9")

    # Issue new access token
    new_access_token = create_access_token(
        data={"sub": user.email, "user_id": user.id}
    )
    expires_at = (datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)).isoformat()

    return {
        "access_token": new_access_token,
        "token_type": "bearer",
        "expires_at": expires_at,
    }
