from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from app.config import get_settings

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

# Dépendance pour obtenir la session DB
def get_db():
    db = SessionLocal()
    try:
        yield db
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()
