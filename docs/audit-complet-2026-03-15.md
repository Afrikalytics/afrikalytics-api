# AUDIT COMPLET — AFRIKALYTICS MONOREPO

**Date :** 15 mars 2026 | **Auditeurs :** 3 agents spécialisés (Sécurité, Qualité Code, Architecture/Performance)
**Périmètre :** `afrikalytics-dashboard/` + `afrikalytics-api/`
**Audit précédent :** 3.2/10

---

## SCORE GLOBAL : 6.5 / 10 (+3.3 vs 3.2/10)

| Domaine | Score | Objectif | Delta vs précédent |
|---------|-------|----------|---------------------|
| Sécurité | **7.1/10** | 7/10 | +3.9 |
| Qualité Code | **5.8/10** | 7/10 | +2.6 |
| Architecture | **7.0/10** | 7/10 | +3.8 |
| Tests | **5.5/10** | 70% cov | +5.5 (de ~0) |
| Performance | **6.5/10** | — | +3.3 |
| **GLOBAL** | **6.5/10** | **7/10** | **+3.3** |

---

## OBJECTIFS ATTEINTS

| Objectif | Statut |
|----------|--------|
| Sécurité >= 7/10 | **ATTEINT (7.1)** |
| Qualité Code >= 7/10 | Non atteint (5.8) |
| Architecture >= 7/10 | **ATTEINT (7.0)** |
| Tests >= 70% | Non atteint (~45%) |

---

## AMÉLIORATIONS MAJEURES DEPUIS L'AUDIT PRÉCÉDENT

1. **Auth sécurisé** — JWT migré de localStorage vers httpOnly cookies + proxy Next.js
2. **SSO sécurisé** — Exchange code pattern (plus de JWT dans les URLs)
3. **API refactorisée** — Monolithe 127KB → 15 routers + 12 services + 18 schemas
4. **Duplication dashboard** — 46% → ~12% (useAuth hook + lib/api.ts centralisés)
5. **Alembic migrations** — 12 fichiers de migration (plus de create_all())
6. **CORS restrictif** — Plus de wildcard, liste blanche explicite
7. **Rate limiting** — Tous les endpoints sensibles protégés avec IP réelle
8. **Swagger désactivé** en production
9. **Tests créés** — 21 fichiers API + 12 fichiers dashboard + 6 E2E Playwright
10. **Token blacklist** — Logout, reset-password, change-password invalidés
11. **PayDunya async** — Migré de requests sync vers httpx async avec timeout 30s

---

## SECTION 1 — SÉCURITÉ (7.1/10)

### Checklist

| Critère | Statut | Détail |
|---------|--------|--------|
| Pas de secrets hardcodés | **PASS** | pydantic-settings, .env exclusivement |
| API_URL en env var | **PARTIAL** | Centralisé dans constants.ts, fallback localhost en dev |
| JWT sécurisé | **PASS** | HS256 whitelist, JTI, blacklist, httpOnly cookies |
| CORS sans wildcard | **PASS** | 7 origines + regex Vercel preview |
| Validation rôles server-side | **PASS** | DB-loaded user, jamais de confiance client |
| Rate limiting endpoints sensibles | **PASS** | 3-10/min selon endpoint, IP réelle |
| Pas de XSS | **PARTIAL** | Pas de dangerouslySetInnerHTML, iframe sandboxé mais allow-same-origin risqué |

### Vulnérabilités résiduelles

| Sévérité | ID | Description | Fichier |
|----------|----|-------------|---------|
| **Haute** | SEC-R1 | `hmac.new()` potentiellement cassé dans webhook PayDunya | `payments.py:369` |
| **Moyenne** | SEC-R2 | OAuth state non vérifié (CSRF SSO) | `auth.py:505,605` |
| **Moyenne** | SEC-R3 | embed_url sans validation d'origine dans schemas | `schemas/studies.py` |
| **Moyenne** | SEC-R4 | iframe sandbox allow-same-origin + allow-scripts | `etudes/[id]/page.tsx:331` |
| **Basse** | SEC-R5 | Token expiry 7 jours (réduire à 15-60 min) | `config.py:24` |

---

## SECTION 2 — QUALITÉ CODE (5.8/10)

### Dashboard

| Critère | Score | Détail |
|---------|-------|--------|
| Duplication | 8/10 | ~12% (objectif <20% **ATTEINT**) |
| `any` TypeScript | 7/10 | 3 occurrences seulement (2 dans ActivityChart) |
| Types centralisés | 8/10 | lib/types.ts complet (22 types exportés) |
| Constantes centralisées | 8/10 | lib/constants.ts (API_URL, ROUTES, ADMIN_ROLES...) |
| Nommage FR/EN | 6/10 | Cohérent : routes FR, code EN |

### API

| Critère | Score | Détail |
|---------|-------|--------|
| Duplication payments.py | **4/10** | ~40% duplication interne |
| .dict() vs .model_dump() | 9/10 | Migration Pydantic v2 complète |
| Imports app.* | **4/10** | 4 routers encore sur imports racine |
| Logging f-strings | **5/10** | 29 occurrences (devrait être %s) |
| Type hints | 7/10 | Bonne couverture, quelques dict bruts |

### Points bloquants pour atteindre 7/10

1. **payments.py** — Extraire helpers: `_get_paydunya_headers()`, `_build_invoice()`, `_create_payment_record()`
2. **Imports** — Migrer auth.py, admin.py, payments.py, blog.py vers `from app.*`
3. **Logging** — Remplacer 29 f-strings par style `%s`

---

## SECTION 3 — ARCHITECTURE (7.0/10)

### Dashboard Architecture

| Aspect | Score | Détail |
|--------|-------|--------|
| Layout partagé | 9/10 | Route group (dashboard) avec layout unique |
| Sidebar réutilisable | 9/10 | Composant unique dans components/ |
| API client centralisé | 8/10 | lib/api.ts (ApiService class) |
| useAuth centralisé | 9/10 | Toutes les pages via layout |
| Code splitting | 8/10 | next/dynamic sur composants lourds |

### API Architecture

| Aspect | Score | Détail |
|--------|-------|--------|
| Modularisation | 9/10 | 15 routers, 18 schemas, 12 services |
| Séparation concerns | 7/10 | Services extraits, mais payments reste monolithique |
| Alembic migrations | 8/10 | 12 migrations versionnées |
| Config centralisée | 9/10 | pydantic-settings + lru_cache |
| Middleware | 8/10 | CSRF, security headers, proxy headers, versioning |

### Architecture résiduelle

| Issue | Impact |
|-------|--------|
| SQLAlchemy sync dans handlers async | Event loop bloqué sous charge |
| send_email() synchrone inline | Bloque la requête si Resend lent |
| 5 COUNT séquentiels dans dashboard/stats | Performance dégradée |
| Activity chart avec Math.random() | Données fictives en production |

---

## SECTION 4 — TESTS (5.5/10)

### Inventaire

| Projet | Framework | Fichiers | Couverture estimée |
|--------|-----------|----------|--------------------|
| Dashboard | Jest + RTL | 12 unit tests | ~40-50% des pages |
| Dashboard | Playwright | 6 E2E specs | Auth, admin, builder, import |
| API | pytest | 21 test files | ~60-70% des endpoints |
| **Total** | — | **39 fichiers** | **~45%** |

### Points forts
- API : couverture de tous les 15 domaines (auth, RBAC, payments, blog...)
- Dashboard : E2E auth bien écrit (a11y, responsive, mocking API)
- Fixtures partagées, CSRFTestClient, mock email

### Lacunes
- Tests API sur SQLite (pas PostgreSQL) — JSONB, RLS, index partiels non testés
- Pas de CI/CD — tests jamais exécutés automatiquement
- E2E encore basé sur localStorage (stale après migration httpOnly)
- Pages non couvertes : facturation, insights/[id], reports, payment-success

---

## SECTION 5 — PERFORMANCE (6.5/10)

### Dashboard

| Aspect | Score | Détail |
|--------|-------|--------|
| Promise.all | 9/10 | Utilisé sur dashboard principal |
| Memoization | 7/10 | 34 useMemo/useCallback sur 8 fichiers |
| Code splitting | 8/10 | next/dynamic sur recharts, framer-motion |
| next/image | 6/10 | 3 `<img>` bruts restants |

### API

| Aspect | Score | Détail |
|--------|-------|--------|
| Caching Redis | 7/10 | TTL 120-300s, invalidation sur mutations |
| Pagination | 7/10 | PaginationParams sur listes |
| N+1 queries | 6/10 | selectin lazy, joinedload sur cron |
| Connection pool | 7/10 | pool_size=10, max_overflow=20, pre_ping |
| Redis KEYS → SCAN | **4/10** | Toujours `KEYS *` bloquant |
| Async/sync mismatch | **4/10** | Session sync dans handlers async |

---

## TOP 10 ACTIONS PRIORITAIRES

| # | Action | Domaine | Effort | Impact |
|---|--------|---------|--------|--------|
| 1 | Fixer `hmac.new()` webhook PayDunya | Sécurité | 0.5j | Critique — bug live |
| 2 | Vérifier OAuth state dans SSO callbacks | Sécurité | 1j | Haute — CSRF SSO |
| 3 | Refactorer payments.py (extraire helpers) | Qualité | 2j | Haute — -15% duplication |
| 4 | Standardiser imports → `from app.*` | Qualité | 0.5j | Haute — dette technique |
| 5 | Remplacer 29 f-strings logging → `%s` | Qualité | 0.5j | Moyenne — perf + sécurité |
| 6 | Redis KEYS → SCAN | Performance | 0.5j | Haute — blocage prod |
| 7 | CI/CD GitHub Actions (lint + tests) | Tests | 1j | Haute — régression |
| 8 | Valider embed_url dans schemas Pydantic | Sécurité | 0.5j | Moyenne — XSS stored |
| 9 | BackgroundTasks pour send_email() | Performance | 1j | Moyenne — latence |
| 10 | Tests PostgreSQL en CI (Docker) | Tests | 1j | Moyenne — fidelité |

---

## COMPARATIF DÉTAILLÉ

| Catégorie | Mars 2026 (initial) | Mars 2026 (post-fix) | Cible Q2 |
|-----------|--------------------|-----------------------|----------|
| Secrets | 2/10 | 9/10 | 9/10 |
| Auth/JWT | 3/10 | 9/10 | 9/10 |
| CORS | 2/10 | 9/10 | 9/10 |
| Rate limiting | 1/10 | 9/10 | 9/10 |
| XSS | 2/10 | 7/10 | 8/10 |
| CSRF | 1/10 | 8/10 | 9/10 |
| Duplication dashboard | 2/10 | 8/10 | 9/10 |
| Duplication API | N/A | 4/10 | 7/10 |
| Architecture dashboard | 3/10 | 8/10 | 9/10 |
| Architecture API | 2/10 | 8/10 | 9/10 |
| Tests | 0/10 | 5.5/10 | 7/10 |
| CI/CD | 0/10 | 0/10 | 7/10 |
| Performance | 3/10 | 6.5/10 | 7/10 |
| **GLOBAL** | **3.2/10** | **6.5/10** | **7.5/10** |

---

## CONCLUSION

Le projet a progressé de **3.2/10 à 6.5/10** (+3.3 points) grâce à un effort significatif de refactorisation. Les objectifs de sécurité (7.1/10) et d'architecture (7.0/10) sont atteints. Les deux domaines restants sous l'objectif sont la **qualité du code** (5.8, principalement payments.py) et les **tests** (5.5, besoin de CI/CD + PostgreSQL).

Pour atteindre le score cible de 7.5/10, les 3 actions à plus fort ROI sont :
1. Refactorer `payments.py` (+1 pt qualité code)
2. Mettre en place CI/CD avec tests PostgreSQL (+1.5 pt tests)
3. Fixer les 2 vulnérabilités résiduelles hmac + OAuth state (+0.5 pt sécurité)

---

*Rapport généré le 15 mars 2026 par 3 agents spécialisés Claude Code (Opus 4.6)*
