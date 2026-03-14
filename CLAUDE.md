# CLAUDE.md — Afrikalytics API (Backend FastAPI)

Ce fichier guide Claude Code pour le developpement du backend Afrikalytics.

## Project Overview

Backend API REST pour la plateforme Afrikalytics AI. Gere l'authentification, les abonnements, les etudes de marche, les insights, les rapports, le blog/CMS et les paiements.

## Development Commands

```bash
# Setup local
python -m venv venv
source venv/bin/activate          # Linux/Mac
# venv\Scripts\activate           # Windows
pip install -r requirements.txt
cp .env.example .env              # Configurer les variables

# Run
uvicorn main:app --reload --port 8000

# Docs API interactive
# http://localhost:8000/docs       (Swagger UI)
# http://localhost:8000/redoc      (ReDoc)
```

Pas de framework de test configure. Pas de linter configure. Pas de CI/CD.

## Architecture

**Stack :** FastAPI 0.104 + SQLAlchemy 2.0 + PostgreSQL 16 + Pydantic 2.5

**Structure actuelle (monolithe) :**
```
afrikalytics-api/
├── main.py           # 127KB — TOUT le code applicatif (endpoints, schemas, logique metier)
├── models.py         # Modeles SQLAlchemy (User, Study, Subscription, BlogPost, etc.)
├── auth.py           # JWT : hash_password, verify_password, create/decode_access_token
├── database.py       # Configuration SQLAlchemy (engine, session, Base)
├── requirements.txt  # Dependencies Python
├── .env.example      # Template variables d'environnement
├── Procfile          # Commande de lancement Railway
├── railway.json      # Configuration deploiement Railway
└── README.md
```

**Probleme majeur :** `main.py` est un fichier monolithique de 127KB contenant tous les endpoints, schemas Pydantic, et la logique metier. A refactorer en modules.

### Structure cible (refactoring)
```
afrikalytics-api/
├── app/
│   ├── __init__.py
│   ├── main.py              # App FastAPI + CORS + middleware
│   ├── config.py            # Settings (pydantic-settings)
│   ├── database.py          # Engine + session
│   ├── models/              # SQLAlchemy models
│   │   ├── user.py
│   │   ├── study.py
│   │   ├── subscription.py
│   │   ├── blog.py
│   │   └── newsletter.py
│   ├── schemas/             # Pydantic schemas
│   │   ├── auth.py
│   │   ├── user.py
│   │   ├── study.py
│   │   └── ...
│   ├── routers/             # APIRouter par domaine
│   │   ├── auth.py
│   │   ├── users.py
│   │   ├── admin.py
│   │   ├── studies.py
│   │   ├── insights.py
│   │   ├── reports.py
│   │   ├── blog.py
│   │   ├── newsletter.py
│   │   ├── payments.py
│   │   └── dashboard.py
│   ├── services/            # Logique metier
│   │   ├── email.py
│   │   ├── payment.py
│   │   └── ...
│   └── middleware/
│       ├── auth.py
│       └── rate_limit.py
├── tests/
├── alembic/                 # Migrations DB
├── requirements.txt
└── Procfile
```

## API Endpoints (42 routes)

### Auth (`/api/auth/`)
| Method | Path | Auth | Description |
|--------|------|------|-------------|
| POST | `/register` | Non | Inscription utilisateur |
| POST | `/login` | Non | Connexion (retourne JWT) |
| POST | `/verify-code` | Non | Verification 2FA (code 6 chiffres) |
| POST | `/resend-code` | Non | Renvoyer code 2FA |
| POST | `/forgot-password` | Non | Demande reset password |
| POST | `/reset-password` | Non | Confirmation reset password |

### Users (`/api/users/`)
| Method | Path | Auth | Description |
|--------|------|------|-------------|
| POST | `/create` | Zapier | Creation utilisateur (integration Zapier) |
| GET | `/me` | Oui | Profil utilisateur courant |
| GET | `/{user_id}` | Oui | Detail utilisateur |
| PUT | `/{user_id}/deactivate` | Admin | Desactiver utilisateur |
| PUT | `/change-password` | Oui | Changer mot de passe |

### Admin (`/api/admin/`)
| Method | Path | Auth | Description |
|--------|------|------|-------------|
| GET | `/roles` | Admin | Lister les roles |
| GET | `/users` | Admin | Lister tous les utilisateurs |
| POST | `/users` | super_admin | Creer admin |
| PUT | `/users/{id}` | super_admin | Modifier admin |
| DELETE | `/users/{id}` | super_admin | Supprimer utilisateur |

### Studies (`/api/studies/`)
| Method | Path | Auth | Description |
|--------|------|------|-------------|
| GET | `/` | Oui | Lister les etudes |
| GET | `/active` | Oui | Etudes actives |
| GET | `/{id}` | Oui | Detail etude |
| POST | `/` | Admin | Creer etude |
| PUT | `/{id}` | Admin | Modifier etude |
| DELETE | `/{id}` | Admin | Supprimer etude |

### Insights (`/api/insights/`)
| Method | Path | Auth | Description |
|--------|------|------|-------------|
| GET | `/` | Oui | Lister les insights |
| GET | `/study/{id}` | Oui | Insights par etude |
| GET | `/{id}` | Oui | Detail insight |
| POST | `/` | Admin | Creer insight |
| PUT | `/{id}` | Admin | Modifier insight |
| DELETE | `/{id}` | Admin | Supprimer insight |

### Reports, Blog, Newsletter, Payments, Dashboard
Voir le code source `main.py` pour la liste complete.

## Data Models

| Modele | Champs cles |
|--------|-------------|
| **User** | email, name, password_hash, plan (basic/pro/entreprise), admin_role, is_active |
| **Study** | title, description, category, status (Ouvert/Ferme/Bientot), embed_url |
| **Subscription** | user_id, plan, status (active/cancelled/expired), start/end_date |
| **Insight** | study_id, title, summary, key_findings, recommendations |
| **Report** | study_id, title, file_url, download_count |
| **BlogPost** | title, slug, content, category, status (draft/published), SEO fields |
| **NewsletterSubscriber** | email, status, confirmation_token, is_confirmed |

## RBAC

| Role | Permissions |
|------|-------------|
| `super_admin` | Acces total |
| `admin_content` | Etudes, insights, rapports |
| `admin_studies` | Etudes uniquement |
| `admin_insights` | Insights uniquement |
| `admin_reports` | Rapports uniquement |

## Plans utilisateur
- `basic` — Acces limite
- `professionnel` — Acces complet
- `entreprise` — + gestion equipe (5 membres max, `parent_user_id`)

## Environment Variables

| Variable | Description | Requis |
|----------|-------------|--------|
| `DATABASE_URL` | URL PostgreSQL | Oui (Railway auto) |
| `SECRET_KEY` | Cle JWT (changer en prod!) | Oui |
| `RESEND_API_KEY` | Cle API Resend (emails) | Oui |
| `PAYDUNYA_MASTER_KEY` | Cle PayDunya | Oui (paiements) |
| `PAYDUNYA_PRIVATE_KEY` | Cle privee PayDunya | Oui (paiements) |
| `PAYDUNYA_TOKEN` | Token PayDunya | Oui (paiements) |
| `PAYDUNYA_MODE` | `test` ou `live` | Oui |
| `ZAPIER_SECRET` | Secret webhook Zapier | Optionnel |
| `ENVIRONMENT` | `development` ou `production` | Optionnel |

## Security Notes

- **JWT :** HS256, expiry 7j, secret key depuis env var (fallback insecure a supprimer)
- **Passwords :** bcrypt avec salt
- **Rate limiting :** SlowAPI par IP
- **CORS :** Configure pour les domaines de production et localhost
- **Attention :** Le fallback `SECRET_KEY = "your-super-secret-key-change-in-production"` dans `auth.py` est une faille critique a corriger

## Coding Conventions

- Python 3.11+ avec type hints
- Pydantic v2 pour la validation
- SQLAlchemy 2.0 style (select, not query)
- Noms de variables et commentaires en anglais
- Docstrings pour les endpoints
- HTTP status codes corrects (201 pour creation, 404 pour not found, etc.)
- Conventional commits en anglais

## Deployment

- **Production :** Railway (auto-deploy depuis GitHub)
- **Builder :** Nixpacks
- **Healthcheck :** `GET /health`
- **Start :** `uvicorn main:app --host 0.0.0.0 --port $PORT`
