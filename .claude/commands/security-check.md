---
description: Verification de securite pre-deploiement pour l'API FastAPI
---

# Security Check Command (API)

## Verification automatique

### 1. Secrets et configuration
- [ ] Grep pour des secrets hardcodes : `password`, `secret`, `key`, `token` dans le code (hors .env)
- [ ] Verifier que `.env` est dans `.gitignore`
- [ ] Verifier que `SECRET_KEY` n'a pas de fallback insecure dans `auth.py`
- [ ] Verifier que les cles PayDunya et Resend viennent de `os.environ`

### 2. Authentication
- [ ] Tous les endpoints proteges utilisent `Depends(get_current_user)`
- [ ] Les endpoints admin verifient `admin_role` cote serveur
- [ ] Pas de bypass d'authentification
- [ ] Token JWT avec expiration raisonnable

### 3. Input Validation
- [ ] Tous les POST/PUT utilisent des schemas Pydantic
- [ ] Pas de SQL brut (tout via SQLAlchemy ORM)
- [ ] Tailles limitees sur les champs texte
- [ ] Validation email/URL quand applicable

### 4. CORS
- [ ] Pas de wildcard `*` dans `allow_origins`
- [ ] Seuls les domaines de production et dev autorises
- [ ] `allow_credentials=True` uniquement si necessaire

### 5. Rate Limiting
- [ ] Endpoints auth limites (login, register, forgot-password)
- [ ] SlowAPI configure et actif

### 6. Dependencies
- [ ] Verifier les vulnerabilites : `pip audit` ou `safety check`
- [ ] Pas de packages inutilises dans requirements.txt

## Rapport
```
🔒 Security Check — Afrikalytics API
═════════════════════════════════════
✅ Passed  : X checks
⚠️  Warning : X issues
❌ Failed  : X issues
═════════════════════════════════════
[Details...]

Ready to deploy: ✅ Yes | ❌ No (fix required issues first)
```
