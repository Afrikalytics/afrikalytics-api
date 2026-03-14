"""
Shared test fixtures for Afrikalytics API tests.

Provides:
- SQLite in-memory test database (overrides PostgreSQL)
- TestClient with dependency override for DB session
- Auth helper to generate valid JWT tokens for authenticated requests
"""
import os
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

# Set test environment variables BEFORE importing app modules
os.environ.setdefault("SECRET_KEY", "test-secret-key-for-ci")
os.environ.setdefault("DATABASE_URL", "sqlite:///./test.db")

from database import Base, get_db
from main import app
from auth import hash_password, create_access_token
from models import User

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


@pytest.fixture()
def db():
    """Yield a test database session."""
    session = TestingSessionLocal()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture()
def client(db):
    """FastAPI TestClient with overridden DB dependency."""

    def _override_get_db():
        try:
            yield db
        finally:
            pass

    app.dependency_overrides[get_db] = _override_get_db
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


@pytest.fixture()
def test_user(db) -> User:
    """Create and return a basic test user."""
    user = User(
        email="testuser@example.com",
        full_name="Test User",
        hashed_password=hash_password("TestPassword123!"),
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
        hashed_password=hash_password("AdminPassword123!"),
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
def auth_headers(test_user) -> dict:
    """Return Authorization headers with a valid JWT for test_user."""
    token = create_access_token(data={"sub": test_user.email})
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture()
def admin_auth_headers(admin_user) -> dict:
    """Return Authorization headers with a valid JWT for admin_user."""
    token = create_access_token(data={"sub": admin_user.email})
    return {"Authorization": f"Bearer {token}"}
