# Audit Backend — Afrikalytics API

Execute un audit technique complet sur le backend FastAPI.

## Etapes

### 1. Securite
- Scanner `auth.py` pour le SECRET_KEY fallback
- Verifier CORS dans `main.py` (pas de wildcard `*`)
- Verifier que tous les endpoints admin ont `Depends(get_current_user)` + `require_admin_permission()`
- Scanner les `os.getenv()` sans valeur par defaut securisee
- Verifier le rate limiting sur auth endpoints

### 2. Qualite code
- Compter les type hints manquants
- Verifier la coherence des schemas Pydantic (Create/Update/Response)
- Scanner les `try: except: pass` (exceptions avalees)
- Verifier les imports inutilises

### 3. Architecture
- Verifier la separation router/service/model
- Scanner les requetes SQL directes (doit utiliser ORM)
- Verifier que `models.py` et `auth.py` sont bien integres dans `app/`

### 4. Tests
- Verifier si `tests/` existe et contient des tests
- Calculer la couverture si pytest est installe
- Lister les endpoints sans tests

### 5. Rapport
Generer un score /10 par domaine et un score global.
