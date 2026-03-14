"""
Router pour les études de marché (CRUD).
6 endpoints : liste complète, actives, détail, création, mise à jour, suppression.
"""
from typing import List

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from database import get_db
from models import User, Study
from app.dependencies import get_current_user
from app.permissions import check_admin_permission
from app.schemas.studies import StudyCreate, StudyResponse

router = APIRouter()


@router.get("/api/studies", response_model=List[StudyResponse])
async def get_all_studies(
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Récupérer toutes les études, triées par date de création décroissante.
    Supporte la pagination via skip/limit.
    """
    studies = db.query(Study).order_by(Study.created_at.desc()).offset(skip).limit(limit).all()
    return studies


@router.get("/api/studies/active", response_model=List[StudyResponse])
async def get_active_studies(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    """
    Récupérer les études actives (is_active=True) pour le site public.
    """
    studies = (
        db.query(Study)
        .filter(Study.is_active == True)
        .order_by(Study.created_at.desc())
        .all()
    )
    return studies


@router.get("/api/studies/{study_id}", response_model=StudyResponse)
async def get_study(study_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    """
    Récupérer une étude par son ID.
    """
    study = db.query(Study).filter(Study.id == study_id).first()
    if not study:
        raise HTTPException(status_code=404, detail="Étude non trouvée")
    return study


@router.post("/api/studies", response_model=StudyResponse, status_code=201)
async def create_study(
    data: StudyCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Créer une nouvelle étude (Admin avec permission studies).
    """
    if not check_admin_permission(current_user, "studies"):
        raise HTTPException(
            status_code=403,
            detail="Vous n'avez pas la permission de gérer les études",
        )

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
        is_active=data.is_active,
    )

    db.add(new_study)
    db.commit()
    db.refresh(new_study)

    return new_study


@router.put("/api/studies/{study_id}", response_model=StudyResponse)
async def update_study(
    study_id: int,
    data: StudyCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Modifier une étude existante (Admin avec permission studies).
    """
    if not check_admin_permission(current_user, "studies"):
        raise HTTPException(
            status_code=403,
            detail="Vous n'avez pas la permission de gérer les études",
        )

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


@router.delete("/api/studies/{study_id}")
async def delete_study(
    study_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Supprimer une étude (Admin avec permission studies).
    """
    if not check_admin_permission(current_user, "studies"):
        raise HTTPException(
            status_code=403,
            detail="Vous n'avez pas la permission de gérer les études",
        )

    study = db.query(Study).filter(Study.id == study_id).first()
    if not study:
        raise HTTPException(status_code=404, detail="Étude non trouvée")

    db.delete(study)
    db.commit()

    return {"message": "Étude supprimée avec succès"}
