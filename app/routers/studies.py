"""
Router pour les études de marché (CRUD + import CSV/Excel).
8 endpoints : liste complète, actives, détail, création, mise à jour, suppression, import, preview.
"""
import logging
from typing import List

from fastapi import APIRouter, Depends, Form, HTTPException, Query, Request, UploadFile, File
from sqlalchemy import select
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

from app.database import get_db
from app.models import User, Study
from app.dependencies import get_current_user
from app.permissions import check_admin_permission
from app.schemas.studies import StudyCreate, StudyUpdate, StudyResponse
from app.schemas.imports import ImportResponse, ImportValidationResult, ImportPreviewResponse
from app.services.audit import log_action
from app.services.cache import cache_get, cache_set, cache_delete_pattern
from app.services.import_service import (
    validate_file,
    parse_file,
    ImportError as FileImportError,
)
from app.rate_limit import limiter

router = APIRouter()


@router.get("/api/studies", response_model=List[StudyResponse])
@limiter.limit("30/minute")
async def get_all_studies(
    request: Request,
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Récupérer toutes les études, triées par date de création décroissante.
    Supporte la pagination via skip/limit.
    """
    studies = db.execute(
        select(Study).order_by(Study.created_at.desc()).offset(skip).limit(limit)
    ).scalars().all()
    return studies


@router.get("/api/studies/active", response_model=List[StudyResponse])
@limiter.limit("30/minute")
async def get_active_studies(request: Request, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    """
    Récupérer les études actives (is_active=True) pour le site public.
    """
    # Check cache
    cached = cache_get("studies:active")
    if cached:
        return cached

    studies = db.execute(
        select(Study)
        .where(Study.is_active.is_(True))
        .order_by(Study.created_at.desc())
    ).scalars().all()

    result = [StudyResponse.from_orm(s).model_dump() for s in studies]
    cache_set("studies:active", result, ttl=300)
    return result


@router.get("/api/studies/{study_id}", response_model=StudyResponse)
@limiter.limit("30/minute")
async def get_study(request: Request, study_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    """
    Récupérer une étude par son ID.
    """
    study = db.execute(
        select(Study).where(Study.id == study_id)
    ).scalar_one_or_none()
    if not study:
        raise HTTPException(status_code=404, detail="Étude non trouvée")
    return study


@router.post("/api/studies", response_model=StudyResponse, status_code=201)
@limiter.limit("10/minute")
async def create_study(
    data: StudyCreate,
    request: Request,
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

    # Invalidate studies cache on mutation
    cache_delete_pattern("studies:*")
    cache_delete_pattern("dashboard:*")

    # Audit log
    try:
        log_action(
            db=db, user_id=current_user.id, action="create", resource_type="study",
            resource_id=new_study.id, details={"title": new_study.title},
            request=request,
        )
    except Exception as e:
        logger.warning(f"Audit log failed: {e}")

    return new_study


@router.put("/api/studies/{study_id}", response_model=StudyResponse)
@limiter.limit("10/minute")
async def update_study(
    study_id: int,
    data: StudyUpdate,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Modifier une étude existante (Admin avec permission studies).
    Seuls les champs fournis sont mis à jour (partial update).
    """
    if not check_admin_permission(current_user, "studies"):
        raise HTTPException(
            status_code=403,
            detail="Vous n'avez pas la permission de gérer les études",
        )

    study = db.execute(
        select(Study).where(Study.id == study_id)
    ).scalar_one_or_none()
    if not study:
        raise HTTPException(status_code=404, detail="Étude non trouvée")

    update_data = data.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(study, key, value)

    db.commit()
    db.refresh(study)

    # Invalidate studies cache on mutation
    cache_delete_pattern("studies:*")
    cache_delete_pattern("dashboard:*")

    # Audit log
    try:
        log_action(
            db=db, user_id=current_user.id, action="update", resource_type="study",
            resource_id=study_id, details={"title": study.title},
            request=request,
        )
    except Exception as e:
        logger.warning(f"Audit log failed: {e}")

    return study


@router.delete("/api/studies/{study_id}")
@limiter.limit("5/minute")
async def delete_study(
    study_id: int,
    request: Request,
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

    study = db.execute(
        select(Study).where(Study.id == study_id)
    ).scalar_one_or_none()
    if not study:
        raise HTTPException(status_code=404, detail="Étude non trouvée")

    deleted_title = study.title

    # Audit log BEFORE deletion
    try:
        log_action(
            db=db, user_id=current_user.id, action="delete", resource_type="study",
            resource_id=study_id, details={"deleted_title": deleted_title},
            request=request,
        )
    except Exception as e:
        logger.warning(f"Audit log failed: {e}")

    db.delete(study)
    db.commit()

    # Invalidate studies cache on mutation
    cache_delete_pattern("studies:*")
    cache_delete_pattern("dashboard:*")

    return {"message": "Étude supprimée avec succès"}


# ================================================================
# IMPORT CSV/Excel
# ================================================================


@router.post("/api/studies/import/preview", response_model=ImportPreviewResponse)
@limiter.limit("10/minute")
async def preview_import(
    request: Request,
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
):
    """
    Prévisualiser un fichier CSV/Excel avant import.
    Retourne les colonnes détectées et les 5 premières lignes.
    Ne crée PAS d'étude.
    """
    if not check_admin_permission(current_user, "studies"):
        raise HTTPException(
            status_code=403,
            detail="Vous n'avez pas la permission de gérer les études",
        )

    content = await file.read()
    file_size = len(content)

    try:
        await validate_file(file.filename or "unknown", file_size)
    except FileImportError as e:
        raise HTTPException(status_code=400, detail=e.message)

    try:
        result = await parse_file(content, file.filename or "unknown")
    except FileImportError as e:
        raise HTTPException(status_code=400, detail=e.message)

    return ImportPreviewResponse(
        filename=file.filename or "unknown",
        file_size=file_size,
        result=ImportValidationResult(
            total_rows=result.total_rows,
            imported_rows=result.imported_rows,
            skipped_rows=result.skipped_rows,
            columns=result.columns,
            preview=result.preview,
            errors=result.errors,
        ),
    )


@router.post("/api/studies/import", response_model=ImportResponse, status_code=201)
@limiter.limit("5/minute")
async def import_study_data(
    request: Request,
    file: UploadFile = File(...),
    title: str = Form(..., max_length=200),
    description: str = Form("", max_length=5000),
    category: str = Form("general", max_length=100),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Importer des données CSV/Excel pour créer une nouvelle étude.
    Les données sont stockées en JSONB dans le champ imported_data de l'étude.
    """
    if not check_admin_permission(current_user, "studies"):
        raise HTTPException(
            status_code=403,
            detail="Vous n'avez pas la permission de gérer les études",
        )

    content = await file.read()
    file_size = len(content)

    try:
        await validate_file(file.filename or "unknown", file_size)
    except FileImportError as e:
        raise HTTPException(status_code=400, detail=e.message)

    try:
        result = await parse_file(content, file.filename or "unknown")
    except FileImportError as e:
        raise HTTPException(status_code=400, detail=e.message)

    if result.imported_rows == 0:
        raise HTTPException(
            status_code=400,
            detail="Aucune donnée importée. Le fichier est vide ou invalide.",
        )

    new_study = Study(
        title=title,
        description=description if description else None,
        category=category,
        status="Ouvert",
        is_active=True,
        imported_data=result.data,
        imported_columns=result.columns,
        imported_row_count=result.imported_rows,
        import_source=file.filename,
    )

    db.add(new_study)
    db.commit()
    db.refresh(new_study)

    cache_delete_pattern("studies:*")
    cache_delete_pattern("dashboard:*")

    try:
        log_action(
            db=db,
            user_id=current_user.id,
            action="import",
            resource_type="study",
            resource_id=new_study.id,
            details={
                "title": new_study.title,
                "source_file": file.filename,
                "rows_imported": result.imported_rows,
                "columns": result.columns,
            },
            request=request,
        )
    except Exception as e:
        logger.warning(f"Audit log failed: {e}")

    logger.info(
        f"Study #{new_study.id} created via import: "
        f"{result.imported_rows} rows from '{file.filename}'"
    )

    return ImportResponse(
        study_id=new_study.id,
        message=f"Import réussi : {result.imported_rows} lignes importées depuis '{file.filename}'",
        result=ImportValidationResult(
            total_rows=result.total_rows,
            imported_rows=result.imported_rows,
            skipped_rows=result.skipped_rows,
            columns=result.columns,
            preview=result.preview,
            errors=result.errors,
        ),
    )
