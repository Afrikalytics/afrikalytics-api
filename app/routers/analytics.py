"""
Router pour l'analyse statistique et la détection d'anomalies.
2 endpoints : analyse complète d'une étude, détection d'anomalies.
"""
import logging

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import get_current_user
from app.models import User, Study
from app.rate_limit import limiter
from app.schemas.analytics import (
    AnalysisResponse,
    AnomaliesResponse,
    AnomalyResult,
    AnomalySummary,
)
from app.services.analytics_service import analyze_dataset
from app.services.anomaly_detection import detect_anomalies

logger = logging.getLogger(__name__)

router = APIRouter()


def _get_study_with_data(study_id: int, db: Session, current_user: User) -> Study:
    """Helper : récupère une étude et vérifie qu'elle a des données importées."""
    study = db.execute(
        select(Study).where(Study.id == study_id)
    ).scalar_one_or_none()

    if not study:
        raise HTTPException(status_code=404, detail="Étude non trouvée.")

    if not study.dataset or not study.dataset.data or not study.dataset.columns:
        raise HTTPException(
            status_code=400,
            detail="Cette étude n'a pas de données importées. Importez un fichier CSV/Excel d'abord.",
        )

    return study


@router.post("/api/studies/{study_id}/analyze", response_model=AnalysisResponse)
@limiter.limit("10/minute")
def analyze_study(
    study_id: int,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Lance une analyse statistique complète sur les données importées d'une étude.

    Retourne :
    - Statistiques descriptives par colonne numérique (moyenne, médiane, écart-type, etc.)
    - Tendances détectées (hausse/baisse)
    - Corrélations significatives entre colonnes
    - KPIs calculés automatiquement
    - Insights textuels en français
    """
    study = _get_study_with_data(study_id, db, current_user)

    logger.info(
        "Analyse statistique demandée pour l'étude %d (%s) par l'utilisateur %d",
        study.id, study.title, current_user.id,
    )

    result = analyze_dataset(study.dataset.data, study.dataset.columns)

    return AnalysisResponse(
        summary=result.summary,
        trends=result.trends,
        correlations=result.correlations,
        insights=result.insights,
        kpis=result.kpis,
    )


@router.get("/api/studies/{study_id}/anomalies", response_model=AnomaliesResponse)
@limiter.limit("10/minute")
def detect_study_anomalies(
    study_id: int,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Détecte les anomalies (valeurs aberrantes) dans les données importées d'une étude.

    Utilise deux méthodes complémentaires :
    - **Z-score** : valeurs éloignées de la moyenne (warning si 2 < z < 3, critical si z > 3)
    - **IQR** : valeurs en dehors de [Q1 - 1.5×IQR, Q3 + 1.5×IQR]

    Retourne la liste des anomalies avec leur sévérité et une explication en français.
    """
    study = _get_study_with_data(study_id, db, current_user)

    logger.info(
        "Détection d'anomalies demandée pour l'étude %d (%s) par l'utilisateur %d",
        study.id, study.title, current_user.id,
    )

    detection_result = detect_anomalies(study.dataset.data, study.dataset.columns)

    anomalies = [
        AnomalyResult(
            row_index=a.row_index,
            column=a.column,
            value=a.value,
            expected_range=a.expected_range,
            anomaly_type=a.anomaly_type,
            severity=a.severity,
            explanation=a.explanation,
        )
        for a in detection_result.anomalies
    ]

    summary = AnomalySummary(**detection_result.summary)

    return AnomaliesResponse(anomalies=anomalies, summary=summary)
