import html

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Contact, User
from app.dependencies import get_current_user
from app.pagination import PaginationParams, paginate
from app.schemas.contacts import ContactCreate, ContactResponse
from app.services.email import send_email, CONTACT_EMAIL
from app.services.email_templates import contact_form_email
from app.rate_limit import limiter

router = APIRouter()


@router.post("/api/contacts", response_model=ContactResponse, status_code=201)
@limiter.limit("3/minute")
async def create_contact(
    request: Request,
    data: ContactCreate,
    db: Session = Depends(get_db),
):
    new_contact = Contact(
        name=data.name,
        email=data.email,
        company=data.company,
        message=data.message,
    )
    db.add(new_contact)
    db.commit()
    db.refresh(new_contact)

    send_email(
        to=CONTACT_EMAIL,
        subject=f"Nouveau message de contact - {html.escape(data.name)}",
        html=contact_form_email(data.name, data.email, data.company, data.message),
    )

    return new_contact


@router.get("/api/contacts")
async def get_all_contacts(
    include_deleted: bool = False,
    pagination: PaginationParams = Depends(),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Liste des contacts (admin uniquement). Supporte la pagination via page/per_page."""
    if not current_user.is_admin:
        raise HTTPException(status_code=403, detail="Accès réservé aux administrateurs")

    stmt = select(Contact)
    if not include_deleted:
        stmt = stmt.where(Contact.deleted_at.is_(None))
    stmt = stmt.order_by(Contact.created_at.desc())
    return paginate(db, stmt, pagination)


@router.put("/api/contacts/{contact_id}/read")
async def mark_contact_as_read(
    contact_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Marquer un contact comme lu (admin uniquement)."""
    if not current_user.is_admin:
        raise HTTPException(status_code=403, detail="Accès réservé aux administrateurs")

    contact = db.execute(
        select(Contact).where(Contact.id == contact_id)
    ).scalar_one_or_none()
    if not contact:
        raise HTTPException(status_code=404, detail="Contact non trouvé")

    contact.is_read = True
    db.commit()

    return {"message": "Contact marqué comme lu"}


@router.delete("/api/contacts/{contact_id}")
async def delete_contact(
    contact_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Supprimer un contact (admin uniquement)."""
    if not current_user.is_admin:
        raise HTTPException(status_code=403, detail="Accès réservé aux administrateurs")

    contact = db.execute(
        select(Contact).where(Contact.id == contact_id)
    ).scalar_one_or_none()
    if not contact:
        raise HTTPException(status_code=404, detail="Contact non trouvé")

    from datetime import datetime, timezone
    contact.deleted_at = datetime.now(timezone.utc)
    db.commit()
    return {"message": "Contact supprimé avec succès"}
