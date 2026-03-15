# RAPPORT D'AUDIT TECHNIQUE — AFRIKALYTICS API (FastAPI)
**Date :** 15 mars 2026
**Auditeur :** Claude Code (Opus 4.6)
**Version auditée :** 1.0.0
**Périmètre :** `afrikalytics-api/`

---

## RÉSUMÉ EXÉCUTIF

### Score global : **6.1 / 10** (vs 3.2/10 précédemment — +2.9 points)

Le backend Afrikalytics a subi une refactorisation significative depuis l'état monolithique initial. L'application présente aujourd'hui une architecture modulaire correcte, un système d'authentification 2FA fonctionnel, un token blacklist, un audit log, une migration Alembic, et une suite de tests non triviale.

Cependant, plusieurs vulnérabilités de sécurité importantes subsistent : JWT en clair dans les redirections SSO, Swagger exposé en production, timeouts manquants sur les appels HTTP sortants, et un modèle de cohérence entre les deux projets du monorepo qui reste fragile.

---

## STATISTIQUES GLOBALES

| Sévérité | Nombre |
|----------|--------|
| Critique | 5 |
| Haute | 9 |
| Moyenne | 12 |
| Basse | 8 |
| **Total** | **34** |

| Catégorie | Nombre |
|-----------|--------|
| Sécurité | 10 |
| Architecture | 7 |
| Qualité Code | 7 |
| Performance | 4 |
| API Design | 3 |
| Database | 2 |
| Testing | 1 |

---

## SECTION 1 — SÉCURITÉ

### CRITIQUE — SEC-01 : JWT transmis en clair dans l'URL de redirection SSO

**Fichier :** `app/routers/auth.py` — lignes 632–634 et 746–748

**Description :** À la fin des callbacks SSO Google et Microsoft, le token JWT est injecté directement dans l'URL de redirection vers le frontend :

```python
return RedirectResponse(
    url=f"{frontend_url}/login?token={access_token}&sso=true"
)
```

Ce patron expose le JWT dans : les logs serveur, l'historique du navigateur, l'en-tête `Referer`, et les outils de monitoring. OWASP A02:2021 — Cryptographic Failures.

**Recommandation :** Utiliser un code d'autorisation à usage unique (PKCE-style) avec TTL 60 secondes, échangé contre le JWT via un appel API POST authentifié.

```python
sso_code = secrets.token_urlsafe(32)
# Stocker dans Redis/TokenBlacklist avec TTL 60s et user_id
return RedirectResponse(url=f"{frontend_url}/login?sso_code={sso_code}&sso=true")
# Le frontend échange ce code via POST /api/auth/sso/exchange -> retourne le JWT
```

---

### CRITIQUE — SEC-02 : Documentation Swagger/ReDoc accessible en production

**Fichier :** `main.py` — lignes 53–61

**Description :** L'application FastAPI est créée sans désactiver la documentation interactive. `/docs` et `/redoc` sont accessibles en production, révélant la surface d'attaque complète.

**Recommandation :**
```python
settings = get_settings()
docs_url = "/docs" if settings.environment != "production" else None
redoc_url = "/redoc" if settings.environment != "production" else None

app = FastAPI(
    title="Afrikalytics API",
    version="1.0.0",
    docs_url=docs_url,
    redoc_url=redoc_url,
    openapi_url="/openapi.json" if settings.environment != "production" else None,
)
```

---

### CRITIQUE — SEC-03 : Timeouts absents sur tous les appels HTTP sortants (PayDunya)

**Fichier :** `app/routers/payments.py` — lignes 246–251, 337–342, 450–451, 644–646

**Description :** Tous les appels vers l'API PayDunya utilisent `requests` sans timeout. Si PayDunya est lent ou down, ces appels bloquent indéfiniment le worker uvicorn → DoS indirect.

**Recommandation :**
```python
response = req.post(url, json=invoice_data, headers=headers, timeout=30)
```

---

### CRITIQUE — SEC-04 : Appel bloquant `requests` dans des handlers `async def`

**Fichier :** `app/routers/payments.py` — lignes 165, 288, 437, 624

**Description :** Les endpoints de paiement sont déclarés `async def` mais font des appels HTTP synchrones avec `requests`, bloquant l'event loop Python entier.

**Recommandation :** Migrer vers `httpx` (déjà dans `requirements.txt`) :
```python
import httpx

async def change_plan(...):
    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.post(url, json=invoice_data, headers=headers)
```

---

### CRITIQUE — SEC-05 : IP client non fiable derrière un proxy — Rate limiting contournable

**Fichier :** `app/rate_limit.py` — ligne 8

**Description :** `get_remote_address` retourne l'IP du proxy Railway, pas l'IP réelle du client. Tous les utilisateurs partagent le même compteur de rate limiting.

**Recommandation :**
```python
def get_real_ip(request: Request) -> str:
    forwarded_for = request.headers.get("X-Forwarded-For")
    if forwarded_for:
        return forwarded_for.split(",")[0].strip()
    return request.client.host if request.client else "unknown"

limiter = Limiter(key_func=get_real_ip)
```

---

### HAUTE — SEC-06 : Secrets PayDunya stockés dans des variables de module

**Fichier :** `app/routers/payments.py` — lignes 74–77

**Description :** Les clés sont évaluées à l'import time. En cas de rotation des secrets, un restart est obligatoire.

**Recommandation :** Accéder aux settings via `get_settings()` directement dans les fonctions.

---

### HAUTE — SEC-07 : Verify payment expose les données brutes PayDunya sans filtrage

**Fichier :** `app/routers/payments.py` — lignes 644–650

**Description :** Le handler retourne le JSON brut de PayDunya directement au client, pouvant contenir des informations sensibles.

**Recommandation :** Définir un schema `PaymentVerifyResponse` avec uniquement les champs nécessaires au frontend.

---

### HAUTE — SEC-08 : f-strings dans les logs avec des données utilisateur (injection de logs)

**Fichier :** Multiples routers

**Recommandation :** Utiliser le style `%s` :
```python
logger.warning("PayDunya webhook received unknown plan: %s", plan)
```

---

### HAUTE — SEC-09 : Absence de validation de l'email dans le webhook PayDunya

**Fichier :** `app/routers/payments.py` — lignes 471–473

**Recommandation :** Valider avec `pydantic.EmailStr` avant utilisation en DB.

---

### HAUTE — SEC-10 : CSRF bypass possible via la gestion des chemins exempts

**Fichier :** `main.py` — lignes 127–134

**Description :** L'interaction entre le middleware de rewrite de version et le CSRFMiddleware n'est pas vérifiée.

**Recommandation :** Normaliser les chemins avant les comparaisons et ajouter des tests couvrant cette interaction.

---

## SECTION 2 — ARCHITECTURE

### HAUTE — ARCH-01 : Imports depuis les modules racine au lieu de `app.*`

**Fichier :** `app/routers/auth.py`, `admin.py`, `payments.py`

**Description :** Plusieurs routers importent depuis les shims racine (`database`, `models`, `auth`) au lieu de `app.*`.

**Recommandation :** Standardiser tous les imports vers `app.*` et supprimer les shims.

---

### HAUTE — ARCH-02 : `get_tenant_db` pas un générateur — utilisation incorrecte

**Fichier :** `app/database.py` — lignes 57–63

**Recommandation :** Utiliser `yield from _get_tenant_db()` ou supprimer la fonction.

---

### HAUTE — ARCH-03 : Soft delete implémenté mais non appliqué

**Fichier :** `app/models.py` (SoftDeleteMixin) vs tous les routers

**Description :** Le `SoftDeleteMixin` ajoute `deleted_at` et `is_deleted` mais les suppressions utilisent `db.delete()` et les requêtes ne filtrent pas les éléments supprimés.

**Recommandation :** Implémenter le soft-delete de manière cohérente ou supprimer le mixin.

---

### MOYENNE — ARCH-04 : Duplication du code PayDunya

**Fichier :** `app/routers/payments.py` — `change_plan` et `create_paydunya_invoice`

**Recommandation :** Extraire dans `app/services/payment_service.py`.

---

### MOYENNE — ARCH-05 : Tags JSONB stockés comme chaîne JSON

**Fichier :** `app/routers/blog.py` — lignes 47, 181

**Recommandation :** Passer directement la liste Python, SQLAlchemy gère la sérialisation JSONB.

---

### MOYENNE — ARCH-06 : Correlation ID absent

**Recommandation :** Ajouter un middleware `X-Request-ID`.

---

### MOYENNE — ARCH-07 : `require_admin_permission` défini mais non utilisé

**Fichier :** `app/permissions.py` — ligne 59–67

**Recommandation :** Utiliser comme dependency FastAPI pour simplifier les routers.

---

## SECTION 3 — QUALITÉ DU CODE

### HAUTE — QC-01 : `datetime.fromtimestamp()` sans timezone

**Fichier :** `app/routers/auth.py` — ligne 428 ; `app/routers/users.py` — ligne 293

**Recommandation :**
```python
expires_at = datetime.fromtimestamp(payload.get("exp"), tz=timezone.utc)
```

---

### HAUTE — QC-02 : Brute-force protection compte les succès comme des échecs

**Fichier :** `app/routers/auth.py` — lignes 225–268

**Description :** `is_used=True` est aussi l'état d'un code utilisé avec succès, ce qui peut verrouiller un utilisateur légitime.

---

### HAUTE — QC-03 : `reset-password` hardcode l'URL du dashboard

**Fichier :** `app/routers/auth.py` — ligne 360

**Recommandation :** Utiliser `settings.frontend_url`.

---

### HAUTE — QC-04 : Dashboard stats — logique inversée pour les insights Basic

**Fichier :** `app/routers/dashboard.py` — lignes 100–107

**Description :** Le compteur pour Basic compte les insights NON publiés au lieu des publiés.

**Recommandation :**
```python
insights_count = db.execute(
    select(func.count()).select_from(Insight).where(Insight.is_published.is_(True))
).scalar()
```

---

### MOYENNE — QC-05 : `__import__('requests').RequestException` — antipattern

**Fichier :** `app/routers/payments.py` — ligne 356

---

### MOYENNE — QC-06 : `.dict()` déprécié (Pydantic v2)

**Fichier :** `app/routers/blog.py`, `admin.py`

**Recommandation :** Remplacer par `.model_dump()`.

---

### MOYENNE — QC-07 : Logging avec f-strings (performance + sécurité)

**Recommandation :** Utiliser le style `%s` systématiquement.

---

## SECTION 4 — PERFORMANCE

### HAUTE — PERF-01 : `cache_delete_pattern` utilise `KEYS *` — bloquant Redis

**Fichier :** `app/services/cache.py` — lignes 59–68

**Recommandation :** Utiliser `SCAN` avec curseur.

---

### HAUTE — PERF-02 : Redis client non thread-safe

**Fichier :** `app/services/cache.py` — lignes 13, 17–32

**Recommandation :** Utiliser `threading.Lock()` et backoff en cas d'échec.

---

### MOYENNE — PERF-03 : Queries séquentielles dans `login`

**Fichier :** `app/routers/auth.py` — lignes 141–170

---

### MOYENNE — PERF-04 : Import de `requests` dans les fonctions handler

**Fichier :** `app/routers/payments.py`

---

## SECTION 5 — DESIGN D'API

### MOYENNE — API-01 : Status codes incohérents sur DELETE (200 au lieu de 204)

### MOYENNE — API-02 : `/api/newsletter/subscribers` ne pagine pas

### BASSE — API-03 : Endpoint `popular` sans limite supérieure sur `limit`

---

## SECTION 6 — BASE DE DONNÉES

### MOYENNE — DB-01 : `images` Insight sérialisé manuellement dans JSONB

### BASSE — DB-02 : Absence d'index sur `VerificationCode`

---

## SECTION 7 — TESTS

### MOYENNE — TEST-01 : Tests SQLite incompatibles avec PostgreSQL

**Description :** La suite de tests utilise SQLite en mémoire mais l'app utilise des fonctionnalités PostgreSQL-spécifiques (JSONB, RLS, index partiels).

**Recommandation :** Configurer une base de test PostgreSQL dans la CI.

---

## SECTION 8 — DEVOPS

| ID | Sévérité | Description |
|----|----------|-------------|
| OPS-01 | Basse | Absence de Dockerfile |
| OPS-02 | Basse | Absence de CI/CD pipeline |
| OPS-03 | Basse | Pool PostgreSQL potentiellement insuffisant |
| OPS-04 | Basse | Versions partiellement non-fixées dans requirements.txt |
| OPS-05 | Basse | Sentry PII potentiels dans les exceptions |
| OPS-06 | Basse | Restart policy sans exponential backoff |

---

## SECTION 9 — DÉPENDANCES

| Package | Version actuelle | Dernière stable | Risque |
|---------|-----------------|-----------------|--------|
| `fastapi` | 0.104.1 | 0.115.x | Medium |
| `uvicorn` | 0.24.0 | 0.32.x | Low |
| `sqlalchemy` | 2.0.23 | 2.0.36+ | Low |
| `pydantic` | 2.5.2 | 2.10.x | Medium |
| `sentry-sdk` | 1.40.0 | 2.x | Medium |
| `resend` | 0.7.0 | 2.x | **High** |

---

## TOP 10 — PRIORITÉS DE REMÉDIATION

| # | ID | Description | Effort | Impact |
|---|-----|-------------|--------|--------|
| 1 | SEC-01 | JWT dans l'URL SSO | 2j | Critique |
| 2 | SEC-03 | Timeout appels PayDunya | 0.5j | Critique |
| 3 | SEC-04 | requests → httpx async | 1j | Critique |
| 4 | SEC-02 | Swagger désactivé en production | 0.5j | Critique |
| 5 | QC-04 | Logique inversée dashboard insights | 0.5j | Haute |
| 6 | QC-01 | datetime sans timezone | 1j | Haute |
| 7 | ARCH-01 | Standardiser imports vers `app.*` | 1j | Haute |
| 8 | PERF-01 | Redis KEYS → SCAN | 0.5j | Haute |
| 9 | ARCH-03 | Soft-delete incohérent | 2j | Haute |
| 10 | TEST-01 | CI avec PostgreSQL réel | 2j | Moyenne |

---

## POINTS POSITIFS

1. **Architecture refactorisée** — Monolithe 127KB → 14 routers modulaires
2. **Token blacklist** — JTI, logout, reset-password, change-password
3. **Audit log** — Actions CRUD admin avec IP, user_id, action, resource
4. **2FA par email** — Code 6 chiffres, expiration 10 min
5. **Alembic migrations** — Migrations versionnées
6. **Configuration centralisée** — `pydantic-settings` avec `lru_cache`
7. **CORS restrictif** — Liste blanche explicite
8. **Security headers** — HSTS, X-Frame-Options, CSP
9. **Suite de tests** — 18 fichiers de tests avec fixtures
10. **Infrastructure soft-delete et RLS** — Présente (à finaliser)

---

## FEUILLE DE ROUTE DE REMÉDIATION

### Semaine 1 (Critiques — 3 jours)
- **J1 :** SEC-01 (SSO JWT URL) + SEC-02 (Swagger production)
- **J2 :** SEC-03 (timeout PayDunya) + SEC-04 (requests → httpx async)
- **J3 :** QC-01 (datetime timezone) + QC-04 (dashboard insights bug)

### Semaine 2 (Hautes — 4 jours)
- **J1–J2 :** ARCH-01 (imports) + ARCH-03 (soft-delete)
- **J2 :** PERF-01 (Redis SCAN) + PERF-02 (Redis singleton)
- **J3 :** QC-02 (brute-force) + QC-03 (reset URL)
- **J4 :** SEC-05 (IP rate limit) + ARCH-02 (get_tenant_db)

### Semaine 3 (Moyennes)
- CI/CD GitHub Actions, PayDunya service, JSONB fixes, dépendances

### Semaine 4 (Basses + polish)
- Dockerfile, conventions API, code quality, DevOps

---

## SCORE DÉTAILLÉ

| Catégorie | Score |
|-----------|-------|
| Sécurité | 5.5/10 |
| Architecture | 6.5/10 |
| Qualité Code | 6.0/10 |
| Performance | 6.5/10 |
| API Design | 7.0/10 |
| Database | 7.0/10 |
| Auth & RBAC | 7.5/10 |
| Testing | 6.0/10 |
| DevOps | 5.5/10 |
| Dépendances | 6.0/10 |
| **GLOBAL** | **6.1/10** |

---

*Rapport généré le 15 mars 2026 par Claude Code (Opus 4.6)*
