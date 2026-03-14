# Skill: Review API Code

Revue de code backend avec focus sur securite, qualite et performance.

## Checklist de revue

### Securite (OWASP Top 10)
- [ ] Pas de secrets hardcodes (SECRET_KEY, API keys, passwords)
- [ ] Injection SQL : utilise SQLAlchemy ORM, pas de raw SQL
- [ ] Validation des entrees : Pydantic schemas sur tous les endpoints
- [ ] Authentification : `Depends(get_current_user)` sur les endpoints proteges
- [ ] Autorisation : `require_admin_permission()` verifie les roles
- [ ] Rate limiting : SlowAPI sur les endpoints sensibles
- [ ] CORS : pas de wildcard `*` en production

### Qualite
- [ ] Type hints sur tous les parametres et retours
- [ ] Docstrings FastAPI (summary, description)
- [ ] Gestion d'erreurs coherente (HTTPException avec detail)
- [ ] Pas de `try: except: pass` (swallowed exceptions)
- [ ] Nommage coherent (snake_case, noms descriptifs)
- [ ] Import propres (pas de `from module import *`)

### Performance
- [ ] Queries optimisees (pas de N+1, utiliser joinedload)
- [ ] Pagination sur les listes
- [ ] Index DB sur les colonnes filtrees
- [ ] Pas de calculs lourds dans les endpoints (deleguer aux services)

### Architecture
- [ ] Separation router/service/model
- [ ] Dependency injection via `Depends()`
- [ ] Schemas Pydantic separes pour Create/Update/Response
- [ ] Pas de logique metier dans les routers

## Output

Generer un rapport avec :
- CRITICAL / HIGH / MEDIUM / LOW par issue
- Fichier et ligne concernes
- Suggestion de correction
