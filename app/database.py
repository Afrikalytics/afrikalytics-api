import logging
from typing import Generator

from sqlalchemy import MetaData, create_engine, text
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
# pool_size: number of persistent connections kept open (matches typical Railway worker count)
# max_overflow: extra connections allowed under load, closed when idle
# pool_pre_ping: test connections before use (detects stale connections after Railway restarts)
# pool_recycle: recreate connections every 1800s to avoid PostgreSQL idle-connection timeouts
# pool_timeout: max seconds to wait for a connection from the pool before raising an error
engine = create_engine(
    DATABASE_URL,
    pool_size=10,
    max_overflow=20,
    pool_pre_ping=True,
    pool_recycle=1800,
    pool_timeout=30,
    connect_args={"connect_timeout": 10},
)

# Session locale
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Naming convention for consistent constraint names across all tables
NAMING_CONVENTION = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}

# Base pour les modèles (SQLAlchemy 2.0 style)
class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=NAMING_CONVENTION)


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
