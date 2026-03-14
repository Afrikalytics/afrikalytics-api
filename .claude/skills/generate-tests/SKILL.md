# Skill: Generate Tests for API

Genere des tests Pytest pour un module ou endpoint specifique.

## Processus

1. Lire le router cible dans `app/routers/`
2. Identifier tous les endpoints (methode, path, auth, parametres)
3. Lire le schema associe dans `app/schemas/`
4. Generer les tests :
   - **Happy path** : requete valide, reponse attendue
   - **Auth required** : requete sans token → 401
   - **Forbidden** : mauvais role → 403
   - **Validation** : donnees invalides → 422
   - **Not found** : ID inexistant → 404
   - **Edge cases** : champs vides, limites, caracteres speciaux

## Fichier conftest.py

Si `tests/conftest.py` n'existe pas, le creer avec :

```python
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from database import Base, get_db
from main import app

SQLALCHEMY_TEST_URL = "sqlite:///./test.db"
engine = create_engine(SQLALCHEMY_TEST_URL, connect_args={"check_same_thread": False})
TestingSessionLocal = sessionmaker(bind=engine)

@pytest.fixture(scope="function")
def db_session():
    Base.metadata.create_all(bind=engine)
    session = TestingSessionLocal()
    yield session
    session.close()
    Base.metadata.drop_all(bind=engine)

@pytest.fixture
def client(db_session):
    def override_get_db():
        yield db_session
    app.dependency_overrides[get_db] = override_get_db
    yield TestClient(app)
    app.dependency_overrides.clear()

@pytest.fixture
def auth_headers(client):
    client.post("/api/auth/register", json={
        "full_name": "Test User",
        "email": "test@test.com",
        "password": "TestPass123!"
    })
    response = client.post("/api/auth/login", json={
        "email": "test@test.com",
        "password": "TestPass123!"
    })
    token = response.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}
```
