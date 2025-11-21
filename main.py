from fastapi import FastAPI, Depends, HTTPException, Header
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session
from pydantic import BaseModel, EmailStr
from typing import Optional
import secrets
import os
from datetime import datetime, timedelta

from database import get_db, engine
from models import Base, User
from auth import hash_password, verify_password, create_access_token

# Créer les tables
Base.metadata.create_all(bind=engine)

app = FastAPI(
    title="Afrikalytics API",
    description="Backend API pour Afrikalytics AI - Intelligence d'Affaires pour l'Afrique",
    version="1.0.0"
)

# CORS - Permettre les requêtes depuis le frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "https://afrikalytics-website.vercel.app",
        "https://dashboard.afrikalytics.com",
        "http://localhost:3000",
        "*"  # Pour le développement
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

class UserLogin(BaseModel):
    email: EmailStr
    password: str

class UserResponse(BaseModel):
    id: int
    email: str
    full_name: str
    plan: str
    is_active: bool
    created_at: datetime

    class Config:
        from_attributes = True

class TokenResponse(BaseModel):
    access_token: str
    token_type: str
    user: UserResponse

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


# ==================== ZAPIER WEBHOOK ====================
# Cette route est appelée par Zapier après un paiement WooCommerce

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
    # Vérifier le secret Zapier (optionnel en dev)
    if os.getenv("ENVIRONMENT") == "production":
        if x_zapier_secret != ZAPIER_SECRET:
            raise HTTPException(status_code=401, detail="Unauthorized")
    
    # Vérifier si l'utilisateur existe déjà
    existing_user = db.query(User).filter(User.email == data.email).first()
    if existing_user:
        # Mettre à jour le plan si l'utilisateur existe
        existing_user.plan = data.plan
        existing_user.is_active = True
        db.commit()
        return {
            "message": "User updated",
            "user_id": existing_user.id,
            "email": existing_user.email,
            "dashboard_url": "https://dashboard.afrikalytics.com"
        }
    
    # Générer un mot de passe temporaire
    temp_password = secrets.token_urlsafe(12)
    hashed_password = hash_password(temp_password)
    
    # Créer le nouvel utilisateur
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
        "temp_password": temp_password,  # À envoyer par email via Zapier
        "dashboard_url": "https://dashboard.afrikalytics.com"
    }


# ==================== AUTHENTIFICATION ====================

@app.post("/api/auth/login", response_model=TokenResponse)
async def login(data: UserLogin, db: Session = Depends(get_db)):
    """
    Connexion utilisateur
    """
    user = db.query(User).filter(User.email == data.email).first()
    
    if not user or not verify_password(data.password, user.hashed_password):
        raise HTTPException(status_code=401, detail="Email ou mot de passe incorrect")
    
    if not user.is_active:
        raise HTTPException(status_code=403, detail="Compte désactivé")
    
    # Créer le token JWT
    access_token = create_access_token(data={"sub": user.email, "user_id": user.id})
    
    return {
        "access_token": access_token,
        "token_type": "bearer",
        "user": user
    }


@app.get("/api/users/me", response_model=UserResponse)
async def get_current_user(
    db: Session = Depends(get_db),
    authorization: str = Header(None)
):
    """
    Récupérer les infos de l'utilisateur connecté
    """
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Token manquant")
    
    token = authorization.replace("Bearer ", "")
    
    from auth import decode_access_token
    payload = decode_access_token(token)
    
    if not payload:
        raise HTTPException(status_code=401, detail="Token invalide")
    
    user = db.query(User).filter(User.email == payload.get("sub")).first()
    
    if not user:
        raise HTTPException(status_code=404, detail="Utilisateur non trouvé")
    
    return user


# ==================== GESTION DES UTILISATEURS ====================

@app.get("/api/users/{user_id}", response_model=UserResponse)
async def get_user(user_id: int, db: Session = Depends(get_db)):
    """
    Récupérer un utilisateur par son ID
    """
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
    """
    Désactiver un utilisateur (appelé par Zapier si paiement échoué)
    """
    if os.getenv("ENVIRONMENT") == "production":
        if x_zapier_secret != ZAPIER_SECRET:
            raise HTTPException(status_code=401, detail="Unauthorized")
    
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="Utilisateur non trouvé")
    
    user.is_active = False
    db.commit()
    
    return {"message": "Utilisateur désactivé", "user_id": user_id}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=int(os.getenv("PORT", 8000)))
