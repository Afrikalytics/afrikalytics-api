import json

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy.orm import Session

from database import get_db
from models import Insight, User
from app.dependencies import get_current_user
from app.permissions import check_admin_permission
from app.schemas.insights import InsightCreate, InsightResponse

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
def get_all_insights(
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    insights = (
        db.query(Insight)
        .filter(Insight.is_published == True)
        .offset(skip)
        .limit(limit)
        .all()
    )
    return [convert_insight_images(insight) for insight in insights]


@router.get("/api/insights/study/{study_id}")
def get_insight_by_study(study_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    insight = (
        db.query(Insight)
        .filter(Insight.study_id == study_id, Insight.is_published == True)
        .first()
    )
    if not insight:
        raise HTTPException(status_code=404, detail="Insight not found")
    return convert_insight_images(insight)


@router.get("/api/insights/{insight_id}")
def get_insight(insight_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    insight = db.query(Insight).filter(Insight.id == insight_id).first()
    if not insight:
        raise HTTPException(status_code=404, detail="Insight not found")
    return convert_insight_images(insight)


@router.post("/api/insights", status_code=201)
def create_insight(
    data: InsightCreate,
    db: Session = Depends(get_db),
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
    return convert_insight_images(insight)


@router.put("/api/insights/{insight_id}")
def update_insight(
    insight_id: int,
    data: InsightCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if not check_admin_permission(current_user, "insights"):
        raise HTTPException(status_code=403, detail="Vous n'avez pas la permission de gérer les insights")

    insight = db.query(Insight).filter(Insight.id == insight_id).first()
    if not insight:
        raise HTTPException(status_code=404, detail="Insight non trouvé")

    insight.study_id = data.study_id
    insight.title = data.title
    insight.summary = data.summary
    insight.key_findings = data.key_findings
    insight.recommendations = data.recommendations
    insight.author = data.author
    insight.images = json.dumps(data.images) if data.images else None
    insight.is_published = data.is_published

    db.commit()
    db.refresh(insight)
    return convert_insight_images(insight)


@router.delete("/api/insights/{insight_id}")
def delete_insight(
    insight_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if not check_admin_permission(current_user, "insights"):
        raise HTTPException(status_code=403, detail="Vous n'avez pas la permission de gérer les insights")

    insight = db.query(Insight).filter(Insight.id == insight_id).first()
    if not insight:
        raise HTTPException(status_code=404, detail="Insight non trouvé")

    db.delete(insight)
    db.commit()
    return {"message": "Insight deleted successfully"}
