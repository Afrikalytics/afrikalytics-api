"""
Router pour le dashboard, les statistiques et la gestion des abonnements.
3 endpoints : stats dashboard, vérification expiry (cron), abonnement courant.
"""
import logging
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, Header, HTTPException
from sqlalchemy import select, func
from sqlalchemy.orm import Session, joinedload

from app.config import get_settings
from app.database import get_db
from app.models import User, Study, Subscription, Report, Insight
from app.dependencies import get_current_user
from app.services.email import send_email
from app.services.email_templates import (
    subscription_reminder_j7_email,
    subscription_reminder_j3_email,
    subscription_reminder_j0_email,
    subscription_expired_email,
    team_subscription_expired_email,
)
from app.utils import calculate_days_remaining
from app.services.cache import cache_get, cache_set

logger = logging.getLogger(__name__)

settings = get_settings()

router = APIRouter()

CRON_SECRET = settings.cron_secret
if not CRON_SECRET:
    logger.warning("CRON_SECRET is not set. Cron endpoints will return 503.")


@router.get("/api/dashboard/stats")
async def get_dashboard_stats(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Récupérer les statistiques du dashboard pour l'utilisateur connecté.
    Adapte les compteurs selon le plan (basic vs premium).
    """
    # Check cache (per-user, keyed by user id and plan)
    cache_key = f"dashboard:stats:{current_user.id}:{current_user.plan}"
    cached = cache_get(cache_key)
    if cached:
        return cached

    # Études accessibles (actives)
    studies_accessible = db.execute(
        select(func.count()).select_from(Study).where(Study.is_active.is_(True))
    ).scalar()

    # Études auxquelles l'utilisateur peut accéder selon son plan
    if current_user.plan == "basic":
        # Basic : seulement études ouvertes à la participation
        studies_count = db.execute(
            select(func.count()).select_from(Study).where(
                Study.is_active.is_(True),
                Study.status == "Ouvert",
            )
        ).scalar()
    else:
        # Premium : toutes les études actives
        studies_count = studies_accessible

    # Jours restants d'abonnement
    days_remaining = None
    if current_user.plan in ["professionnel", "entreprise"]:
        subscription = db.execute(
            select(Subscription).where(
                Subscription.user_id == current_user.id,
                Subscription.status == "active",
            )
        ).scalar_one_or_none()

        if subscription and subscription.end_date:
            days_remaining = calculate_days_remaining(subscription.end_date)

    # Rapports disponibles selon le plan
    if current_user.plan == "basic":
        reports_count = db.execute(
            select(func.count()).select_from(Report).where(Report.report_type == "basic")
        ).scalar()
    else:
        reports_count = db.execute(
            select(func.count()).select_from(Report)
        ).scalar()

    # Insights disponibles selon le plan
    # Note: Insight.is_premium n'existe pas dans le modèle — on utilise is_published
    # comme proxy pour les insights accessibles au plan basic.
    if current_user.plan == "basic":
        insights_count = db.execute(
            select(func.count()).select_from(Insight).where(Insight.is_published.is_(False))
        ).scalar()
    else:
        insights_count = db.execute(
            select(func.count()).select_from(Insight)
        ).scalar()

    # Études ouvertes (status = "Ouvert")
    studies_open = db.execute(
        select(func.count()).select_from(Study).where(
            Study.is_active.is_(True),
            Study.status == "Ouvert",
        )
    ).scalar()

    result = {
        "studies_accessible": studies_count,
        "studies_total": studies_accessible,
        "studies_open": studies_open,
        "reports_available": reports_count,
        "insights_available": insights_count,
        "subscription_days_remaining": days_remaining,
        "plan": current_user.plan,
        "is_premium": current_user.plan in ["professionnel", "entreprise"],
    }
    cache_set(cache_key, result, ttl=120)
    return result


@router.post("/api/subscriptions/check-expiry")
async def check_subscription_expiry(
    db: Session = Depends(get_db),
    x_cron_secret: Optional[str] = Header(None),
):
    """
    Vérifier les abonnements et envoyer les rappels / rétrograder vers Basic.
    Endpoint appelé par un cron job quotidien (cron-job.org).
    Reminders : J-7, J-3, J-0. Downgrade + notification à J+1.
    """
    # Vérifier le secret
    if not CRON_SECRET:
        raise HTTPException(status_code=503, detail="Cron integration not configured")
    if not x_cron_secret or x_cron_secret != CRON_SECRET:
        raise HTTPException(status_code=401, detail="Unauthorized")

    today = datetime.now(timezone.utc).date()
    results = {
        "checked_at": datetime.now(timezone.utc).isoformat(),
        "reminders_j7": 0,
        "reminders_j3": 0,
        "reminders_j0": 0,
        "downgraded": 0,
        "errors": [],
    }

    # Récupérer tous les abonnements actifs avec leurs utilisateurs (eager load to avoid N+1)
    active_subscriptions = db.execute(
        select(Subscription)
        .options(joinedload(Subscription.user))
        .where(Subscription.status == "active")
    ).scalars().all()

    for sub in active_subscriptions:
        try:
            if not sub.end_date:
                continue

            end_date = (
                sub.end_date.date()
                if hasattr(sub.end_date, "date")
                else sub.end_date
            )
            days_remaining = (end_date - today).days

            # User is already eager-loaded via joinedload
            user = sub.user
            if not user:
                continue

            # J-7 : Rappel 7 jours avant
            if days_remaining == 7:
                send_email(
                    to=user.email,
                    subject="⏰ Votre abonnement Afrikalytics expire dans 7 jours",
                    html=subscription_reminder_j7_email(user.full_name, sub.plan),
                )
                results["reminders_j7"] += 1

            # J-3 : Rappel 3 jours avant
            elif days_remaining == 3:
                send_email(
                    to=user.email,
                    subject="⚠️ Plus que 3 jours pour renouveler votre abonnement Afrikalytics",
                    html=subscription_reminder_j3_email(user.full_name, sub.plan),
                )
                results["reminders_j3"] += 1

            # J-0 : Dernier jour
            elif days_remaining == 0:
                send_email(
                    to=user.email,
                    subject="🚨 DERNIER JOUR - Votre abonnement Afrikalytics expire aujourd'hui",
                    html=subscription_reminder_j0_email(user.full_name, sub.plan),
                )
                results["reminders_j0"] += 1

            # J+1 : Abonnement expiré — Rétrograder vers Basic
            elif days_remaining < 0:
                # Mettre à jour le statut de l'abonnement
                sub.status = "expired"

                # Si c'est un propriétaire Entreprise, rétrograder aussi tous ses membres
                if user.plan == "entreprise" and user.parent_user_id is None:
                    team_members = db.execute(
                        select(User).where(User.parent_user_id == user.id)
                    ).scalars().all()
                    for member in team_members:
                        member.plan = "basic"
                        member.parent_user_id = None
                        # Notifier chaque membre
                        send_email(
                            to=member.email,
                            subject="😢 L'abonnement Entreprise de votre équipe a expiré",
                            html=team_subscription_expired_email(member.full_name, user.full_name),
                        )

                # Rétrograder l'utilisateur vers Basic
                user.plan = "basic"

                db.commit()

                # Envoyer email de notification d'expiration
                send_email(
                    to=user.email,
                    subject="😢 Votre abonnement Afrikalytics a expiré",
                    html=subscription_expired_email(user.full_name, sub.plan),
                )
                results["downgraded"] += 1

        except Exception as e:
            results["errors"].append(f"User {sub.user_id}: {str(e)}")

    return results


@router.get("/api/subscriptions/my-subscription")
async def get_my_subscription(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Récupérer l'abonnement actif de l'utilisateur connecté.
    Retourne has_subscription=False si aucun abonnement actif.
    """
    subscription = db.execute(
        select(Subscription).where(
            Subscription.user_id == current_user.id,
            Subscription.status == "active",
        )
    ).scalar_one_or_none()

    if not subscription:
        return {
            "has_subscription": False,
            "plan": current_user.plan,
            "message": "Aucun abonnement actif",
        }

    # Calculer les jours restants
    days_remaining = calculate_days_remaining(subscription.end_date)

    return {
        "has_subscription": True,
        "plan": subscription.plan,
        "status": subscription.status,
        "start_date": subscription.start_date.isoformat() if subscription.start_date else None,
        "end_date": subscription.end_date.isoformat() if subscription.end_date else None,
        "days_remaining": days_remaining,
    }
