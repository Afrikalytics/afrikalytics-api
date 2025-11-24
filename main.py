from fastapi import FastAPI, Depends, HTTPException, Header
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session
from pydantic import BaseModel, EmailStr
from typing import Optional, List
import secrets
import os
from datetime import datetime, timedelta

from database import get_db, engine
from models import Base, User, Study
from auth import hash_password, verify_password, create_access_token, decode_access_token

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
    is_active: bool
    created_at: datetime

    class Config:
        from_attributes = True

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

@app.post("/api/auth/login", response_model=TokenResponse)
async def login(data: UserLogin, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.email == data.email).first()
    
    if not user or not verify_password(data.password, user.hashed_password):
        raise HTTPException(status_code=401, detail="Email ou mot de passe incorrect")
    
    if not user.is_active:
        raise HTTPException(status_code=403, detail="Compte désactivé")
    
    access_token = create_access_token(data={"sub": user.email, "user_id": user.id})
    
    return {
        "access_token": access_token,
        "token_type": "bearer",
        "user": user
    }


@app.get("/api/users/me", response_model=UserResponse)
async def get_current_user_info(current_user: User = Depends(get_current_user)):
    return current_user


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


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=int(os.getenv("PORT", 8000)))
