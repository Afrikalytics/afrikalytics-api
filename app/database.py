import logging
from typing import Generator

from sqlalchemy import create_engine, text
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.config import get_settings

logger = logging.getLogger(__name__)

settings = get_settings()

# URL de la base de données (Railway fournira DATABASE_URL)
DATABASE_URL = settings.database_url

# Fix pour PostgreSQL sur Railway (postgresql:// -> postgresql+psycopg2://)
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

# Créer le moteur SQLAlchemy avec pool configuré pour PostgreSQL
engine = create_engine(
    DATABASE_URL,
    pool_size=5,
    max_overflow=10,
    pool_pre_ping=True,
    pool_recycle=300,
    connect_args={"connect_timeout": 10},
)

# Session locale
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Base pour les modèles (SQLAlchemy 2.0 style)
class Base(DeclarativeBase):
    pass


# Dépendance pour obtenir la session DB (sans contexte tenant — pour endpoints publics)
def get_db() -> Generator[Session, None, None]:
    """
    Standard database session without RLS tenant context.
    Use this for public endpoints (blog, newsletter, auth) and admin endpoints
    that need to see all data regardless of tenant.
    """
    db = SessionLocal()
    try:
        yield db
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


# Re-export get_tenant_db for convenience (canonical location: app.middleware.tenant)
# Import deferred to avoid circular imports — use app.middleware.tenant directly in routers
def get_tenant_db():
    """
    Database session with RLS tenant context.
    Convenience re-export — canonical import: from app.middleware.tenant import get_tenant_db
    """
    from app.middleware.tenant import get_tenant_db as _get_tenant_db
    return _get_tenant_db()
