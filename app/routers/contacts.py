import html

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy.orm import Session
from typing import List

from database import get_db
from models import Contact, User
from app.dependencies import get_current_user
from app.permissions import check_admin_permission
from app.schemas.contacts import ContactCreate, ContactResponse
from app.services.email import send_email, CONTACT_EMAIL
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
        html=f"""
            <h2>Nouveau message de contact</h2>
            <p><strong>Nom :</strong> {html.escape(data.name)}</p>
            <p><strong>Email :</strong> {html.escape(data.email)}</p>
            <p><strong>Entreprise :</strong> {html.escape(data.company) if data.company else 'Non renseigné'}</p>
            <hr>
            <p><strong>Message :</strong></p>
            <p>{html.escape(data.message)}</p>
            <hr>
            <p><em>Message envoyé depuis le formulaire de contact Afrikalytics</em></p>
        """,
    )

    return new_contact


@router.get("/api/contacts", response_model=List[ContactResponse])
async def get_all_contacts(
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Liste des contacts (admin uniquement). Supporte la pagination via skip/limit."""
    if not current_user.is_admin:
        raise HTTPException(status_code=403, detail="Acc\u00e8s r\u00e9serv\u00e9 aux administrateurs")

    contacts = db.query(Contact).order_by(Contact.created_at.desc()).offset(skip).limit(limit).all()
    return contacts


@router.put("/api/contacts/{contact_id}/read")
async def mark_contact_as_read(
    contact_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Marquer un contact comme lu (admin uniquement)."""
    if not current_user.is_admin:
        raise HTTPException(status_code=403, detail="Acc\u00e8s r\u00e9serv\u00e9 aux administrateurs")

    contact = db.query(Contact).filter(Contact.id == contact_id).first()
    if not contact:
        raise HTTPException(status_code=404, detail="Contact non trouv\u00e9")

    contact.is_read = True
    db.commit()

    return {"message": "Contact marqu\u00e9 comme lu"}


@router.delete("/api/contacts/{contact_id}")
async def delete_contact(
    contact_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Supprimer un contact (admin uniquement)."""
    if not current_user.is_admin:
        raise HTTPException(status_code=403, detail="Acc\u00e8s r\u00e9serv\u00e9 aux administrateurs")

    contact = db.query(Contact).filter(Contact.id == contact_id).first()
    if not contact:
        raise HTTPException(status_code=404, detail="Contact non trouv\u00e9")

    db.delete(contact)
    db.commit()
    return {"message": "Contact supprim\u00e9 avec succ\u00e8s"}
