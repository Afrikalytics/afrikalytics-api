"""
Utility functions and constants for the Afrikalytics API.
Extracted from models.py to keep models clean.
"""

import re
import secrets
import unicodedata


def validate_password(password: str) -> tuple[bool, str]:
    """
    Valider la complexite d'un mot de passe.
    Retourne (True, "") si valide, (False, "message en francais") sinon.
    """
    if len(password) < 8:
        return False, "Le mot de passe doit contenir au moins 8 caractères"

    if not re.search(r'[A-Z]', password):
        return False, "Le mot de passe doit contenir au moins une lettre majuscule"

    if not re.search(r'[a-z]', password):
        return False, "Le mot de passe doit contenir au moins une lettre minuscule"

    if not re.search(r'[0-9]', password):
        return False, "Le mot de passe doit contenir au moins un chiffre"

    if not re.search(r'[!@#$%^&*()\-_+=\[\]{}|;:,.<>?]', password):
        return False, "Le mot de passe doit contenir au moins un caractère spécial (!@#$%^&*()_+-=[]{}|;:,.<>?)"

    return True, ""


def generate_slug(title: str) -> str:
    """
    Generate a slug from a title.
    Example: "Les 5 Tendances IA en 2025" -> "les-5-tendances-ia-en-2025"
    """
    # Normalize accents
    slug = unicodedata.normalize('NFKD', title)
    slug = slug.encode('ascii', 'ignore').decode('utf-8')

    # Lowercase
    slug = slug.lower()

    # Replace spaces and special chars with dashes
    slug = re.sub(r'[^a-z0-9\s-]', '', slug)
    slug = re.sub(r'[\s]+', '-', slug)
    slug = re.sub(r'-+', '-', slug)

    # Strip leading/trailing dashes
    slug = slug.strip('-')

    # Limit to 100 chars
    slug = slug[:100]

    return slug


def ensure_unique_slug(db, slug: str, post_id: int | None = None) -> str:
    """
    Ensure the slug is unique in blog_posts.
    If it already exists, append a numeric suffix.
    """
    from sqlalchemy import select
    from app.models import BlogPost

    original_slug = slug
    counter = 1

    while True:
        stmt = select(BlogPost).where(BlogPost.slug == slug)

        # Exclude current post when editing
        if post_id:
            stmt = stmt.where(BlogPost.id != post_id)

        existing = db.execute(stmt).scalar_one_or_none()

        if not existing:
            return slug

        slug = f"{original_slug}-{counter}"
        counter += 1

        # Safety: max 100 attempts
        if counter > 100:
            slug = f"{original_slug}-{secrets.token_hex(4)}"
            break

    return slug


def calculate_days_remaining(end_date) -> int | None:
    """
    Calculate the number of days remaining from today until end_date.
    Returns None if end_date is None, 0 if already expired.
    Handles both datetime and date objects.
    """
    from datetime import datetime, timezone

    if end_date is None:
        return None

    if hasattr(end_date, "date"):
        end = end_date.date()
    else:
        end = end_date

    days = (end - datetime.now(timezone.utc).date()).days
    return max(0, days)


