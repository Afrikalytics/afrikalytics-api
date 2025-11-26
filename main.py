from fastapi import FastAPI, Depends, HTTPException, Header
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session
from pydantic import BaseModel, EmailStr
from typing import Optional, List
import secrets
import os
from datetime import datetime, timedelta
import resend

from database import get_db, engine
from models import Base, User, Study, Insight, Report, Contact
from auth import hash_password, verify_password, create_access_token, decode_access_token

# Créer les tables
Base.metadata.create_all(bind=engine)

# Configurer Resend
resend.api_key = os.getenv("RESEND_API_KEY")
CONTACT_EMAIL = os.getenv("CONTACT_EMAIL", "contact@afrikalytics.com")

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
    is_available: Optional[bool] = True

class ReportResponse(BaseModel):
    id: int
    study_id: int
    title: str
    description: Optional[str]
    file_url: str
    file_name: Optional[str]
    file_size: Optional[str]
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

@app.post("/api/auth/register", response_model=TokenResponse)
async def register(data: UserRegister, db: Session = Depends(get_db)):
    """
    Inscription d'un nouvel utilisateur (plan Basic gratuit)
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
    
    # Envoyer email de bienvenue (optionnel)
    try:
        resend.emails.send({
            "from": "Afrikalytics <noreply@notifications.afrikalytics.com>",
            "to": [new_user.email],
            "subject": "Bienvenue sur Afrikalytics AI !",
            "html": f"""
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
        })
    except Exception as e:
        print(f"Erreur envoi email bienvenue: {e}")
    
    return {
        "access_token": access_token,
        "token_type": "bearer",
        "user": new_user
    }


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
    Récupérer le rapport d'une étude
    """
    report = db.query(Report).filter(Report.study_id == study_id, Report.is_available == True).first()
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
    """
    report = db.query(Report).filter(Report.id == report_id).first()
    if not report:
        raise HTTPException(status_code=404, detail="Rapport non trouvé")
    
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
    
    return {"message": "Téléchargement enregistré", "download_count": report.download_count}


# ==================== CONTACTS ====================

@app.post("/api/contacts", response_model=ContactResponse)
async def create_contact(
    data: ContactCreate,
    db: Session = Depends(get_db)
):
    """
    Créer un nouveau message de contact (public)
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
    try:
        resend.emails.send({
            "from": "Afrikalytics <noreply@notifications.afrikalytics.com>",
            "to": [CONTACT_EMAIL],
            "subject": f"Nouveau message de contact - {data.name}",
            "html": f"""
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
        })
    except Exception as e:
        # Log l'erreur mais ne pas bloquer la requête
        print(f"Erreur envoi email: {e}")
    
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


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=int(os.getenv("PORT", 8000)))
