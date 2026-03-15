"""
Service d'envoi d'emails via Resend.
Extrait de main.py pour centraliser la logique email.
"""
import logging
import os
import resend

logger = logging.getLogger(__name__)

# Configurer Resend
resend.api_key = os.getenv("RESEND_API_KEY")
CONTACT_EMAIL = os.getenv("CONTACT_EMAIL", "contact@afrikalytics.com")


def send_email(to: str, subject: str, html: str) -> bool:
    """
    Envoyer un email via Resend.

    Args:
        to: Adresse email du destinataire
        subject: Sujet de l'email
        html: Contenu HTML de l'email

    Returns:
        True si l'envoi a reussi, False sinon
    """
    try:
        params = {
            "from": "Afrikalytics <noreply@notifications.afrikalytics.com>",
            "to": [to],
            "subject": subject,
            "html": html
        }
        resend.Emails.send(params)
        return True
    except Exception as e:
        logger.error("Erreur envoi email: %s", e)
        return False
