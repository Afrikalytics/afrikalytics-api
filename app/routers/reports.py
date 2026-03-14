from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import update
from sqlalchemy.orm import Session
from typing import List

from database import get_db
from models import Report, Study, User
from app.dependencies import get_current_user
from app.permissions import check_admin_permission, check_content_access
from app.schemas.reports import ReportCreate, ReportResponse

router = APIRouter()


@router.get("/api/reports", response_model=List[ReportResponse])
async def get_all_reports(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    reports = (
        db.query(Report)
        .filter(Report.is_available == True)
        .order_by(Report.created_at.desc())
        .all()
    )
    return reports


@router.get("/api/reports/study/{study_id}", response_model=ReportResponse)
async def get_report_by_study(study_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    report = (
        db.query(Report)
        .filter(Report.study_id == study_id, Report.is_available == True)
        .first()
    )
    if not report:
        raise HTTPException(status_code=404, detail="Rapport non trouvé")
    return report


@router.get("/api/reports/study/{study_id}/type/{report_type}", response_model=ReportResponse)
async def get_report_by_study_and_type(
    study_id: int, report_type: str, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)
):
    report = (
        db.query(Report)
        .filter(
            Report.study_id == study_id,
            Report.report_type == report_type,
            Report.is_available == True,
        )
        .first()
    )
    if not report:
        raise HTTPException(status_code=404, detail="Rapport non trouvé")
    return report


@router.get("/api/reports/{report_id}", response_model=ReportResponse)
async def get_report(report_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    report = db.query(Report).filter(Report.id == report_id).first()
    if not report:
        raise HTTPException(status_code=404, detail="Rapport non trouvé")
    # Unavailable reports are only accessible to admins
    if not report.is_available and not current_user.is_admin:
        raise HTTPException(status_code=404, detail="Rapport non trouvé")
    # Plan-based access control: basic users cannot access premium reports
    check_content_access(current_user, report_type=report.report_type)
    return report


@router.post("/api/reports", response_model=ReportResponse, status_code=201)
async def create_report(
    data: ReportCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if not check_admin_permission(current_user, "reports"):
        raise HTTPException(status_code=403, detail="Vous n'avez pas la permission de gérer les rapports")

    new_report = Report(
        study_id=data.study_id,
        title=data.title,
        description=data.description,
        file_url=data.file_url,
        file_name=data.file_name,
        file_size=data.file_size,
        report_type=data.report_type,
        is_available=data.is_available,
    )
    db.add(new_report)
    db.commit()
    db.refresh(new_report)
    return new_report


@router.put("/api/reports/{report_id}", response_model=ReportResponse)
async def update_report(
    report_id: int,
    data: ReportCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if not check_admin_permission(current_user, "reports"):
        raise HTTPException(status_code=403, detail="Vous n'avez pas la permission de gérer les rapports")

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


@router.delete("/api/reports/{report_id}")
async def delete_report(
    report_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if not check_admin_permission(current_user, "reports"):
        raise HTTPException(status_code=403, detail="Vous n'avez pas la permission de gérer les rapports")

    report = db.query(Report).filter(Report.id == report_id).first()
    if not report:
        raise HTTPException(status_code=404, detail="Rapport non trouvé")

    if report.study_id:
        study = db.query(Study).filter(Study.id == report.study_id).first()
        if study:
            if report.report_type == "basic":
                study.report_url_basic = None
            elif report.report_type == "premium":
                study.report_url_premium = None
            else:
                study.report_url_basic = None
                study.report_url_premium = None

    db.delete(report)
    db.commit()
    return {"message": "Rapport supprimé avec succès"}


@router.post("/api/reports/{report_id}/download")
async def track_download(report_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    report = db.query(Report).filter(Report.id == report_id).first()
    if not report:
        raise HTTPException(status_code=404, detail="Rapport non trouvé")

    # Atomic increment to avoid race conditions
    db.execute(
        update(Report)
        .where(Report.id == report_id)
        .values(download_count=Report.download_count + 1)
    )
    db.commit()
    db.refresh(report)

    return {
        "message": "Téléchargement enregistré",
        "download_count": report.download_count,
        "file_url": report.file_url,
    }


@router.post("/api/reports/study/{study_id}/type/{report_type}/download")
async def track_download_by_type(
    study_id: int, report_type: str, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)
):
    report = (
        db.query(Report)
        .filter(
            Report.study_id == study_id,
            Report.report_type == report_type,
            Report.is_available == True,
        )
        .first()
    )
    if not report:
        raise HTTPException(status_code=404, detail="Rapport non trouvé")

    # Atomic increment to avoid race conditions
    db.execute(
        update(Report)
        .where(Report.id == report.id)
        .values(download_count=Report.download_count + 1)
    )
    db.commit()
    db.refresh(report)

    return {
        "message": "Téléchargement enregistré",
        "download_count": report.download_count,
        "file_url": report.file_url,
    }
