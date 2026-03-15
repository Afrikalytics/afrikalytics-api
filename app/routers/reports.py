import logging

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import select, update
from sqlalchemy.orm import Session
logger = logging.getLogger(__name__)

from app.database import get_db
from app.middleware.tenant import get_tenant_db
from app.models import Report, Study, User
from app.dependencies import get_current_user
from app.pagination import PaginationParams, paginate
from app.permissions import check_admin_permission, check_content_access
from app.schemas.reports import ReportCreate, ReportUpdate, ReportResponse
from app.services.audit import log_action
from app.rate_limit import limiter

router = APIRouter()


@router.get("/api/reports")
@limiter.limit("30/minute")
def get_all_reports(
    request: Request,
    pagination: PaginationParams = Depends(),
    db: Session = Depends(get_tenant_db),
    current_user: User = Depends(get_current_user),
):
    stmt = (
        select(Report)
        .where(Report.is_available.is_(True))
        .order_by(Report.created_at.desc())
    )
    return paginate(db, stmt, pagination)


@router.get("/api/reports/study/{study_id}", response_model=ReportResponse)
@limiter.limit("30/minute")
def get_report_by_study(request: Request, study_id: int, db: Session = Depends(get_tenant_db), current_user: User = Depends(get_current_user)):
    report = db.execute(
        select(Report)
        .where(Report.study_id == study_id, Report.is_available.is_(True))
    ).scalar_one_or_none()
    if not report:
        raise HTTPException(status_code=404, detail="Rapport non trouvé")
    check_content_access(current_user, report_type=report.report_type)
    return report


@router.get("/api/reports/study/{study_id}/type/{report_type}", response_model=ReportResponse)
@limiter.limit("30/minute")
def get_report_by_study_and_type(
    request: Request, study_id: int, report_type: str, db: Session = Depends(get_tenant_db), current_user: User = Depends(get_current_user)
):
    report = db.execute(
        select(Report)
        .where(
            Report.study_id == study_id,
            Report.report_type == report_type,
            Report.is_available.is_(True),
        )
    ).scalar_one_or_none()
    if not report:
        raise HTTPException(status_code=404, detail="Rapport non trouvé")
    check_content_access(current_user, report_type=report.report_type)
    return report


@router.get("/api/reports/{report_id}", response_model=ReportResponse)
@limiter.limit("30/minute")
def get_report(request: Request, report_id: int, db: Session = Depends(get_tenant_db), current_user: User = Depends(get_current_user)):
    report = db.execute(
        select(Report).where(Report.id == report_id)
    ).scalar_one_or_none()
    if not report:
        raise HTTPException(status_code=404, detail="Rapport non trouvé")
    # Unavailable reports are only accessible to admins
    if not report.is_available and not current_user.is_admin:
        raise HTTPException(status_code=404, detail="Rapport non trouvé")
    # Plan-based access control: basic users cannot access premium reports
    check_content_access(current_user, report_type=report.report_type)
    return report


@router.post("/api/reports", response_model=ReportResponse, status_code=201)
@limiter.limit("10/minute")
def create_report(
    data: ReportCreate,
    request: Request,
    db: Session = Depends(get_tenant_db),
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

    # Audit log
    try:
        log_action(
            db=db, user_id=current_user.id, action="create", resource_type="report",
            resource_id=new_report.id, details={"title": new_report.title, "report_type": new_report.report_type},
            request=request,
        )
    except Exception as e:
        logger.warning(f"Audit log failed: {e}")

    return new_report


@router.put("/api/reports/{report_id}", response_model=ReportResponse)
@limiter.limit("10/minute")
def update_report(
    report_id: int,
    data: ReportUpdate,
    request: Request,
    db: Session = Depends(get_tenant_db),
    current_user: User = Depends(get_current_user),
):
    if not check_admin_permission(current_user, "reports"):
        raise HTTPException(status_code=403, detail="Vous n'avez pas la permission de gérer les rapports")

    report = db.execute(
        select(Report).where(Report.id == report_id)
    ).scalar_one_or_none()
    if not report:
        raise HTTPException(status_code=404, detail="Rapport non trouvé")

    update_data = data.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(report, key, value)

    db.commit()
    db.refresh(report)

    # Audit log
    try:
        log_action(
            db=db, user_id=current_user.id, action="update", resource_type="report",
            resource_id=report_id, details={"title": report.title},
            request=request,
        )
    except Exception as e:
        logger.warning(f"Audit log failed: {e}")

    return report


@router.delete("/api/reports/{report_id}")
@limiter.limit("5/minute")
def delete_report(
    report_id: int,
    request: Request,
    db: Session = Depends(get_tenant_db),
    current_user: User = Depends(get_current_user),
):
    if not check_admin_permission(current_user, "reports"):
        raise HTTPException(status_code=403, detail="Vous n'avez pas la permission de gérer les rapports")

    report = db.execute(
        select(Report).where(Report.id == report_id)
    ).scalar_one_or_none()
    if not report:
        raise HTTPException(status_code=404, detail="Rapport non trouvé")

    # Audit log BEFORE deletion
    try:
        log_action(
            db=db, user_id=current_user.id, action="delete", resource_type="report",
            resource_id=report_id, details={"deleted_title": report.title},
            request=request,
        )
    except Exception as e:
        logger.warning(f"Audit log failed: {e}")

    if report.study_id:
        study = db.execute(
            select(Study).where(Study.id == report.study_id)
        ).scalar_one_or_none()
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
@limiter.limit("10/minute")
def track_download(request: Request, report_id: int, db: Session = Depends(get_tenant_db), current_user: User = Depends(get_current_user)):
    report = db.execute(
        select(Report).where(Report.id == report_id)
    ).scalar_one_or_none()
    if not report:
        raise HTTPException(status_code=404, detail="Rapport non trouvé")
    if not report.is_available and not current_user.is_admin:
        raise HTTPException(status_code=404, detail="Rapport non trouvé")
    check_content_access(current_user, report_type=report.report_type)

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
@limiter.limit("10/minute")
def track_download_by_type(
    request: Request, study_id: int, report_type: str, db: Session = Depends(get_tenant_db), current_user: User = Depends(get_current_user)
):
    report = db.execute(
        select(Report)
        .where(
            Report.study_id == study_id,
            Report.report_type == report_type,
            Report.is_available.is_(True),
        )
    ).scalar_one_or_none()
    if not report:
        raise HTTPException(status_code=404, detail="Rapport non trouvé")
    check_content_access(current_user, report_type=report.report_type)

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
