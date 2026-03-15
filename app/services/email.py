"""
Service d'envoi d'emails via Resend.
Extrait de main.py pour centraliser la logique email.
"""
import logging

import resend
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from app.config import get_settings

logger = logging.getLogger(__name__)

settings = get_settings()

# Configurer Resend
resend.api_key = settings.resend_api_key
CONTACT_EMAIL = settings.contact_email

# Set HTTP timeout for the Resend SDK (uses httpx internally)
resend.httpx_client_timeout = 10  # seconds


@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=1, max=10),
    retry=retry_if_exception_type((ConnectionError, TimeoutError, OSError)),
    reraise=True,
)
def _send_with_retry(params: dict) -> dict:
    """Send email via Resend SDK with retry on network errors."""
    return resend.Emails.send(params)


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
        _send_with_retry(params)
        return True
    except (ConnectionError, TimeoutError, OSError) as e:
        logger.error("Resend network error after retries: %s", e)
        return False
    except Exception as e:
        logger.error("Erreur envoi email: %s", e)
        return False
