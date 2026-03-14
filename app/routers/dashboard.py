"""
Router pour le dashboard, les statistiques et la gestion des abonnements.
3 endpoints : stats dashboard, vérification expiry (cron), abonnement courant.
"""
import html
import logging
import os
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, Header, HTTPException
from sqlalchemy.orm import Session, joinedload

from database import get_db
from models import User, Study, Subscription, Report, Insight
from app.dependencies import get_current_user
from app.services.email import send_email
from app.utils import calculate_days_remaining

logger = logging.getLogger(__name__)

router = APIRouter()

CRON_SECRET = os.getenv("CRON_SECRET", "")
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
    # Études accessibles (actives)
    studies_accessible = db.query(Study).filter(Study.is_active == True).count()

    # Études auxquelles l'utilisateur peut accéder selon son plan
    if current_user.plan == "basic":
        # Basic : seulement études ouvertes à la participation
        studies_count = db.query(Study).filter(
            Study.is_active == True,
            Study.status == "Ouvert",
        ).count()
    else:
        # Premium : toutes les études actives
        studies_count = studies_accessible

    # Jours restants d'abonnement
    days_remaining = None
    if current_user.plan in ["professionnel", "entreprise"]:
        subscription = db.query(Subscription).filter(
            Subscription.user_id == current_user.id,
            Subscription.status == "active",
        ).first()

        if subscription and subscription.end_date:
            days_remaining = calculate_days_remaining(subscription.end_date)

    # Rapports disponibles selon le plan
    if current_user.plan == "basic":
        reports_count = db.query(Report).filter(Report.report_type == "basic").count()
    else:
        reports_count = db.query(Report).count()

    # Insights disponibles selon le plan
    # Note: Insight.is_premium n'existe pas dans le modèle — on utilise is_published
    # comme proxy pour les insights accessibles au plan basic.
    if current_user.plan == "basic":
        insights_count = db.query(Insight).filter(Insight.is_published == False).count()
    else:
        insights_count = db.query(Insight).count()

    # Études ouvertes (status = "Ouvert")
    studies_open = db.query(Study).filter(
        Study.is_active == True,
        Study.status == "Ouvert",
    ).count()

    return {
        "studies_accessible": studies_count,
        "studies_total": studies_accessible,
        "studies_open": studies_open,
        "reports_available": reports_count,
        "insights_available": insights_count,
        "subscription_days_remaining": days_remaining,
        "plan": current_user.plan,
        "is_premium": current_user.plan in ["professionnel", "entreprise"],
    }


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

    today = datetime.utcnow().date()
    results = {
        "checked_at": datetime.utcnow().isoformat(),
        "reminders_j7": 0,
        "reminders_j3": 0,
        "reminders_j0": 0,
        "downgraded": 0,
        "errors": [],
    }

    # Récupérer tous les abonnements actifs avec leurs utilisateurs (eager load to avoid N+1)
    active_subscriptions = (
        db.query(Subscription)
        .options(joinedload(Subscription.user))
        .filter(Subscription.status == "active")
        .all()
    )

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
                    html=f"""
                        <h2>Bonjour {html.escape(user.full_name)},</h2>
                        <p>Votre abonnement <strong>{html.escape(sub.plan.capitalize())}</strong> expire dans <strong>7 jours</strong>.</p>
                        <p>Pour continuer à profiter de tous les avantages Premium :</p>
                        <ul>
                            <li>✅ Résultats en temps réel</li>
                            <li>✅ Insights complets</li>
                            <li>✅ Rapports PDF détaillés</li>
                            <li>✅ Dashboard avancé</li>
                        </ul>
                        <p style="margin: 30px 0;">
                            <a href="https://afrikalytics.com/checkout"
                               style="background-color: #2563eb; color: white; padding: 12px 24px; text-decoration: none; border-radius: 8px; font-weight: bold;">
                                Renouveler mon abonnement
                            </a>
                        </p>
                        <hr>
                        <p><em>L'équipe Afrikalytics AI by Marketym</em></p>
                    """,
                )
                results["reminders_j7"] += 1

            # J-3 : Rappel 3 jours avant
            elif days_remaining == 3:
                send_email(
                    to=user.email,
                    subject="⚠️ Plus que 3 jours pour renouveler votre abonnement Afrikalytics",
                    html=f"""
                        <h2>Bonjour {html.escape(user.full_name)},</h2>
                        <p>Votre abonnement <strong>{html.escape(sub.plan.capitalize())}</strong> expire dans <strong>3 jours</strong>.</p>
                        <p style="color: #e74c3c; font-weight: bold;">
                            Sans renouvellement, vous perdrez l'accès aux fonctionnalités Premium.
                        </p>
                        <p style="margin: 30px 0;">
                            <a href="https://afrikalytics.com/checkout"
                               style="background-color: #e74c3c; color: white; padding: 12px 24px; text-decoration: none; border-radius: 8px; font-weight: bold;">
                                Renouveler maintenant
                            </a>
                        </p>
                        <hr>
                        <p><em>L'équipe Afrikalytics AI by Marketym</em></p>
                    """,
                )
                results["reminders_j3"] += 1

            # J-0 : Dernier jour
            elif days_remaining == 0:
                send_email(
                    to=user.email,
                    subject="🚨 DERNIER JOUR - Votre abonnement Afrikalytics expire aujourd'hui",
                    html=f"""
                        <h2>Bonjour {html.escape(user.full_name)},</h2>
                        <p style="color: #e74c3c; font-size: 18px; font-weight: bold;">
                            Votre abonnement {html.escape(sub.plan.capitalize())} expire AUJOURD'HUI !
                        </p>
                        <p>Renouvelez maintenant pour ne pas perdre vos accès Premium.</p>
                        <p style="margin: 30px 0;">
                            <a href="https://afrikalytics.com/checkout"
                               style="background-color: #e74c3c; color: white; padding: 16px 32px; text-decoration: none; border-radius: 8px; font-weight: bold; font-size: 16px;">
                                RENOUVELER MAINTENANT
                            </a>
                        </p>
                        <hr>
                        <p><em>L'équipe Afrikalytics AI by Marketym</em></p>
                    """,
                )
                results["reminders_j0"] += 1

            # J+1 : Abonnement expiré — Rétrograder vers Basic
            elif days_remaining < 0:
                # Mettre à jour le statut de l'abonnement
                sub.status = "expired"

                # Si c'est un propriétaire Entreprise, rétrograder aussi tous ses membres
                if user.plan == "entreprise" and user.parent_user_id is None:
                    team_members = (
                        db.query(User).filter(User.parent_user_id == user.id).all()
                    )
                    for member in team_members:
                        member.plan = "basic"
                        member.parent_user_id = None
                        # Notifier chaque membre
                        send_email(
                            to=member.email,
                            subject="😢 L'abonnement Entreprise de votre équipe a expiré",
                            html=f"""
                                <h2>Bonjour {html.escape(member.full_name)},</h2>
                                <p>L'abonnement Entreprise de <strong>{html.escape(user.full_name)}</strong> a expiré.</p>
                                <p>Votre compte a été rétrogradé au <strong>Plan Basic (gratuit)</strong>.</p>
                                <p>Vous conservez l'accès à :</p>
                                <ul>
                                    <li>✅ Participation aux études</li>
                                    <li>✅ Aperçu des insights</li>
                                    <li>✅ Dashboard basic</li>
                                </ul>
                                <p>Vous n'avez plus accès aux fonctionnalités Premium.</p>
                                <p>Si vous souhaitez continuer avec un abonnement individuel :</p>
                                <p style="margin: 30px 0;">
                                    <a href="https://afrikalytics.com/premium"
                                       style="background-color: #2563eb; color: white; padding: 12px 24px; text-decoration: none; border-radius: 8px; font-weight: bold;">
                                        Voir les offres Premium
                                    </a>
                                </p>
                                <hr>
                                <p><em>L'équipe Afrikalytics AI by Marketym</em></p>
                            """,
                        )

                # Rétrograder l'utilisateur vers Basic
                user.plan = "basic"

                db.commit()

                # Envoyer email de notification d'expiration
                send_email(
                    to=user.email,
                    subject="😢 Votre abonnement Afrikalytics a expiré",
                    html=f"""
                        <h2>Bonjour {html.escape(user.full_name)},</h2>
                        <p>Votre abonnement <strong>{html.escape(sub.plan.capitalize())}</strong> a expiré.</p>
                        <p>Votre compte a été rétrogradé au <strong>Plan Basic (gratuit)</strong>.</p>
                        <p>Vous conservez l'accès à :</p>
                        <ul>
                            <li>✅ Participation aux études</li>
                            <li>✅ Aperçu des insights</li>
                            <li>✅ Dashboard basic</li>
                        </ul>
                        <p>Vous n'avez plus accès à :</p>
                        <ul>
                            <li>❌ Résultats en temps réel</li>
                            <li>❌ Insights complets</li>
                            <li>❌ Rapports PDF</li>
                        </ul>
                        <p style="margin: 30px 0;">
                            <a href="https://afrikalytics.com/checkout"
                               style="background-color: #2563eb; color: white; padding: 12px 24px; text-decoration: none; border-radius: 8px; font-weight: bold;">
                                Réactiver mon abonnement Premium
                            </a>
                        </p>
                        <hr>
                        <p><em>L'équipe Afrikalytics AI by Marketym</em></p>
                    """,
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
    subscription = db.query(Subscription).filter(
        Subscription.user_id == current_user.id,
        Subscription.status == "active",
    ).first()

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
