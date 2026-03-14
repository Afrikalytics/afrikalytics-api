# Deploy Check — Backend API

Verification pre-deploiement pour le backend FastAPI sur Railway.

## Checklist

### 1. Configuration
- [ ] `Procfile` pointe vers `main:app`
- [ ] `railway.json` a le healthcheck `/health`
- [ ] `requirements.txt` est a jour (pas de deps manquantes)
- [ ] `.env.example` contient toutes les variables requises

### 2. Securite
- [ ] `SECRET_KEY` n'a pas de fallback hardcode
- [ ] CORS ne contient pas `*` en production
- [ ] Pas de `print()` ou `breakpoint()` oublies
- [ ] Rate limiting actif sur les endpoints auth

### 3. Base de donnees
- [ ] Migrations Alembic a jour (si configurees)
- [ ] Pas de `Base.metadata.create_all()` en production (utiliser migrations)
- [ ] Indexes sur les colonnes critiques

### 4. API
- [ ] Tous les routers sont inclus dans `main.py`
- [ ] Swagger UI accessible (`/docs`)
- [ ] Endpoint `/health` repond 200
- [ ] Pas d'endpoints de debug exposes

### 5. Resume
Generer un rapport PASS/FAIL avec recommandations.
