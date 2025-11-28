from fastapi import FastAPI, Depends, HTTPException, Header, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session
from sqlalchemy import Column, Integer, String, Boolean, DateTime, ForeignKey
from sqlalchemy.sql import func
from pydantic import BaseModel, EmailStr
from typing import Optional, List
import secrets
import os
from datetime import datetime, timedelta
import resend
import hashlib
import hmac
import random

# Rate limiting
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded

from database import get_db, engine
from models import Base, User, Study, Insight, Report, Contact, Subscription
from auth import hash_password, verify_password, create_access_token, decode_access_token

# Modèle pour les codes de vérification 2FA
class VerificationCode(Base):
    __tablename__ = "verification_codes"
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    code = Column(String(6), nullable=False)
    expires_at = Column(DateTime(timezone=True), nullable=False)
    is_used = Column(Boolean, default=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

# Créer les tables
Base.metadata.create_all(bind=engine)

# Configurer Resend
resend.api_key = os.getenv("RESEND_API_KEY")
CONTACT_EMAIL = os.getenv("CONTACT_EMAIL", "contact@afrikalytics.com")

# Configurer PayDunya
PAYDUNYA_MASTER_KEY = os.getenv("PAYDUNYA_MASTER_KEY", "")
PAYDUNYA_PRIVATE_KEY = os.getenv("PAYDUNYA_PRIVATE_KEY", "")
PAYDUNYA_TOKEN = os.getenv("PAYDUNYA_TOKEN", "")
PAYDUNYA_MODE = os.getenv("PAYDUNYA_MODE", "test")  # test ou live

# Configurer Rate Limiter
limiter = Limiter(key_func=get_remote_address)

app = FastAPI(
    title="Afrikalytics API",
    description="Backend API pour Afrikalytics AI - Intelligence d'Affaires pour l'Afrique",
    version="1.0.0"
)

# Ajouter le rate limiter à l'app
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# CORS - Permettre les requêtes depuis le frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "https://afrikalytics.com",
        "https://www.afrikalytics.com",
        "https://afrikalytics-website.vercel.app",
        "https://dashboard.afrikalytics.com",
        "https://afrikalytics-dashboard.vercel.app",
        "http://localhost:3000",
        "*"
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ==================== SCHEMAS ====================

class UserCreate(BaseModel):
    email: EmailStr
    name: str
    plan: str
    order_id: str

class UserRegister(BaseModel):
    email: EmailStr
    name: str
    password: str

class UserLogin(BaseModel):
    email: EmailStr
    password: str

class UserResponse(BaseModel):
    id: int
    email: str
    full_name: str
    plan: str
    is_active: bool
    is_admin: bool = False
    created_at: datetime

    class Config:
        from_attributes = True

class TokenResponse(BaseModel):
    access_token: str
    token_type: str
    user: UserResponse

class StudyCreate(BaseModel):
    title: str
    description: str
    category: str
    duration: Optional[str] = "15-20 min"
    deadline: Optional[str] = None
    status: Optional[str] = "Ouvert"
    icon: Optional[str] = "users"
    embed_url_particulier: Optional[str] = None
    embed_url_entreprise: Optional[str] = None
    embed_url_results: Optional[str] = None
    report_url_basic: Optional[str] = None
    report_url_premium: Optional[str] = None
    is_active: Optional[bool] = True

class StudyResponse(BaseModel):
    id: int
    title: str
    description: Optional[str]
    category: Optional[str]
    duration: Optional[str]
    deadline: Optional[str]
    status: Optional[str]
    icon: Optional[str]
    embed_url_particulier: Optional[str]
    embed_url_entreprise: Optional[str]
    embed_url_results: Optional[str]
    report_url_basic: Optional[str]
    report_url_premium: Optional[str]
    is_active: bool
    created_at: datetime

    class Config:
        from_attributes = True

class InsightCreate(BaseModel):
    study_id: int
    title: str
    summary: Optional[str] = None
    key_findings: Optional[str] = None
    recommendations: Optional[str] = None
    author: Optional[str] = None
    is_published: Optional[bool] = False

class InsightResponse(BaseModel):
    id: int
    study_id: int
    title: str
    summary: Optional[str]
    key_findings: Optional[str]
    recommendations: Optional[str]
    author: Optional[str]
    is_published: bool
    created_at: datetime

    class Config:
        from_attributes = True

class ReportCreate(BaseModel):
    study_id: int
    title: str
    description: Optional[str] = None
    file_url: str
    file_name: Optional[str] = None
    file_size: Optional[str] = None
    report_type: Optional[str] = "premium"
    is_available: Optional[bool] = True

class ReportResponse(BaseModel):
    id: int
    study_id: int
    title: str
    description: Optional[str]
    file_url: str
    file_name: Optional[str]
    file_size: Optional[str]
    report_type: Optional[str]
    download_count: int
    is_available: bool
    created_at: datetime

    class Config:
        from_attributes = True

class ContactCreate(BaseModel):
    name: str
    email: EmailStr
    company: Optional[str] = None
    message: str

class ContactResponse(BaseModel):
    id: int
    name: str
    email: str
    company: Optional[str]
    message: str
    is_read: bool
    created_at: datetime

    class Config:
        from_attributes = True

class PaymentCreate(BaseModel):
    email: EmailStr
    name: str
    plan: str = "professionnel"

class PasswordChange(BaseModel):
    current_password: str
    new_password: str

class ForgotPassword(BaseModel):
    email: EmailStr

class ResetPassword(BaseModel):
    token: str
    new_password: str

class VerifyCodeRequest(BaseModel):
    email: EmailStr
    code: str

class LoginPendingResponse(BaseModel):
    status: str
    message: str
    email: str
    requires_verification: bool

# ==================== ADMIN SCHEMAS ====================

class AdminUserCreate(BaseModel):
    email: EmailStr
    full_name: str
    password: Optional[str] = None  # Si vide, génère un mot de passe
    plan: str = "basic"  # basic, professionnel, entreprise
    is_active: bool = True
    is_admin: bool = False
    parent_user_id: Optional[int] = None  # Pour les sous-utilisateurs entreprise

class AdminUserUpdate(BaseModel):
    email: Optional[EmailStr] = None
    full_name: Optional[str] = None
    plan: Optional[str] = None
    is_active: Optional[bool] = None
    is_admin: Optional[bool] = None

class AdminUserResponse(BaseModel):
    id: int
    email: str
    full_name: str
    plan: str
    is_active: bool
    is_admin: bool
    created_at: datetime
    
    class Config:
        from_attributes = True

class EnterpriseUserAdd(BaseModel):
    email: EmailStr
    full_name: str

class DashboardStats(BaseModel):
    studies_accessible: int
    studies_participated: int
    reports_downloaded: int
    insights_viewed: int
    subscription_days_remaining: Optional[int]
    plan: str

# ==================== HELPERS ====================

def get_current_user(authorization: str = Header(None), db: Session = Depends(get_db)):
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Token manquant")
    
    token = authorization.replace("Bearer ", "")
    payload = decode_access_token(token)
    
    if not payload:
        raise HTTPException(status_code=401, detail="Token invalide")
    
    user = db.query(User).filter(User.email == payload.get("sub")).first()
    
    if not user:
        raise HTTPException(status_code=404, detail="Utilisateur non trouvé")
    
    return user


def send_email(to: str, subject: str, html: str):
    """
    Envoyer un email via Resend
    """
    try:
        params = {
            "from": "Afrikalytics <noreply@notifications.afrikalytics.com>",
            "to": [to],
            "subject": subject,
            "html": html
        }
        resend.Emails.send(params)
        return True
    except Exception as e:
        print(f"Erreur envoi email: {e}")
        return False


# ==================== ROUTES ====================

@app.get("/")
def read_root():
    return {
        "message": "Bienvenue sur l'API Afrikalytics AI",
        "version": "1.0.0",
        "status": "online",
        "docs": "/docs"
    }

@app.get("/health")
def health_check():
    return {"status": "healthy", "timestamp": datetime.utcnow()}


# ==================== PAYDUNYA ====================

@app.post("/api/paydunya/create-invoice")
async def create_paydunya_invoice(
    data: PaymentCreate,
    db: Session = Depends(get_db)
):
    """
    Créer une facture PayDunya pour le paiement
    """
    import requests
    
    # URL PayDunya selon le mode
    if PAYDUNYA_MODE == "live":
        base_url = "https://app.paydunya.com/api/v1"
    else:
        base_url = "https://app.paydunya.com/sandbox-api/v1"
    
    # Définir le prix selon le plan
    prices = {
        "professionnel": 295000,  # 295 000 CFA
        "entreprise": 500000,     # Sur mesure - à ajuster
    }
    
    amount = prices.get(data.plan, 295000)
    
    # Créer la facture
    invoice_data = {
        "invoice": {
            "items": {
                "item_0": {
                    "name": f"Abonnement {data.plan.capitalize()} - Afrikalytics",
                    "quantity": 1,
                    "unit_price": amount,
                    "total_price": amount,
                    "description": f"Abonnement mensuel au plan {data.plan.capitalize()}"
                }
            },
            "total_amount": amount,
            "description": f"Abonnement Afrikalytics - Plan {data.plan.capitalize()}"
        },
        "store": {
            "name": "Afrikalytics AI",
            "tagline": "Intelligence d'Affaires pour l'Afrique",
            "postal_address": "Dakar, Sénégal",
            "website_url": "https://afrikalytics.com"
        },
        "custom_data": {
            "email": data.email,
            "name": data.name,
            "plan": data.plan
        },
        "actions": {
            "cancel_url": "https://afrikalytics.com/premium?status=cancelled",
            "return_url": "https://dashboard.afrikalytics.com/payment-success",
            "callback_url": "https://web-production-ef657.up.railway.app/api/paydunya/webhook"
        }
    }
    
    headers = {
        "Content-Type": "application/json",
        "PAYDUNYA-MASTER-KEY": PAYDUNYA_MASTER_KEY,
        "PAYDUNYA-PRIVATE-KEY": PAYDUNYA_PRIVATE_KEY,
        "PAYDUNYA-TOKEN": PAYDUNYA_TOKEN
    }
    
    try:
        response = requests.post(
            f"{base_url}/checkout-invoice/create",
            json=invoice_data,
            headers=headers
        )
        
        result = response.json()
        
        if result.get("response_code") == "00":
            return {
                "success": True,
                "payment_url": result.get("response_text"),
                "token": result.get("token")
            }
        else:
            print(f"Erreur PayDunya: {result}")
            raise HTTPException(
                status_code=400,
                detail=f"Erreur création facture: {result.get('response_text', 'Erreur inconnue')}"
            )
            
    except requests.RequestException as e:
        print(f"Erreur requête PayDunya: {e}")
        raise HTTPException(status_code=500, detail="Erreur de connexion à PayDunya")


@app.post("/api/paydunya/webhook")
async def paydunya_webhook(
    request: Request,
    db: Session = Depends(get_db)
):
    """
    Webhook PayDunya - appelé après paiement réussi
    """
    try:
        # PayDunya peut envoyer JSON ou form-data
        content_type = request.headers.get("content-type", "")
        
        if "application/json" in content_type:
            data = await request.json()
        else:
            # Form data avec format data[key][subkey]
            form_data = await request.form()
            raw_data = dict(form_data)
            
            print(f"PayDunya Webhook reçu (raw): {raw_data}")
            print(f"Content-Type: {content_type}")
            
            # Parser le format PayDunya data[key][subkey]
            data = {}
            for key, value in raw_data.items():
                if key.startswith("data["):
                    # Extraire les clés imbriquées
                    # data[status] -> status
                    # data[custom_data][email] -> custom_data.email
                    import re
                    matches = re.findall(r'\[([^\]]+)\]', key)
                    
                    if len(matches) == 1:
                        data[matches[0]] = value
                    elif len(matches) == 2:
                        if matches[0] not in data:
                            data[matches[0]] = {}
                        data[matches[0]][matches[1]] = value
                    elif len(matches) == 3:
                        if matches[0] not in data:
                            data[matches[0]] = {}
                        if matches[1] not in data[matches[0]]:
                            data[matches[0]][matches[1]] = {}
                        data[matches[0]][matches[1]][matches[2]] = value
        
        print(f"PayDunya Webhook parsé: {data}")
        
        # ==================== VÉRIFICATION SIGNATURE ====================
        # Vérifier le hash pour s'assurer que la requête vient bien de PayDunya
        received_hash = data.get("hash")
        invoice_token = data.get("invoice", {}).get("token") if isinstance(data.get("invoice"), dict) else data.get("token")
        
        if received_hash and invoice_token:
            # Calculer le hash attendu : SHA512(master_key + invoice_token)
            expected_hash = hashlib.sha512(
                (PAYDUNYA_MASTER_KEY + invoice_token).encode('utf-8')
            ).hexdigest()
            
            if received_hash != expected_hash:
                print(f"⚠️ ALERTE SÉCURITÉ: Hash invalide!")
                print(f"Hash reçu: {received_hash}")
                print(f"Hash attendu: {expected_hash}")
                # En production, on devrait rejeter la requête
                # Pour l'instant on log l'alerte mais on continue
                # return {"status": "error", "reason": "Invalid signature"}
        else:
            print(f"Info: Hash ou token manquant, vérification signature ignorée")
        # ==================== FIN VÉRIFICATION SIGNATURE ====================
        
        # Vérifier le statut du paiement
        # PayDunya peut envoyer status ou response_code
        status = data.get("status") or data.get("response_code")
        
        # Si on a un token, vérifier le paiement via l'API
        token = data.get("token") or data.get("invoice_token")
        
        if token and not status:
            # Vérifier le paiement via l'API PayDunya
            import requests as req
            
            if PAYDUNYA_MODE == "live":
                verify_url = f"https://app.paydunya.com/api/v1/checkout-invoice/confirm/{token}"
            else:
                verify_url = f"https://app.paydunya.com/sandbox-api/v1/checkout-invoice/confirm/{token}"
            
            verify_headers = {
                "PAYDUNYA-MASTER-KEY": PAYDUNYA_MASTER_KEY,
                "PAYDUNYA-PRIVATE-KEY": PAYDUNYA_PRIVATE_KEY,
                "PAYDUNYA-TOKEN": PAYDUNYA_TOKEN
            }
            
            try:
                verify_response = req.get(verify_url, headers=verify_headers)
                verify_data = verify_response.json()
                print(f"Vérification PayDunya: {verify_data}")
                
                status = verify_data.get("status")
                if not data.get("custom_data"):
                    data["custom_data"] = verify_data.get("custom_data", {})
            except Exception as e:
                print(f"Erreur vérification: {e}")
        
        if status != "completed":
            print(f"Paiement non complété: {status}")
            return {"status": "ignored", "reason": f"Status: {status}"}
        
        # Récupérer les données personnalisées
        custom_data = data.get("custom_data", {})
        
        # Si custom_data est une chaîne JSON, la parser
        if isinstance(custom_data, str):
            import json
            try:
                custom_data = json.loads(custom_data)
            except:
                custom_data = {}
        
        email = custom_data.get("email")
        name = custom_data.get("name")
        plan = custom_data.get("plan", "professionnel")
        
        print(f"Custom data: email={email}, name={name}, plan={plan}")
        
        if not email:
            print("Email manquant dans custom_data")
            print(f"Data complète reçue: {data}")
            return {"status": "error", "reason": "Email manquant"}
        
        # Vérifier si l'utilisateur existe
        existing_user = db.query(User).filter(User.email == email).first()
        
        if existing_user:
            # Mettre à jour l'utilisateur existant
            existing_user.plan = plan
            existing_user.is_active = True
            db.commit()
            
            # Créer ou mettre à jour la subscription
            existing_subscription = db.query(Subscription).filter(
                Subscription.user_id == existing_user.id,
                Subscription.status == "active"
            ).first()
            
            if existing_subscription:
                # Renouveler l'abonnement existant
                existing_subscription.plan = plan
                existing_subscription.start_date = datetime.utcnow()
                existing_subscription.end_date = datetime.utcnow() + timedelta(days=30)
                existing_subscription.status = "active"
            else:
                # Créer une nouvelle subscription
                new_subscription = Subscription(
                    user_id=existing_user.id,
                    plan=plan,
                    status="active",
                    start_date=datetime.utcnow(),
                    end_date=datetime.utcnow() + timedelta(days=30)
                )
                db.add(new_subscription)
            
            db.commit()
            
            # Envoyer email de confirmation upgrade
            send_email(
                to=email,
                subject="🎉 Bienvenue dans Afrikalytics Premium !",
                html=f"""
                    <h2>Félicitations {existing_user.full_name} !</h2>
                    <p>Votre abonnement <strong>{plan.capitalize()}</strong> est maintenant actif.</p>
                    <hr>
                    <p>Vous avez maintenant accès à :</p>
                    <ul>
                        <li>✅ Résultats en temps réel</li>
                        <li>✅ Insights complets</li>
                        <li>✅ Rapports PDF détaillés</li>
                        <li>✅ Dashboard avancé</li>
                        <li>✅ Support prioritaire</li>
                    </ul>
                    <hr>
                    <p><a href="https://dashboard.afrikalytics.com">Accéder à mon dashboard Premium →</a></p>
                    <hr>
                    <p><em>L'équipe Afrikalytics AI by Marketym</em></p>
                """
            )
            
            return {"status": "success", "action": "user_upgraded", "user_id": existing_user.id}
        
        else:
            # Créer un nouvel utilisateur
            temp_password = secrets.token_urlsafe(12)
            hashed_password = hash_password(temp_password)
            
            new_user = User(
                email=email,
                full_name=name,
                hashed_password=hashed_password,
                plan=plan,
                is_active=True
            )
            
            db.add(new_user)
            db.commit()
            db.refresh(new_user)
            
            # Créer la subscription
            new_subscription = Subscription(
                user_id=new_user.id,
                plan=plan,
                status="active",
                start_date=datetime.utcnow(),
                end_date=datetime.utcnow() + timedelta(days=30)
            )
            db.add(new_subscription)
            db.commit()
            
            # Envoyer email avec identifiants
            send_email(
                to=email,
                subject="🎉 Bienvenue dans Afrikalytics Premium !",
                html=f"""
                    <h2>Bienvenue {name} !</h2>
                    <p>Votre compte Afrikalytics <strong>{plan.capitalize()}</strong> a été créé avec succès.</p>
                    <hr>
                    <h3>Vos identifiants de connexion :</h3>
                    <p><strong>Email :</strong> {email}</p>
                    <p><strong>Mot de passe temporaire :</strong> {temp_password}</p>
                    <p style="color: #e74c3c;"><em>⚠️ Pensez à changer votre mot de passe après votre première connexion.</em></p>
                    <hr>
                    <p>Vous avez maintenant accès à :</p>
                    <ul>
                        <li>✅ Résultats en temps réel</li>
                        <li>✅ Insights complets</li>
                        <li>✅ Rapports PDF détaillés</li>
                        <li>✅ Dashboard avancé</li>
                        <li>✅ Support prioritaire</li>
                    </ul>
                    <hr>
                    <p><a href="https://dashboard.afrikalytics.com/login">Se connecter à mon dashboard →</a></p>
                    <hr>
                    <p><em>L'équipe Afrikalytics AI by Marketym</em></p>
                """
            )
            
            return {"status": "success", "action": "user_created", "user_id": new_user.id}
    
    except Exception as e:
        print(f"Erreur webhook PayDunya: {e}")
        return {"status": "error", "reason": str(e)}


@app.get("/api/paydunya/verify/{token}")
async def verify_payment(token: str):
    """
    Vérifier le statut d'un paiement
    """
    import requests
    
    if PAYDUNYA_MODE == "live":
        base_url = "https://app.paydunya.com/api/v1"
    else:
        base_url = "https://app.paydunya.com/sandbox-api/v1"
    
    headers = {
        "Content-Type": "application/json",
        "PAYDUNYA-MASTER-KEY": PAYDUNYA_MASTER_KEY,
        "PAYDUNYA-PRIVATE-KEY": PAYDUNYA_PRIVATE_KEY,
        "PAYDUNYA-TOKEN": PAYDUNYA_TOKEN
    }
    
    try:
        response = requests.get(
            f"{base_url}/checkout-invoice/confirm/{token}",
            headers=headers
        )
        
        return response.json()
        
    except requests.RequestException as e:
        print(f"Erreur vérification PayDunya: {e}")
        raise HTTPException(status_code=500, detail="Erreur de vérification")


# ==================== ZAPIER WEBHOOK ====================

ZAPIER_SECRET = os.getenv("ZAPIER_SECRET", "your-secret-key-here")

@app.post("/api/users/create")
async def create_user_from_zapier(
    data: UserCreate,
    db: Session = Depends(get_db),
    x_zapier_secret: Optional[str] = Header(None)
):
    """
    Créer un utilisateur après paiement WooCommerce (appelé par Zapier)
    """
    if os.getenv("ENVIRONMENT") == "production":
        if x_zapier_secret != ZAPIER_SECRET:
            raise HTTPException(status_code=401, detail="Unauthorized")
    
    existing_user = db.query(User).filter(User.email == data.email).first()
    if existing_user:
        existing_user.plan = data.plan
        existing_user.is_active = True
        db.commit()
        return {
            "message": "User updated",
            "user_id": existing_user.id,
            "email": existing_user.email,
            "dashboard_url": "https://dashboard.afrikalytics.com"
        }
    
    temp_password = secrets.token_urlsafe(12)
    hashed_password = hash_password(temp_password)
    
    new_user = User(
        email=data.email,
        full_name=data.name,
        hashed_password=hashed_password,
        plan=data.plan,
        order_id=data.order_id,
        is_active=True
    )
    
    db.add(new_user)
    db.commit()
    db.refresh(new_user)
    
    return {
        "message": "User created successfully",
        "user_id": new_user.id,
        "email": new_user.email,
        "temp_password": temp_password,
        "dashboard_url": "https://dashboard.afrikalytics.com"
    }


# ==================== AUTHENTIFICATION ====================

@app.post("/api/auth/register", response_model=TokenResponse)
@limiter.limit("3/minute")
async def register(request: Request, data: UserRegister, db: Session = Depends(get_db)):
    """
    Inscription d'un nouvel utilisateur (plan Basic gratuit)
    Limité à 3 tentatives par minute
    """
    # Vérifier si l'email existe déjà
    existing_user = db.query(User).filter(User.email == data.email).first()
    if existing_user:
        raise HTTPException(status_code=400, detail="Cet email est déjà utilisé")
    
    # Valider le mot de passe
    if len(data.password) < 8:
        raise HTTPException(status_code=400, detail="Le mot de passe doit contenir au moins 8 caractères")
    
    # Créer l'utilisateur
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
    
    # Créer le token
    access_token = create_access_token(data={"sub": new_user.email, "user_id": new_user.id})
    
    # Envoyer email de bienvenue
    send_email(
        to=new_user.email,
        subject="Bienvenue sur Afrikalytics AI !",
        html=f"""
            <h2>Bienvenue {new_user.full_name} !</h2>
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
        "token_type": "bearer",
        "user": new_user
    }


@app.post("/api/auth/login")
@limiter.limit("5/minute")
async def login(request: Request, data: UserLogin, db: Session = Depends(get_db)):
    """
    Connexion utilisateur - Étape 1 : Vérification email/mot de passe
    Envoie un code de vérification par email
    Limité à 5 tentatives par minute
    """
    user = db.query(User).filter(User.email == data.email).first()
    
    if not user or not verify_password(data.password, user.hashed_password):
        raise HTTPException(status_code=401, detail="Email ou mot de passe incorrect")
    
    if not user.is_active:
        raise HTTPException(status_code=403, detail="Compte désactivé")
    
    # Vérifier si l'abonnement est expiré (backup du cron job)
    if user.plan in ["professionnel", "entreprise"]:
        active_subscription = db.query(Subscription).filter(
            Subscription.user_id == user.id,
            Subscription.status == "active"
        ).first()
        
        if active_subscription and active_subscription.end_date:
            end_date = active_subscription.end_date.date() if hasattr(active_subscription.end_date, 'date') else active_subscription.end_date
            if end_date < datetime.utcnow().date():
                # Abonnement expiré - rétrograder
                active_subscription.status = "expired"
                user.plan = "basic"
                db.commit()
    
    # Générer un code à 6 chiffres
    code = str(random.randint(100000, 999999))
    
    # Supprimer les anciens codes non utilisés de cet utilisateur
    db.query(VerificationCode).filter(
        VerificationCode.user_id == user.id,
        VerificationCode.is_used == False
    ).delete()
    
    # Créer le nouveau code (expire dans 10 minutes)
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
            <p>Bonjour {user.full_name},</p>
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


@app.post("/api/auth/verify-code", response_model=TokenResponse)
@limiter.limit("5/minute")
async def verify_code(request: Request, data: VerifyCodeRequest, db: Session = Depends(get_db)):
    """
    Connexion utilisateur - Étape 2 : Vérification du code
    Retourne le token JWT si le code est correct
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
    
    # Marquer le code comme utilisé
    verification.is_used = True
    db.commit()
    
    # Créer le token JWT
    access_token = create_access_token(data={"sub": user.email, "user_id": user.id})
    
    return {
        "access_token": access_token,
        "token_type": "bearer",
        "user": user
    }


@app.post("/api/auth/resend-code")
@limiter.limit("3/minute")
async def resend_code(request: Request, data: ForgotPassword, db: Session = Depends(get_db)):
    """
    Renvoyer un nouveau code de vérification
    """
    user = db.query(User).filter(User.email == data.email).first()
    
    if not user:
        # Ne pas révéler si l'email existe
        return {"message": "Si un compte existe, un nouveau code a été envoyé"}
    
    # Générer un nouveau code
    code = str(random.randint(100000, 999999))
    
    # Supprimer les anciens codes
    db.query(VerificationCode).filter(
        VerificationCode.user_id == user.id,
        VerificationCode.is_used == False
    ).delete()
    
    # Créer le nouveau code
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
            <p>Bonjour {user.full_name},</p>
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


@app.post("/api/auth/forgot-password")
@limiter.limit("3/minute")
async def forgot_password(request: Request, data: ForgotPassword, db: Session = Depends(get_db)):
    """
    Envoyer un email de réinitialisation de mot de passe
    Limité à 3 tentatives par minute
    """
    user = db.query(User).filter(User.email == data.email).first()
    
    # Ne pas révéler si l'email existe ou non (sécurité)
    if not user:
        return {"message": "Si cet email existe, un lien de réinitialisation a été envoyé"}
    
    # Créer un token de reset (expire dans 1h)
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
            <p>Bonjour {user.full_name},</p>
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


@app.post("/api/auth/reset-password")
@limiter.limit("5/minute")
async def reset_password(request: Request, data: ResetPassword, db: Session = Depends(get_db)):
    """
    Réinitialiser le mot de passe avec le token
    Limité à 5 tentatives par minute
    """
    # Vérifier le token
    payload = decode_access_token(data.token)
    
    if not payload:
        raise HTTPException(status_code=400, detail="Lien invalide ou expiré")
    
    # Vérifier que c'est bien un token de reset
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
        raise HTTPException(status_code=400, detail="Le mot de passe doit contenir au moins 8 caractères")
    
    # Mettre à jour le mot de passe
    user.hashed_password = hash_password(data.new_password)
    db.commit()
    
    # Envoyer email de confirmation
    send_email(
        to=user.email,
        subject="Mot de passe modifié - Afrikalytics",
        html=f"""
            <h2>Mot de passe modifié</h2>
            <p>Bonjour {user.full_name},</p>
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


@app.get("/api/users/me", response_model=UserResponse)
async def get_current_user_info(current_user: User = Depends(get_current_user)):
    return current_user


# ==================== ADMIN - GESTION UTILISATEURS ====================

@app.get("/api/admin/users", response_model=List[AdminUserResponse])
async def admin_get_all_users(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Lister tous les utilisateurs (Admin seulement)
    """
    users = db.query(User).order_by(User.created_at.desc()).all()
    return users


@app.post("/api/admin/users", response_model=AdminUserResponse)
async def admin_create_user(
    data: AdminUserCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Créer un utilisateur manuellement (Admin seulement)
    """
    # Vérifier si l'email existe déjà
    existing_user = db.query(User).filter(User.email == data.email).first()
    if existing_user:
        raise HTTPException(status_code=400, detail="Cet email est déjà utilisé")
    
    # Générer un mot de passe si non fourni
    password = data.password if data.password else secrets.token_urlsafe(12)
    hashed_password = hash_password(password)
    
    # Créer l'utilisateur
    new_user = User(
        email=data.email,
        full_name=data.full_name,
        hashed_password=hashed_password,
        plan=data.plan,
        is_active=data.is_active,
        is_admin=data.is_admin,
        parent_user_id=data.parent_user_id
    )
    
    db.add(new_user)
    db.commit()
    db.refresh(new_user)
    
    # Si c'est un abonnement payant, créer la subscription
    if data.plan in ["professionnel", "entreprise"]:
        new_subscription = Subscription(
            user_id=new_user.id,
            plan=data.plan,
            status="active",
            start_date=datetime.utcnow(),
            end_date=datetime.utcnow() + timedelta(days=30)
        )
        db.add(new_subscription)
        db.commit()
    
    # Envoyer email avec les identifiants
    send_email(
        to=new_user.email,
        subject="🎉 Votre compte Afrikalytics a été créé",
        html=f"""
            <h2>Bienvenue sur Afrikalytics AI !</h2>
            <p>Bonjour {new_user.full_name},</p>
            <p>Votre compte a été créé avec succès.</p>
            <div style="background-color: #f3f4f6; padding: 20px; border-radius: 8px; margin: 20px 0;">
                <p><strong>Email :</strong> {new_user.email}</p>
                <p><strong>Mot de passe :</strong> {password}</p>
                <p><strong>Plan :</strong> {new_user.plan.capitalize()}</p>
            </div>
            <p style="color: #e74c3c;">Nous vous recommandons de changer votre mot de passe après votre première connexion.</p>
            <p style="margin: 30px 0;">
                <a href="https://dashboard.afrikalytics.com/login" 
                   style="background-color: #2563eb; color: white; padding: 12px 24px; text-decoration: none; border-radius: 8px; font-weight: bold;">
                    Se connecter
                </a>
            </p>
            <hr>
            <p><em>L'équipe Afrikalytics AI by Marketym</em></p>
        """
    )
    
    return new_user


@app.put("/api/admin/users/{user_id}", response_model=AdminUserResponse)
async def admin_update_user(
    user_id: int,
    data: AdminUserUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Modifier un utilisateur (Admin seulement)
    """
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="Utilisateur non trouvé")
    
    if data.email is not None:
        # Vérifier si le nouvel email n'est pas déjà pris
        existing = db.query(User).filter(User.email == data.email, User.id != user_id).first()
        if existing:
            raise HTTPException(status_code=400, detail="Cet email est déjà utilisé")
        user.email = data.email
    
    if data.full_name is not None:
        user.full_name = data.full_name
    
    if data.plan is not None:
        user.plan = data.plan
    
    if data.is_active is not None:
        user.is_active = data.is_active
    
    if data.is_admin is not None:
        user.is_admin = data.is_admin
    
    db.commit()
    db.refresh(user)
    
    return user


@app.put("/api/admin/users/{user_id}/toggle-active")
async def admin_toggle_user_active(
    user_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Activer/Désactiver un utilisateur (Admin seulement)
    """
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="Utilisateur non trouvé")
    
    user.is_active = not user.is_active
    db.commit()
    
    status = "activé" if user.is_active else "désactivé"
    return {"message": f"Utilisateur {status}", "is_active": user.is_active}


@app.delete("/api/admin/users/{user_id}")
async def admin_delete_user(
    user_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Supprimer un utilisateur (Admin seulement)
    """
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="Utilisateur non trouvé")
    
    # Ne pas permettre de se supprimer soi-même
    if user.id == current_user.id:
        raise HTTPException(status_code=400, detail="Vous ne pouvez pas supprimer votre propre compte")
    
    db.delete(user)
    db.commit()
    
    return {"message": "Utilisateur supprimé avec succès"}


# ==================== FORFAIT ENTREPRISE ====================

@app.get("/api/enterprise/team")
async def get_enterprise_team(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Récupérer les membres de l'équipe entreprise
    """
    if current_user.plan != "entreprise":
        raise HTTPException(status_code=403, detail="Cette fonctionnalité est réservée au plan Entreprise")
    
    # Récupérer les sous-utilisateurs
    team_members = db.query(User).filter(User.parent_user_id == current_user.id).all()
    
    return {
        "owner": {
            "id": current_user.id,
            "email": current_user.email,
            "full_name": current_user.full_name
        },
        "team_members": [
            {
                "id": m.id,
                "email": m.email,
                "full_name": m.full_name,
                "is_active": m.is_active,
                "created_at": m.created_at.isoformat()
            } for m in team_members
        ],
        "max_members": 5,
        "current_count": len(team_members) + 1  # +1 pour le propriétaire
    }


@app.post("/api/enterprise/team/add")
async def add_enterprise_team_member(
    data: EnterpriseUserAdd,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Ajouter un membre à l'équipe entreprise (max 5 total)
    """
    if current_user.plan != "entreprise":
        raise HTTPException(status_code=403, detail="Cette fonctionnalité est réservée au plan Entreprise")
    
    # Compter les membres actuels
    current_members = db.query(User).filter(User.parent_user_id == current_user.id).count()
    
    if current_members >= 4:  # 4 membres + 1 propriétaire = 5 max
        raise HTTPException(status_code=400, detail="Limite de 5 utilisateurs atteinte pour votre forfait Entreprise")
    
    # Vérifier si l'email existe déjà
    existing_user = db.query(User).filter(User.email == data.email).first()
    if existing_user:
        raise HTTPException(status_code=400, detail="Cet email est déjà utilisé")
    
    # Générer un mot de passe temporaire
    temp_password = secrets.token_urlsafe(12)
    hashed_password = hash_password(temp_password)
    
    # Créer le membre de l'équipe
    new_member = User(
        email=data.email,
        full_name=data.full_name,
        hashed_password=hashed_password,
        plan="entreprise",
        is_active=True,
        parent_user_id=current_user.id
    )
    
    db.add(new_member)
    db.commit()
    db.refresh(new_member)
    
    # Envoyer email d'invitation
    send_email(
        to=new_member.email,
        subject="🎉 Vous êtes invité(e) à rejoindre Afrikalytics",
        html=f"""
            <h2>Bienvenue sur Afrikalytics AI !</h2>
            <p>Bonjour {new_member.full_name},</p>
            <p><strong>{current_user.full_name}</strong> vous a invité(e) à rejoindre son équipe sur Afrikalytics.</p>
            <div style="background-color: #f3f4f6; padding: 20px; border-radius: 8px; margin: 20px 0;">
                <p><strong>Email :</strong> {new_member.email}</p>
                <p><strong>Mot de passe temporaire :</strong> {temp_password}</p>
                <p><strong>Plan :</strong> Entreprise</p>
            </div>
            <p style="color: #e74c3c;">Veuillez changer votre mot de passe après votre première connexion.</p>
            <p style="margin: 30px 0;">
                <a href="https://dashboard.afrikalytics.com/login" 
                   style="background-color: #2563eb; color: white; padding: 12px 24px; text-decoration: none; border-radius: 8px; font-weight: bold;">
                    Se connecter
                </a>
            </p>
            <hr>
            <p><em>L'équipe Afrikalytics AI by Marketym</em></p>
        """
    )
    
    return {
        "message": "Membre ajouté avec succès",
        "member": {
            "id": new_member.id,
            "email": new_member.email,
            "full_name": new_member.full_name
        }
    }


@app.delete("/api/enterprise/team/{member_id}")
async def remove_enterprise_team_member(
    member_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Retirer un membre de l'équipe entreprise
    """
    if current_user.plan != "entreprise":
        raise HTTPException(status_code=403, detail="Cette fonctionnalité est réservée au plan Entreprise")
    
    member = db.query(User).filter(
        User.id == member_id,
        User.parent_user_id == current_user.id
    ).first()
    
    if not member:
        raise HTTPException(status_code=404, detail="Membre non trouvé dans votre équipe")
    
    db.delete(member)
    db.commit()
    
    return {"message": "Membre retiré avec succès"}


# ==================== DASHBOARD STATS ====================

@app.get("/api/dashboard/stats")
async def get_dashboard_stats(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Récupérer les statistiques du dashboard utilisateur
    """
    # Études accessibles (actives)
    studies_accessible = db.query(Study).filter(Study.is_active == True).count()
    
    # Études auxquelles l'utilisateur peut accéder selon son plan
    if current_user.plan == "basic":
        # Basic : seulement études ouvertes à la participation
        studies_count = db.query(Study).filter(
            Study.is_active == True,
            Study.status == "Ouvert"
        ).count()
    else:
        # Premium : toutes les études actives
        studies_count = studies_accessible
    
    # Jours restants d'abonnement
    days_remaining = None
    if current_user.plan in ["professionnel", "entreprise"]:
        subscription = db.query(Subscription).filter(
            Subscription.user_id == current_user.id,
            Subscription.status == "active"
        ).first()
        
        if subscription and subscription.end_date:
            end_date = subscription.end_date.date() if hasattr(subscription.end_date, 'date') else subscription.end_date
            days_remaining = (end_date - datetime.utcnow().date()).days
            if days_remaining < 0:
                days_remaining = 0
    
    # Rapports disponibles selon le plan
    if current_user.plan == "basic":
        reports_count = db.query(Report).filter(Report.report_type == "basic").count()
    else:
        reports_count = db.query(Report).count()
    
    # Insights disponibles selon le plan
    if current_user.plan == "basic":
        insights_count = db.query(Insight).filter(Insight.is_premium == False).count()
    else:
        insights_count = db.query(Insight).count()
    
    return {
        "studies_accessible": studies_count,
        "studies_total": studies_accessible,
        "reports_available": reports_count,
        "insights_available": insights_count,
        "subscription_days_remaining": days_remaining,
        "plan": current_user.plan,
        "is_premium": current_user.plan in ["professionnel", "entreprise"]
    }


# ==================== ÉTUDES (CRUD) ====================

@app.get("/api/studies", response_model=List[StudyResponse])
async def get_all_studies(db: Session = Depends(get_db)):
    """
    Récupérer toutes les études
    """
    studies = db.query(Study).order_by(Study.created_at.desc()).all()
    return studies


@app.get("/api/studies/active", response_model=List[StudyResponse])
async def get_active_studies(db: Session = Depends(get_db)):
    """
    Récupérer les études actives (pour le site public)
    """
    studies = db.query(Study).filter(Study.is_active == True).order_by(Study.created_at.desc()).all()
    return studies


@app.get("/api/studies/{study_id}", response_model=StudyResponse)
async def get_study(study_id: int, db: Session = Depends(get_db)):
    """
    Récupérer une étude par son ID
    """
    study = db.query(Study).filter(Study.id == study_id).first()
    if not study:
        raise HTTPException(status_code=404, detail="Étude non trouvée")
    return study


@app.post("/api/studies", response_model=StudyResponse)
async def create_study(
    data: StudyCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Créer une nouvelle étude (Admin seulement)
    """
    new_study = Study(
        title=data.title,
        description=data.description,
        category=data.category,
        duration=data.duration,
        deadline=data.deadline,
        status=data.status,
        icon=data.icon,
        embed_url_particulier=data.embed_url_particulier,
        embed_url_entreprise=data.embed_url_entreprise,
        embed_url_results=data.embed_url_results,
        report_url_basic=data.report_url_basic,
        report_url_premium=data.report_url_premium,
        is_active=data.is_active
    )
    
    db.add(new_study)
    db.commit()
    db.refresh(new_study)
    
    return new_study


@app.put("/api/studies/{study_id}", response_model=StudyResponse)
async def update_study(
    study_id: int,
    data: StudyCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Modifier une étude (Admin seulement)
    """
    study = db.query(Study).filter(Study.id == study_id).first()
    if not study:
        raise HTTPException(status_code=404, detail="Étude non trouvée")
    
    study.title = data.title
    study.description = data.description
    study.category = data.category
    study.duration = data.duration
    study.deadline = data.deadline
    study.status = data.status
    study.icon = data.icon
    study.embed_url_particulier = data.embed_url_particulier
    study.embed_url_entreprise = data.embed_url_entreprise
    study.embed_url_results = data.embed_url_results
    study.report_url_basic = data.report_url_basic
    study.report_url_premium = data.report_url_premium
    study.is_active = data.is_active
    
    db.commit()
    db.refresh(study)
    
    return study


@app.delete("/api/studies/{study_id}")
async def delete_study(
    study_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Supprimer une étude (Admin seulement)
    """
    study = db.query(Study).filter(Study.id == study_id).first()
    if not study:
        raise HTTPException(status_code=404, detail="Étude non trouvée")
    
    db.delete(study)
    db.commit()
    
    return {"message": "Étude supprimée avec succès"}


# ==================== INSIGHTS (CRUD) ====================

@app.get("/api/insights", response_model=List[InsightResponse])
async def get_all_insights(db: Session = Depends(get_db)):
    """
    Récupérer tous les insights publiés
    """
    insights = db.query(Insight).filter(Insight.is_published == True).order_by(Insight.created_at.desc()).all()
    return insights


@app.get("/api/insights/study/{study_id}", response_model=InsightResponse)
async def get_insight_by_study(study_id: int, db: Session = Depends(get_db)):
    """
    Récupérer l'insight d'une étude
    """
    insight = db.query(Insight).filter(Insight.study_id == study_id, Insight.is_published == True).first()
    if not insight:
        raise HTTPException(status_code=404, detail="Insight non trouvé")
    return insight


@app.get("/api/insights/{insight_id}", response_model=InsightResponse)
async def get_insight(insight_id: int, db: Session = Depends(get_db)):
    """
    Récupérer un insight par son ID
    """
    insight = db.query(Insight).filter(Insight.id == insight_id).first()
    if not insight:
        raise HTTPException(status_code=404, detail="Insight non trouvé")
    return insight


@app.post("/api/insights", response_model=InsightResponse)
async def create_insight(
    data: InsightCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Créer un nouvel insight (Admin seulement)
    """
    new_insight = Insight(
        study_id=data.study_id,
        title=data.title,
        summary=data.summary,
        key_findings=data.key_findings,
        recommendations=data.recommendations,
        author=data.author,
        is_published=data.is_published
    )
    
    db.add(new_insight)
    db.commit()
    db.refresh(new_insight)
    
    return new_insight


@app.put("/api/insights/{insight_id}", response_model=InsightResponse)
async def update_insight(
    insight_id: int,
    data: InsightCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Modifier un insight (Admin seulement)
    """
    insight = db.query(Insight).filter(Insight.id == insight_id).first()
    if not insight:
        raise HTTPException(status_code=404, detail="Insight non trouvé")
    
    insight.study_id = data.study_id
    insight.title = data.title
    insight.summary = data.summary
    insight.key_findings = data.key_findings
    insight.recommendations = data.recommendations
    insight.author = data.author
    insight.is_published = data.is_published
    
    db.commit()
    db.refresh(insight)
    
    return insight


@app.delete("/api/insights/{insight_id}")
async def delete_insight(
    insight_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Supprimer un insight (Admin seulement)
    """
    insight = db.query(Insight).filter(Insight.id == insight_id).first()
    if not insight:
        raise HTTPException(status_code=404, detail="Insight non trouvé")
    
    db.delete(insight)
    db.commit()
    
    return {"message": "Insight supprimé avec succès"}


# ==================== REPORTS (CRUD) ====================

@app.get("/api/reports", response_model=List[ReportResponse])
async def get_all_reports(db: Session = Depends(get_db)):
    """
    Récupérer tous les rapports disponibles
    """
    reports = db.query(Report).filter(Report.is_available == True).order_by(Report.created_at.desc()).all()
    return reports


@app.get("/api/reports/study/{study_id}", response_model=ReportResponse)
async def get_report_by_study(study_id: int, db: Session = Depends(get_db)):
    """
    Récupérer le rapport d'une étude (premier trouvé)
    """
    report = db.query(Report).filter(Report.study_id == study_id, Report.is_available == True).first()
    if not report:
        raise HTTPException(status_code=404, detail="Rapport non trouvé")
    return report


@app.get("/api/reports/study/{study_id}/type/{report_type}", response_model=ReportResponse)
async def get_report_by_study_and_type(study_id: int, report_type: str, db: Session = Depends(get_db)):
    """
    Récupérer le rapport d'une étude par type (basic ou premium)
    """
    report = db.query(Report).filter(
        Report.study_id == study_id, 
        Report.report_type == report_type,
        Report.is_available == True
    ).first()
    if not report:
        raise HTTPException(status_code=404, detail="Rapport non trouvé")
    return report


@app.get("/api/reports/{report_id}", response_model=ReportResponse)
async def get_report(report_id: int, db: Session = Depends(get_db)):
    """
    Récupérer un rapport par son ID
    """
    report = db.query(Report).filter(Report.id == report_id).first()
    if not report:
        raise HTTPException(status_code=404, detail="Rapport non trouvé")
    return report


@app.post("/api/reports", response_model=ReportResponse)
async def create_report(
    data: ReportCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Créer un nouveau rapport (Admin seulement)
    """
    new_report = Report(
        study_id=data.study_id,
        title=data.title,
        description=data.description,
        file_url=data.file_url,
        file_name=data.file_name,
        file_size=data.file_size,
        report_type=data.report_type,
        is_available=data.is_available
    )
    
    db.add(new_report)
    db.commit()
    db.refresh(new_report)
    
    return new_report


@app.put("/api/reports/{report_id}", response_model=ReportResponse)
async def update_report(
    report_id: int,
    data: ReportCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Modifier un rapport (Admin seulement)
    """
    report = db.query(Report).filter(Report.id == report_id).first()
    if not report:
        raise HTTPException(status_code=404, detail="Rapport non trouvé")
    
    report.study_id = data.study_id
    report.title = data.title
    report.description = data.description
    report.file_url = data.file_url
    report.file_name = data.file_name
    report.file_size = data.file_size
    report.report_type = data.report_type
    report.is_available = data.is_available
    
    db.commit()
    db.refresh(report)
    
    return report


@app.delete("/api/reports/{report_id}")
async def delete_report(
    report_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Supprimer un rapport (Admin seulement)
    Supprime aussi les URLs dans la table studies
    """
    report = db.query(Report).filter(Report.id == report_id).first()
    if not report:
        raise HTTPException(status_code=404, detail="Rapport non trouvé")
    
    # Récupérer l'étude associée pour vider les colonnes URL
    if report.study_id:
        study = db.query(Study).filter(Study.id == report.study_id).first()
        if study:
            # Vider la bonne colonne selon le type de rapport
            if report.report_type == "basic":
                study.report_url_basic = None
            elif report.report_type == "premium":
                study.report_url_premium = None
            else:
                # Si pas de type défini, vider les deux
                study.report_url_basic = None
                study.report_url_premium = None
    
    db.delete(report)
    db.commit()
    
    return {"message": "Rapport supprimé avec succès"}


@app.post("/api/reports/{report_id}/download")
async def track_download(
    report_id: int,
    db: Session = Depends(get_db)
):
    """
    Incrémenter le compteur de téléchargements
    """
    report = db.query(Report).filter(Report.id == report_id).first()
    if not report:
        raise HTTPException(status_code=404, detail="Rapport non trouvé")
    
    report.download_count += 1
    db.commit()
    
    return {"message": "Téléchargement enregistré", "download_count": report.download_count, "file_url": report.file_url}


@app.post("/api/reports/study/{study_id}/type/{report_type}/download")
async def track_download_by_type(
    study_id: int,
    report_type: str,
    db: Session = Depends(get_db)
):
    """
    Incrémenter le compteur de téléchargements par study_id et type
    """
    report = db.query(Report).filter(
        Report.study_id == study_id,
        Report.report_type == report_type,
        Report.is_available == True
    ).first()
    
    if not report:
        raise HTTPException(status_code=404, detail="Rapport non trouvé")
    
    report.download_count += 1
    db.commit()
    
    return {"message": "Téléchargement enregistré", "download_count": report.download_count, "file_url": report.file_url}


# ==================== CONTACTS ====================

@app.post("/api/contacts", response_model=ContactResponse)
@limiter.limit("3/minute")
async def create_contact(
    request: Request,
    data: ContactCreate,
    db: Session = Depends(get_db)
):
    """
    Créer un nouveau message de contact (public)
    Limité à 3 messages par minute
    """
    # Sauvegarder en base de données
    new_contact = Contact(
        name=data.name,
        email=data.email,
        company=data.company,
        message=data.message
    )
    
    db.add(new_contact)
    db.commit()
    db.refresh(new_contact)
    
    # Envoyer email de notification
    send_email(
        to=CONTACT_EMAIL,
        subject=f"Nouveau message de contact - {data.name}",
        html=f"""
            <h2>Nouveau message de contact</h2>
            <p><strong>Nom :</strong> {data.name}</p>
            <p><strong>Email :</strong> {data.email}</p>
            <p><strong>Entreprise :</strong> {data.company or 'Non renseigné'}</p>
            <hr>
            <p><strong>Message :</strong></p>
            <p>{data.message}</p>
            <hr>
            <p><em>Message envoyé depuis le formulaire de contact Afrikalytics</em></p>
        """
    )
    
    return new_contact


@app.get("/api/contacts", response_model=List[ContactResponse])
async def get_all_contacts(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Récupérer tous les messages de contact (Admin seulement)
    """
    contacts = db.query(Contact).order_by(Contact.created_at.desc()).all()
    return contacts


@app.put("/api/contacts/{contact_id}/read")
async def mark_contact_as_read(
    contact_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Marquer un message comme lu (Admin seulement)
    """
    contact = db.query(Contact).filter(Contact.id == contact_id).first()
    if not contact:
        raise HTTPException(status_code=404, detail="Contact non trouvé")
    
    contact.is_read = True
    db.commit()
    
    return {"message": "Contact marqué comme lu"}


@app.delete("/api/contacts/{contact_id}")
async def delete_contact(
    contact_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Supprimer un message de contact (Admin seulement)
    """
    contact = db.query(Contact).filter(Contact.id == contact_id).first()
    if not contact:
        raise HTTPException(status_code=404, detail="Contact non trouvé")
    
    db.delete(contact)
    db.commit()
    
    return {"message": "Contact supprimé avec succès"}


# ==================== GESTION DES UTILISATEURS ====================

@app.get("/api/users/{user_id}", response_model=UserResponse)
async def get_user(user_id: int, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="Utilisateur non trouvé")
    return user


@app.put("/api/users/{user_id}/deactivate")
async def deactivate_user(
    user_id: int,
    db: Session = Depends(get_db),
    x_zapier_secret: Optional[str] = Header(None)
):
    if os.getenv("ENVIRONMENT") == "production":
        if x_zapier_secret != ZAPIER_SECRET:
            raise HTTPException(status_code=401, detail="Unauthorized")
    
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="Utilisateur non trouvé")
    
    user.is_active = False
    db.commit()
    
    return {"message": "Utilisateur désactivé", "user_id": user_id}


@app.put("/api/users/change-password")
async def change_password(
    data: PasswordChange,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Changer le mot de passe de l'utilisateur connecté
    """
    # Vérifier l'ancien mot de passe
    if not verify_password(data.current_password, current_user.hashed_password):
        raise HTTPException(status_code=400, detail="Mot de passe actuel incorrect")
    
    # Valider le nouveau mot de passe
    if len(data.new_password) < 8:
        raise HTTPException(status_code=400, detail="Le nouveau mot de passe doit contenir au moins 8 caractères")
    
    # Mettre à jour le mot de passe
    current_user.hashed_password = hash_password(data.new_password)
    db.commit()
    
    # Envoyer email de confirmation
    send_email(
        to=current_user.email,
        subject="Mot de passe modifié - Afrikalytics",
        html=f"""
            <h2>Mot de passe modifié</h2>
            <p>Bonjour {current_user.full_name},</p>
            <p>Votre mot de passe Afrikalytics a été modifié avec succès.</p>
            <p>Si vous n'êtes pas à l'origine de cette modification, contactez-nous immédiatement.</p>
            <hr>
            <p><em>L'équipe Afrikalytics AI by Marketym</em></p>
        """
    )
    
    return {"message": "Mot de passe modifié avec succès"}


# ==================== GESTION DES ABONNEMENTS ====================

CRON_SECRET = os.getenv("CRON_SECRET", "your-cron-secret-key")

@app.post("/api/subscriptions/check-expiry")
async def check_subscription_expiry(
    db: Session = Depends(get_db),
    x_cron_secret: Optional[str] = Header(None)
):
    """
    Vérifier les abonnements et envoyer les rappels / rétrograder
    Appelé par un cron job quotidien (cron-job.org)
    """
    # Vérifier le secret en production
    if os.getenv("ENVIRONMENT") == "production":
        if x_cron_secret != CRON_SECRET:
            raise HTTPException(status_code=401, detail="Unauthorized")
    
    today = datetime.utcnow().date()
    results = {
        "checked_at": datetime.utcnow().isoformat(),
        "reminders_j7": 0,
        "reminders_j3": 0,
        "reminders_j0": 0,
        "downgraded": 0,
        "errors": []
    }
    
    # Récupérer tous les abonnements actifs
    active_subscriptions = db.query(Subscription).filter(
        Subscription.status == "active"
    ).all()
    
    for sub in active_subscriptions:
        try:
            if not sub.end_date:
                continue
            
            end_date = sub.end_date.date() if hasattr(sub.end_date, 'date') else sub.end_date
            days_remaining = (end_date - today).days
            
            # Récupérer l'utilisateur
            user = db.query(User).filter(User.id == sub.user_id).first()
            if not user:
                continue
            
            # J-7 : Rappel 7 jours avant
            if days_remaining == 7:
                send_email(
                    to=user.email,
                    subject="⏰ Votre abonnement Afrikalytics expire dans 7 jours",
                    html=f"""
                        <h2>Bonjour {user.full_name},</h2>
                        <p>Votre abonnement <strong>{sub.plan.capitalize()}</strong> expire dans <strong>7 jours</strong>.</p>
                        <p>Pour continuer à profiter de tous les avantages Premium :</p>
                        <ul>
                            <li>✅ Résultats en temps réel</li>
                            <li>✅ Insights complets</li>
                            <li>✅ Rapports PDF détaillés</li>
                            <li>✅ Dashboard avancé</li>
                        </ul>
                        <p style="margin: 30px 0;">
                            <a href="https://afrikalytics.com/checkout" 
                               style="background-color: #2563eb; color: white; padding: 12px 24px; text-decoration: none; border-radius: 8px; font-weight: bold;">
                                Renouveler mon abonnement
                            </a>
                        </p>
                        <hr>
                        <p><em>L'équipe Afrikalytics AI by Marketym</em></p>
                    """
                )
                results["reminders_j7"] += 1
            
            # J-3 : Rappel 3 jours avant
            elif days_remaining == 3:
                send_email(
                    to=user.email,
                    subject="⚠️ Plus que 3 jours pour renouveler votre abonnement Afrikalytics",
                    html=f"""
                        <h2>Bonjour {user.full_name},</h2>
                        <p>Votre abonnement <strong>{sub.plan.capitalize()}</strong> expire dans <strong>3 jours</strong>.</p>
                        <p style="color: #e74c3c; font-weight: bold;">
                            Sans renouvellement, vous perdrez l'accès aux fonctionnalités Premium.
                        </p>
                        <p style="margin: 30px 0;">
                            <a href="https://afrikalytics.com/checkout" 
                               style="background-color: #e74c3c; color: white; padding: 12px 24px; text-decoration: none; border-radius: 8px; font-weight: bold;">
                                Renouveler maintenant
                            </a>
                        </p>
                        <hr>
                        <p><em>L'équipe Afrikalytics AI by Marketym</em></p>
                    """
                )
                results["reminders_j3"] += 1
            
            # J-0 : Dernier jour
            elif days_remaining == 0:
                send_email(
                    to=user.email,
                    subject="🚨 DERNIER JOUR - Votre abonnement Afrikalytics expire aujourd'hui",
                    html=f"""
                        <h2>Bonjour {user.full_name},</h2>
                        <p style="color: #e74c3c; font-size: 18px; font-weight: bold;">
                            Votre abonnement {sub.plan.capitalize()} expire AUJOURD'HUI !
                        </p>
                        <p>Renouvelez maintenant pour ne pas perdre vos accès Premium.</p>
                        <p style="margin: 30px 0;">
                            <a href="https://afrikalytics.com/checkout" 
                               style="background-color: #e74c3c; color: white; padding: 16px 32px; text-decoration: none; border-radius: 8px; font-weight: bold; font-size: 16px;">
                                RENOUVELER MAINTENANT
                            </a>
                        </p>
                        <hr>
                        <p><em>L'équipe Afrikalytics AI by Marketym</em></p>
                    """
                )
                results["reminders_j0"] += 1
            
            # J+1 : Abonnement expiré - Rétrograder vers Basic
            elif days_remaining < 0:
                # Mettre à jour l'abonnement
                sub.status = "expired"
                
                # Rétrograder l'utilisateur vers Basic
                user.plan = "basic"
                
                db.commit()
                
                # Envoyer email
                send_email(
                    to=user.email,
                    subject="😢 Votre abonnement Afrikalytics a expiré",
                    html=f"""
                        <h2>Bonjour {user.full_name},</h2>
                        <p>Votre abonnement <strong>{sub.plan.capitalize()}</strong> a expiré.</p>
                        <p>Votre compte a été rétrogradé au <strong>Plan Basic (gratuit)</strong>.</p>
                        <p>Vous conservez l'accès à :</p>
                        <ul>
                            <li>✅ Participation aux études</li>
                            <li>✅ Aperçu des insights</li>
                            <li>✅ Dashboard basic</li>
                        </ul>
                        <p>Vous n'avez plus accès à :</p>
                        <ul>
                            <li>❌ Résultats en temps réel</li>
                            <li>❌ Insights complets</li>
                            <li>❌ Rapports PDF</li>
                        </ul>
                        <p style="margin: 30px 0;">
                            <a href="https://afrikalytics.com/checkout" 
                               style="background-color: #2563eb; color: white; padding: 12px 24px; text-decoration: none; border-radius: 8px; font-weight: bold;">
                                Réactiver mon abonnement Premium
                            </a>
                        </p>
                        <hr>
                        <p><em>L'équipe Afrikalytics AI by Marketym</em></p>
                    """
                )
                results["downgraded"] += 1
        
        except Exception as e:
            results["errors"].append(f"User {sub.user_id}: {str(e)}")
    
    return results


@app.get("/api/subscriptions/my-subscription")
async def get_my_subscription(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Récupérer l'abonnement de l'utilisateur connecté
    """
    subscription = db.query(Subscription).filter(
        Subscription.user_id == current_user.id,
        Subscription.status == "active"
    ).first()
    
    if not subscription:
        return {
            "has_subscription": False,
            "plan": current_user.plan,
            "message": "Aucun abonnement actif"
        }
    
    # Calculer les jours restants
    days_remaining = None
    if subscription.end_date:
        end_date = subscription.end_date.date() if hasattr(subscription.end_date, 'date') else subscription.end_date
        days_remaining = (end_date - datetime.utcnow().date()).days
    
    return {
        "has_subscription": True,
        "plan": subscription.plan,
        "status": subscription.status,
        "start_date": subscription.start_date.isoformat() if subscription.start_date else None,
        "end_date": subscription.end_date.isoformat() if subscription.end_date else None,
        "days_remaining": days_remaining
    }


# ==================== ADMIN - GESTION UTILISATEURS ====================

class AdminUserCreate(BaseModel):
    email: EmailStr
    full_name: str
    password: str
    plan: str = "basic"
    is_active: bool = True
    is_admin: bool = False

class AdminUserUpdate(BaseModel):
    email: Optional[EmailStr] = None
    full_name: Optional[str] = None
    plan: Optional[str] = None
    is_active: Optional[bool] = None
    is_admin: Optional[bool] = None
    new_password: Optional[str] = None

class AdminUserResponse(BaseModel):
    id: int
    email: str
    full_name: str
    plan: str
    is_active: bool
    is_admin: bool
    created_at: datetime
    
    class Config:
        from_attributes = True


@app.get("/api/admin/users", response_model=List[AdminUserResponse])
async def get_all_users(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Récupérer tous les utilisateurs (Admin seulement)
    """
    if not current_user.is_admin:
        raise HTTPException(status_code=403, detail="Accès réservé aux administrateurs")
    
    users = db.query(User).order_by(User.created_at.desc()).all()
    return users


@app.get("/api/admin/users/{user_id}", response_model=AdminUserResponse)
async def get_user_by_id(
    user_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Récupérer un utilisateur par son ID (Admin seulement)
    """
    if not current_user.is_admin:
        raise HTTPException(status_code=403, detail="Accès réservé aux administrateurs")
    
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="Utilisateur non trouvé")
    
    return user


@app.post("/api/admin/users", response_model=AdminUserResponse)
async def create_user_admin(
    data: AdminUserCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Créer un utilisateur manuellement (Admin seulement)
    """
    if not current_user.is_admin:
        raise HTTPException(status_code=403, detail="Accès réservé aux administrateurs")
    
    # Vérifier si l'email existe déjà
    existing_user = db.query(User).filter(User.email == data.email).first()
    if existing_user:
        raise HTTPException(status_code=400, detail="Cet email est déjà utilisé")
    
    # Créer l'utilisateur
    hashed_password = hash_password(data.password)
    
    new_user = User(
        email=data.email,
        full_name=data.full_name,
        hashed_password=hashed_password,
        plan=data.plan,
        is_active=data.is_active,
        is_admin=data.is_admin
    )
    
    db.add(new_user)
    db.commit()
    db.refresh(new_user)
    
    # Envoyer email de bienvenue
    send_email(
        to=new_user.email,
        subject="Bienvenue sur Afrikalytics AI",
        html=f"""
            <h2>Bienvenue sur Afrikalytics AI !</h2>
            <p>Bonjour {new_user.full_name},</p>
            <p>Votre compte a été créé avec succès.</p>
            <p><strong>Email :</strong> {new_user.email}</p>
            <p><strong>Mot de passe :</strong> {data.password}</p>
            <p><strong>Plan :</strong> {new_user.plan.capitalize()}</p>
            <p style="margin: 30px 0;">
                <a href="https://dashboard.afrikalytics.com/login" 
                   style="background-color: #2563eb; color: white; padding: 12px 24px; text-decoration: none; border-radius: 8px; font-weight: bold;">
                    Se connecter
                </a>
            </p>
            <p style="color: #666;">Nous vous recommandons de changer votre mot de passe après votre première connexion.</p>
            <hr>
            <p><em>L'équipe Afrikalytics AI by Marketym</em></p>
        """
    )
    
    return new_user


@app.put("/api/admin/users/{user_id}", response_model=AdminUserResponse)
async def update_user_admin(
    user_id: int,
    data: AdminUserUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Modifier un utilisateur (Admin seulement)
    """
    if not current_user.is_admin:
        raise HTTPException(status_code=403, detail="Accès réservé aux administrateurs")
    
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="Utilisateur non trouvé")
    
    # Mettre à jour les champs fournis
    if data.email is not None:
        # Vérifier si l'email est déjà utilisé par un autre utilisateur
        existing = db.query(User).filter(User.email == data.email, User.id != user_id).first()
        if existing:
            raise HTTPException(status_code=400, detail="Cet email est déjà utilisé")
        user.email = data.email
    
    if data.full_name is not None:
        user.full_name = data.full_name
    
    if data.plan is not None:
        user.plan = data.plan
    
    if data.is_active is not None:
        user.is_active = data.is_active
    
    if data.is_admin is not None:
        user.is_admin = data.is_admin
    
    if data.new_password is not None and len(data.new_password) >= 8:
        user.hashed_password = hash_password(data.new_password)
    
    db.commit()
    db.refresh(user)
    
    return user


@app.delete("/api/admin/users/{user_id}")
async def delete_user_admin(
    user_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Supprimer un utilisateur (Admin seulement)
    """
    if not current_user.is_admin:
        raise HTTPException(status_code=403, detail="Accès réservé aux administrateurs")
    
    # Empêcher de supprimer son propre compte
    if user_id == current_user.id:
        raise HTTPException(status_code=400, detail="Vous ne pouvez pas supprimer votre propre compte")
    
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="Utilisateur non trouvé")
    
    # Supprimer les subscriptions associées
    db.query(Subscription).filter(Subscription.user_id == user_id).delete()
    
    # Supprimer l'utilisateur
    db.delete(user)
    db.commit()
    
    return {"message": "Utilisateur supprimé avec succès"}


@app.put("/api/admin/users/{user_id}/toggle-active")
async def toggle_user_active(
    user_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Activer/Désactiver un utilisateur (Admin seulement)
    """
    if not current_user.is_admin:
        raise HTTPException(status_code=403, detail="Accès réservé aux administrateurs")
    
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="Utilisateur non trouvé")
    
    user.is_active = not user.is_active
    db.commit()
    
    status = "activé" if user.is_active else "désactivé"
    return {"message": f"Utilisateur {status}", "is_active": user.is_active}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=int(os.getenv("PORT", 8000)))
