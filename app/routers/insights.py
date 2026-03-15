import json
import logging

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

from app.database import get_db
from app.middleware.tenant import get_tenant_db
from app.models import Insight, User
from app.dependencies import get_current_user
from app.permissions import check_admin_permission
from app.schemas.insights import InsightCreate, InsightUpdate
from app.services.audit import log_action
from app.rate_limit import limiter

router = APIRouter()


def convert_insight_images(insight):
    return {
        "id": insight.id,
        "study_id": insight.study_id,
        "title": insight.title,
        "summary": insight.summary,
        "key_findings": insight.key_findings,
        "recommendations": insight.recommendations,
        "author": insight.author,
        "images": json.loads(insight.images) if insight.images else [],
        "is_published": insight.is_published,
        "created_at": insight.created_at,
    }


@router.get("/api/insights")
@limiter.limit("30/minute")
def get_all_insights(
    request: Request,
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
    db: Session = Depends(get_tenant_db),
    current_user: User = Depends(get_current_user),
):
    insights = db.execute(
        select(Insight)
        .where(Insight.is_published.is_(True))
        .offset(skip)
        .limit(limit)
    ).scalars().all()
    return [convert_insight_images(insight) for insight in insights]


@router.get("/api/insights/study/{study_id}")
@limiter.limit("30/minute")
def get_insight_by_study(request: Request, study_id: int, db: Session = Depends(get_tenant_db), current_user: User = Depends(get_current_user)):
    insight = db.execute(
        select(Insight)
        .where(Insight.study_id == study_id, Insight.is_published.is_(True))
    ).scalar_one_or_none()
    if not insight:
        raise HTTPException(status_code=404, detail="Insight not found")
    return convert_insight_images(insight)


@router.get("/api/insights/{insight_id}")
@limiter.limit("30/minute")
def get_insight(request: Request, insight_id: int, db: Session = Depends(get_tenant_db), current_user: User = Depends(get_current_user)):
    insight = db.execute(
        select(Insight).where(Insight.id == insight_id)
    ).scalar_one_or_none()
    if not insight:
        raise HTTPException(status_code=404, detail="Insight not found")
    if not insight.is_published and not check_admin_permission(current_user, "insights"):
        raise HTTPException(status_code=404, detail="Insight not found")
    return convert_insight_images(insight)


@router.post("/api/insights", status_code=201)
@limiter.limit("10/minute")
def create_insight(
    data: InsightCreate,
    request: Request,
    db: Session = Depends(get_tenant_db),
    current_user: User = Depends(get_current_user),
):
    if not check_admin_permission(current_user, "insights"):
        raise HTTPException(status_code=403, detail="Vous n'avez pas la permission de gérer les insights")

    insight = Insight(
        study_id=data.study_id,
        title=data.title,
        summary=data.summary,
        key_findings=data.key_findings,
        recommendations=data.recommendations,
        author=data.author,
        images=json.dumps(data.images) if data.images else None,
        is_published=data.is_published,
    )
    db.add(insight)
    db.commit()
    db.refresh(insight)

    # Audit log
    try:
        log_action(
            db=db, user_id=current_user.id, action="create", resource_type="insight",
            resource_id=insight.id, details={"title": insight.title},
            request=request,
        )
    except Exception as e:
        logger.warning(f"Audit log failed: {e}")

    return convert_insight_images(insight)


@router.put("/api/insights/{insight_id}")
@limiter.limit("10/minute")
def update_insight(
    insight_id: int,
    data: InsightUpdate,
    request: Request,
    db: Session = Depends(get_tenant_db),
    current_user: User = Depends(get_current_user),
):
    if not check_admin_permission(current_user, "insights"):
        raise HTTPException(status_code=403, detail="Vous n'avez pas la permission de gérer les insights")

    insight = db.execute(
        select(Insight).where(Insight.id == insight_id)
    ).scalar_one_or_none()
    if not insight:
        raise HTTPException(status_code=404, detail="Insight non trouvé")

    update_data = data.model_dump(exclude_unset=True)
    if "images" in update_data:
        update_data["images"] = json.dumps(update_data["images"]) if update_data["images"] else None
    for key, value in update_data.items():
        setattr(insight, key, value)

    db.commit()
    db.refresh(insight)

    # Audit log
    try:
        log_action(
            db=db, user_id=current_user.id, action="update", resource_type="insight",
            resource_id=insight_id, details={"title": insight.title},
            request=request,
        )
    except Exception as e:
        logger.warning(f"Audit log failed: {e}")

    return convert_insight_images(insight)


@router.delete("/api/insights/{insight_id}")
@limiter.limit("5/minute")
def delete_insight(
    insight_id: int,
    request: Request,
    db: Session = Depends(get_tenant_db),
    current_user: User = Depends(get_current_user),
):
    if not check_admin_permission(current_user, "insights"):
        raise HTTPException(status_code=403, detail="Vous n'avez pas la permission de gérer les insights")

    insight = db.execute(
        select(Insight).where(Insight.id == insight_id)
    ).scalar_one_or_none()
    if not insight:
        raise HTTPException(status_code=404, detail="Insight non trouvé")

    deleted_title = insight.title

    # Audit log BEFORE deletion
    try:
        log_action(
            db=db, user_id=current_user.id, action="delete", resource_type="insight",
            resource_id=insight_id, details={"deleted_title": deleted_title},
            request=request,
        )
    except Exception as e:
        logger.warning(f"Audit log failed: {e}")

    db.delete(insight)
    db.commit()
    return {"message": "Insight deleted successfully"}
