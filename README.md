# Afrikalytics API

Backend REST API pour **Afrikalytics AI** — plateforme de Business Intelligence pour l'Afrique francophone.

[![CI](https://github.com/Afrikalytics/afrikalytics-api/actions/workflows/ci.yml/badge.svg)](https://github.com/Afrikalytics/afrikalytics-api/actions/workflows/ci.yml)

## Stack

- **Framework :** FastAPI 0.104
- **Python :** 3.11+
- **ORM :** SQLAlchemy 2.0
- **Base de donnees :** PostgreSQL 16
- **Validation :** Pydantic v2
- **Auth :** JWT HS256 (python-jose + bcrypt)
- **Emails :** Resend
- **Paiements :** PayDunya (FCFA / Mobile Money)
- **Monitoring :** Sentry
- **CI/CD :** GitHub Actions
- **Deploiement :** Railway (Nixpacks)

## Structure

```
afrikalytics-api/
├── main.py                  # App FastAPI, CORS, middleware, Sentry init
├── auth.py                  # JWT : create/decode tokens, hash/verify passwords
├── models.py                # 12 modeles SQLAlchemy
├── database.py              # Engine + session SQLAlchemy
├── app/
│   ├── routers/             # 11 routers (auth, users, admin, studies, insights,
│   │                        #   reports, blog, newsletter, payments, dashboard, contacts)
│   ├── schemas/             # 11 schemas Pydantic v2
│   ├── services/            # email.py, audit.py
│   ├── dependencies.py      # get_current_user, token blacklist check
│   ├── permissions.py       # RBAC : check_admin_permission, require_admin_permission
│   └── utils.py             # validate_password
├── alembic/                 # Migrations DB (Alembic)
│   └── versions/            # Migration initiale (12 tables)
├── tests/                   # 182 tests pytest
│   ├── conftest.py          # Fixtures, CSRF client, mocks
│   ├── test_users.py        # 15 tests
│   ├── test_admin.py        # 19 tests
│   ├── test_studies.py      # 18 tests
│   ├── test_insights.py     # 20 tests
│   ├── test_reports.py      # 25 tests
│   ├── test_dashboard.py    # 10 tests
│   ├── test_blog.py         # 34 tests
│   ├── test_newsletter.py   # 14 tests
│   ├── test_contacts.py     # 16 tests
│   └── test_payments.py     # 6 tests (3 skipped — PayDunya sandbox)
├── Dockerfile               # Python 3.11-slim + healthcheck
├── docker-compose.yml       # PostgreSQL + Redis + API
├── Procfile                 # alembic upgrade head && uvicorn
├── requirements.txt
└── .github/workflows/
    ├── ci.yml               # Lint (ruff) → Test (pytest) → Security (Bandit)
    └── claude-code.yml      # Claude Code GitHub integration
```

## Installation locale

```bash
# 1. Environnement virtuel
python -m venv venv
source venv/bin/activate      # Linux/Mac
# venv\Scripts\activate       # Windows

# 2. Dependances
pip install -r requirements.txt

# 3. Variables d'environnement
cp .env.example .env
# Editer .env avec vos valeurs (DATABASE_URL, SECRET_KEY, etc.)

# 4. Migrations
alembic upgrade head

# 5. Serveur de dev
uvicorn main:app --reload --port 8000
```

- API : **http://localhost:8000**
- Swagger UI : **http://localhost:8000/docs**
- ReDoc : **http://localhost:8000/redoc**

### Avec Docker

```bash
docker compose up
```

Demarre PostgreSQL 16, Redis 7 et l'API sur le port 8000.

## Tests

```bash
pip install pytest pytest-cov httpx
pytest --cov=app -v
```

182 tests couvrant les 11 routers. Le CI exige un minimum de 40% de couverture.

## Endpoints API (68 routes, 11 domaines)

| Domaine | Prefix | Routes principales |
|---------|--------|--------------------|
| Auth | `/api/auth/` | login, register, verify-code, resend-code, forgot-password, reset-password, logout |
| Users | `/api/users/` | me, quota, change-password, create (Zapier), equipe |
| Admin | `/api/admin/` | CRUD users, roles, toggle active, audit-log |
| Studies | `/api/studies/` | CRUD + active, pagination |
| Insights | `/api/insights/` | CRUD + par etude |
| Reports | `/api/reports/` | CRUD + download PDF |
| Blog | `/api/blog/` | CRUD + public listing, publish |
| Newsletter | `/api/newsletter/` | subscribe, confirm, campaigns |
| Payments | `/api/payments/` | PayDunya checkout + callback |
| Dashboard | `/api/dashboard/` | stats |
| Contacts | `/api/contacts/` | formulaire de contact |

## Modeles de donnees

| Modele | Description |
|--------|-------------|
| User | Utilisateurs (email, plan, admin_role, equipe entreprise) |
| Study | Etudes de marche (titre, categorie, statut, embed URLs) |
| Insight | Insights lies aux etudes |
| Report | Rapports PDF par etude et plan |
| Subscription | Abonnements utilisateurs |
| BlogPost | Articles de blog/CMS avec SEO |
| NewsletterSubscriber | Abonnes newsletter |
| NewsletterCampaign | Campagnes email |
| Contact | Messages du formulaire de contact |
| VerificationCode | Codes 2FA temporaires |
| TokenBlacklist | Tokens JWT revoques (logout) |
| AuditLog | Journal d'audit des actions admin |

## RBAC

| Role | Acces |
|------|-------|
| `super_admin` | Tout |
| `admin_content` | Etudes, insights, rapports |
| `admin_studies` | Etudes uniquement |
| `admin_insights` | Insights uniquement |
| `admin_reports` | Rapports uniquement |

**Plans utilisateur :** `basic`, `professionnel`, `entreprise` (+ gestion equipe 5 membres max)

## Securite

- JWT avec claim `jti` (UUID v4) pour revocation individuelle
- Token blacklist (logout invalide le token)
- Validation mot de passe : 8+ caracteres, majuscule, minuscule, chiffre, caractere special
- Audit logging sur toutes les actions admin
- Rate limiting par IP (SlowAPI)
- CSRF protection via header `X-Requested-With`
- `max_length` sur tous les champs string des schemas
- Bandit SAST dans le CI

## Variables d'environnement

| Variable | Description | Requis |
|----------|-------------|--------|
| `DATABASE_URL` | URL PostgreSQL | Oui |
| `SECRET_KEY` | Cle secrete JWT | Oui |
| `RESEND_API_KEY` | API Resend (emails) | Oui |
| `PAYDUNYA_MASTER_KEY` | Cle PayDunya | Oui |
| `PAYDUNYA_PRIVATE_KEY` | Cle privee PayDunya | Oui |
| `PAYDUNYA_TOKEN` | Token PayDunya | Oui |
| `PAYDUNYA_MODE` | `test` ou `live` | Oui |
| `SENTRY_DSN` | DSN Sentry (monitoring) | Non |
| `ENVIRONMENT` | `development` / `production` | Non |
| `FRONTEND_URL` | URL du dashboard | Non |
| `ZAPIER_SECRET` | Secret webhook Zapier | Non |

## Deploiement

**Production :** Railway (auto-deploy depuis `main`)

Le `Procfile` execute `alembic upgrade head` avant de lancer `uvicorn`.

## Equipe

- **Organisation :** [Afrikalytics](https://github.com/Afrikalytics)
- **Email :** software@hcexecutive.net
- **Localisation :** Dakar, Senegal

---

&copy; 2024-2026 Afrikalytics AI. Tous droits reserves.
