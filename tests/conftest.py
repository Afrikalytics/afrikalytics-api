"""
Shared test fixtures for Afrikalytics API tests.

Provides:
- SQLite in-memory test database (overrides PostgreSQL)
- TestClient with dependency override for DB session
- Auth helper to generate valid JWT tokens for authenticated requests
- CSRF header included automatically via a wrapper client
- Additional fixtures: study, insight, report, blog_post,
  content_admin_user, enterprise_user
- Global mock of app.services.email.send_email (autouse)
"""
import os
import pytest
from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

# Set test environment variables BEFORE importing app modules
os.environ.setdefault("SECRET_KEY", "test-secret-key-for-ci")
os.environ.setdefault("DATABASE_URL", "sqlite:///./test.db")

from app.database import Base, get_db
from main import app
from app.auth import hash_password, create_access_token
from app.models import User, Study, Insight, Report, BlogPost

# ---------------------------------------------------------------------------
# Shared test passwords (not real credentials — used only in test fixtures)
# ---------------------------------------------------------------------------
TEST_USER_PW = "TestPassword123!"       # noqa: S105
ADMIN_PW = "AdminPassword123!"          # noqa: S105
CONTENT_ADMIN_PW = "ContentAdmin123!"   # noqa: S105
ENTERPRISE_PW = "Enterprise123!"        # noqa: S105

# ---------------------------------------------------------------------------
# Test database (SQLite in-memory)
# ---------------------------------------------------------------------------
SQLALCHEMY_TEST_DATABASE_URL = "sqlite:///./test.db"

engine = create_engine(
    SQLALCHEMY_TEST_DATABASE_URL,
    connect_args={"check_same_thread": False},
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


@pytest.fixture(autouse=True)
def setup_database():
    """Create all tables before each test, drop after."""
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)


@pytest.fixture(autouse=True)
def mock_send_email():
    """
    Mock global pour send_email dans tous les routers qui l'importent.
    Evite tout envoi reel d'email pendant les tests.

    Chaque router fait `from app.services.email import send_email`, ce qui
    cree une reference locale dans le module. Il faut patcher chaque module
    individuellement pour intercepter les appels.

    Retourne True (succes simule) par defaut.
    """
    mock = MagicMock(return_value=True)
    patches = [
        patch("app.services.email.send_email", mock),
        patch("app.routers.auth.send_email", mock),
        patch("app.routers.users.send_email", mock),
        patch("app.routers.admin.send_email", mock),
        patch("app.routers.contacts.send_email", mock),
        patch("app.routers.dashboard.send_email", mock),
        patch("app.routers.payments.send_email", mock),
    ]
    for p in patches:
        p.start()
    yield mock
    for p in patches:
        p.stop()


@pytest.fixture()
def db():
    """Yield a test database session."""
    session = TestingSessionLocal()
    try:
        yield session
    finally:
        session.close()


# ---------------------------------------------------------------------------
# CSRF-aware TestClient wrapper
# ---------------------------------------------------------------------------

class CSRFTestClient:
    """
    Wrapper autour de TestClient qui injecte automatiquement le header
    X-Requested-With: XMLHttpRequest sur les requetes POST, PUT, DELETE, PATCH.
    Cela satisfait le CSRFMiddleware de l'application.
    """

    CSRF_METHODS = {"post", "put", "delete", "patch"}
    CSRF_HEADER = {"X-Requested-With": "XMLHttpRequest"}

    def __init__(self, test_client: TestClient):
        self._client = test_client

    def _inject_csrf(self, kwargs: dict) -> dict:
        headers = dict(kwargs.get("headers") or {})
        headers.update(self.CSRF_HEADER)
        kwargs["headers"] = headers
        return kwargs

    def get(self, *args, **kwargs):
        return self._client.get(*args, **kwargs)

    def post(self, *args, **kwargs):
        return self._client.post(*args, **self._inject_csrf(kwargs))

    def put(self, *args, **kwargs):
        return self._client.put(*args, **self._inject_csrf(kwargs))

    def delete(self, *args, **kwargs):
        return self._client.delete(*args, **self._inject_csrf(kwargs))

    def patch(self, *args, **kwargs):
        return self._client.patch(*args, **self._inject_csrf(kwargs))


@pytest.fixture()
def client(db):
    """
    FastAPI TestClient avec override DB et injection CSRF automatique.
    Retourne un CSRFTestClient qui ajoute X-Requested-With sur toutes
    les requetes mutantes.
    """

    def _override_get_db():
        try:
            yield db
        finally:
            pass

    app.dependency_overrides[get_db] = _override_get_db
    with TestClient(app) as raw_client:
        yield CSRFTestClient(raw_client)
    app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# User fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def test_user(db) -> User:
    """Create and return a basic test user."""
    user = User(
        email="testuser@example.com",
        full_name="Test User",
        hashed_password=hash_password(TEST_USER_PW),
        plan="basic",
        is_active=True,
        is_admin=False,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


@pytest.fixture()
def admin_user(db) -> User:
    """Create and return a super_admin test user."""
    user = User(
        email="admin@example.com",
        full_name="Admin User",
        hashed_password=hash_password(ADMIN_PW),
        plan="entreprise",
        is_active=True,
        is_admin=True,
        admin_role="super_admin",
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


@pytest.fixture()
def content_admin_user(db) -> User:
    """
    Create and return an admin_content user.
    Has permissions: studies=True, insights=True, reports=True, users=False.
    """
    user = User(
        email="content_admin@example.com",
        full_name="Content Admin",
        hashed_password=hash_password(CONTENT_ADMIN_PW),
        plan="entreprise",
        is_active=True,
        is_admin=True,
        admin_role="admin_content",
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


@pytest.fixture()
def enterprise_user(db) -> User:
    """Create and return a user with plan='entreprise' (non-admin)."""
    user = User(
        email="enterprise@example.com",
        full_name="Enterprise User",
        hashed_password=hash_password(ENTERPRISE_PW),
        plan="entreprise",
        is_active=True,
        is_admin=False,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


# ---------------------------------------------------------------------------
# Auth header fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def auth_headers(test_user) -> dict:
    """Return Authorization headers with a valid JWT for test_user."""
    token = create_access_token(data={"sub": test_user.email})
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture()
def admin_auth_headers(admin_user) -> dict:
    """Return Authorization headers with a valid JWT for admin_user."""
    token = create_access_token(data={"sub": admin_user.email})
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture()
def content_admin_auth_headers(content_admin_user) -> dict:
    """Return Authorization headers for content_admin_user."""
    token = create_access_token(data={"sub": content_admin_user.email})
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture()
def enterprise_auth_headers(enterprise_user) -> dict:
    """Return Authorization headers for enterprise_user."""
    token = create_access_token(data={"sub": enterprise_user.email})
    return {"Authorization": f"Bearer {token}"}


# ---------------------------------------------------------------------------
# Content fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def study(db, admin_user) -> Study:
    """Create and return a test study linked to admin_user."""
    s = Study(
        title="Etude Test Marche Dakar",
        description="Description de l'etude test.",
        category="Consommation",
        duration="15-20 min",
        deadline="31 Decembre 2026",
        status="Ouvert",
        icon="users",
        is_active=True,
    )
    db.add(s)
    db.commit()
    db.refresh(s)
    return s


@pytest.fixture()
def inactive_study(db) -> Study:
    """Create and return an inactive study."""
    s = Study(
        title="Etude Inactive",
        description="Cette etude n'est pas active.",
        category="Finance",
        status="Ferme",
        is_active=False,
    )
    db.add(s)
    db.commit()
    db.refresh(s)
    return s


@pytest.fixture()
def insight(db, study) -> Insight:
    """Create and return a published insight linked to study."""
    ins = Insight(
        study_id=study.id,
        title="Insight Test",
        summary="Resume de l'insight test.",
        key_findings="Resultat cle 1, Resultat cle 2",
        recommendations="Recommandation A",
        author="Equipe Afrikalytics",
        is_published=True,
    )
    db.add(ins)
    db.commit()
    db.refresh(ins)
    return ins


@pytest.fixture()
def report(db, study) -> Report:
    """Create and return an available basic report linked to study."""
    r = Report(
        study_id=study.id,
        title="Rapport Test",
        description="Description du rapport test.",
        file_url="https://cdn.example.com/reports/test-report.pdf",
        file_name="test-report.pdf",
        file_size=204800,
        report_type="basic",
        download_count=0,
        is_available=True,
    )
    db.add(r)
    db.commit()
    db.refresh(r)
    return r


@pytest.fixture()
def blog_post(db, admin_user) -> BlogPost:
    """Create and return a published blog post linked to admin_user."""
    post = BlogPost(
        title="Article Test",
        slug="article-test-2026",
        excerpt="Extrait de l'article test.",
        content="Contenu complet de l'article test pour les tests automatises.",
        category="Analyse",
        author_id=admin_user.id,
        status="published",
    )
    db.add(post)
    db.commit()
    db.refresh(post)
    return post
