"""
Router d'export — /api/exports/*

Endpoints pour exporter les études, insights et rapports en PDF, Excel ou CSV.
Accès contrôlé par plan : PDF réservé aux plans professionnel et entreprise.
"""

import logging

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import get_current_user
from app.models import Insight, Report, Study, StudyDataset, User
from app.rate_limit import limiter
from app.services.export_service import (
    export_study_csv,
    export_study_pdf,
    export_study_xlsx,
    get_content_type,
    get_file_extension,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/exports", tags=["exports"])


def _check_export_permission(user: User, fmt: str) -> None:
    """Raise 403 if the user's plan doesn't allow this export format."""
    if fmt == "pdf" and user.plan == "basic":
        raise HTTPException(
            status_code=403,
            detail="L'export PDF est réservé aux plans Professionnel et Entreprise.",
        )


@router.get("/studies/{study_id}")
@limiter.limit("10/minute")
def export_study(
    request: Request,
    study_id: int,
    fmt: str = Query("pdf", alias="format", pattern="^(pdf|xlsx|csv)$"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Export study data as PDF, Excel, or CSV."""
    _check_export_permission(current_user, fmt)

    study = db.execute(
        select(Study).where(Study.id == study_id, Study.deleted_at.is_(None))
    ).scalar_one_or_none()
    if not study:
        raise HTTPException(status_code=404, detail="Étude non trouvée")

    # Get dataset
    dataset = db.execute(
        select(StudyDataset).where(StudyDataset.study_id == study_id)
    ).scalar_one_or_none()

    data = dataset.data if dataset and dataset.data else []
    columns = dataset.columns if dataset and dataset.columns else []

    # Generate export
    if fmt == "pdf":
        content = export_study_pdf(study.title, data, columns)
    elif fmt == "xlsx":
        content = export_study_xlsx(study.title, data, columns)
    else:
        content = export_study_csv(data, columns)

    filename = f"afrikalytics-{study.title[:30].replace(' ', '_')}.{get_file_extension(fmt)}"

    return Response(
        content=content,
        media_type=get_content_type(fmt),
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/insights/{insight_id}")
@limiter.limit("10/minute")
def export_insight(
    request: Request,
    insight_id: int,
    fmt: str = Query("pdf", alias="format", pattern="^(pdf|xlsx|csv)$"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Export insight data as PDF, Excel, or CSV."""
    _check_export_permission(current_user, fmt)

    insight = db.execute(
        select(Insight).where(Insight.id == insight_id, Insight.deleted_at.is_(None))
    ).scalar_one_or_none()
    if not insight:
        raise HTTPException(status_code=404, detail="Insight non trouvé")

    # Build export data from insight fields
    data = [
        {"champ": "Titre", "valeur": insight.title},
        {"champ": "Résumé", "valeur": insight.summary or ""},
        {"champ": "Publié", "valeur": "Oui" if insight.is_published else "Non"},
    ]
    # Add key_findings if available
    if insight.key_findings:
        for i, finding in enumerate(insight.key_findings, 1):
            data.append({"champ": f"Résultat clé {i}", "valeur": str(finding)})

    columns = ["champ", "valeur"]

    if fmt == "pdf":
        content = export_study_pdf(f"Insight — {insight.title}", data, columns)
    elif fmt == "xlsx":
        content = export_study_xlsx(f"Insight — {insight.title}", data, columns)
    else:
        content = export_study_csv(data, columns)

    filename = f"afrikalytics-insight-{insight.id}.{get_file_extension(fmt)}"

    return Response(
        content=content,
        media_type=get_content_type(fmt),
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
