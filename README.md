<p align="center">
  <h1 align="center">Afrikalytics API</h1>
  <p align="center">
    <strong>API REST haute performance pour la plateforme de Business Intelligence Afrikalytics</strong>
  </p>
  <p align="center">
    <a href="https://github.com/Afrikalytics/afrikalytics-api/actions/workflows/ci.yml"><img src="https://github.com/Afrikalytics/afrikalytics-api/actions/workflows/ci.yml/badge.svg" alt="CI"></a>
    <img src="https://img.shields.io/badge/FastAPI-0.104-009688?logo=fastapi" alt="FastAPI">
    <img src="https://img.shields.io/badge/Python-3.11+-3776AB?logo=python&logoColor=white" alt="Python">
    <img src="https://img.shields.io/badge/PostgreSQL-16-4169E1?logo=postgresql&logoColor=white" alt="PostgreSQL">
    <img src="https://img.shields.io/badge/SQLAlchemy-2.0-D71F00" alt="SQLAlchemy">
    <img src="https://img.shields.io/badge/Tests-182_pytest-green" alt="Tests">
    <img src="https://img.shields.io/badge/Deploy-Railway-0B0D0E?logo=railway" alt="Railway">
    <img src="https://img.shields.io/badge/Paiements-FCFA_%2F_Mobile_Money-orange" alt="FCFA">
  </p>
</p>

---

Backend de la plateforme **Afrikalytics AI**, un SaaS de Business Intelligence dedie a l'Afrique francophone. Cette API gere l'authentification, les abonnements, les etudes de marche, les insights strategiques, les rapports, le blog/CMS, la newsletter et les paiements en FCFA via mobile money (PayDunya).

> **Partie backend du monorepo Afrikalytics.** Le frontend associe se trouve dans [`afrikalytics-dashboard`](https://github.com/Afrikalytics/afrikalytics-dashboard).

## Fonctionnalites

| Domaine | Description |
|---------|-------------|
| **Authentification** | Inscription, login, 2FA par email, recuperation de mot de passe, logout avec revocation JWT |
| **Gestion utilisateurs** | Profils, changement de mot de passe, quotas, equipes entreprise |
| **Administration** | CRUD utilisateurs, roles, audit log des actions admin |
| **Etudes de marche** | CRUD complet, filtrage par statut, pagination |
| **Insights** | Analyses liees aux etudes, recommandations |
| **Rapports** | Gestion de rapports PDF, telechargement par plan |
| **Blog / CMS** | Articles avec SEO, brouillon/publication, categories |
| **Newsletter** | Inscription, confirmation, campagnes email |
| **Paiements** | Checkout PayDunya, callback, support FCFA/Orange Money/Wave/Free Money |
| **Dashboard** | Statistiques agregees en temps reel |
| **Contacts** | Formulaire de contact |
| **Monitoring** | Sentry pour le suivi des erreurs, audit log |

## Architecture

```
                        +-------------------+
                        |  Vercel (Frontend) |
                        |    Next.js 16      |
                        +---------+---------+
                                  |
                        REST API + JWT Bearer
                                  |
                        +---------v---------+
                        |  Railway (Backend) |
                        |   FastAPI 0.104    |
                        +-+-----+-----+---+-+
                          |     |     |   |
                    +-----+  +--+--+  |   +--------+
                    |        |     |  |            |
               PostgreSQL  Resend |  PayDunya   Sentry
                (donnees) (emails)|  (FCFA)   (monitoring)
                                  |
                               Zapier
                            (webhooks)
```

### Stack technique

| Couche | Technologie |
|--------|-------------|
| Framework | FastAPI 0.104 |
| Langage | Python 3.11+ avec type hints |
| ORM | SQLAlchemy 2.0 |
| Validation | Pydantic v2 |
| Base de donnees | PostgreSQL 16 |
| Migrations | Alembic |
| Auth | JWT HS256 (python-jose + bcrypt) |
| Rate limiting | SlowAPI (par IP) |
| Emails | Resend |
| Paiements | PayDunya (FCFA / Mobile Money) |
| Tests | pytest + httpx (182 tests) |
| Monitoring | Sentry |
| CI/CD | GitHub Actions (ruff, pytest, Bandit) |
| Deploy | Railway (Nixpacks) |

## Demarrage rapide

### Prerequis

- **Python** 3.11+
- **PostgreSQL** 16+ (ou Docker)

### Installation

```bash
# Cloner le repository
git clone https://github.com/Afrikalytics/afrikalytics-api.git
cd afrikalytics-api

# Creer l'environnement virtuel
python -m venv venv
source venv/bin/activate      # Linux / Mac
# venv\Scripts\activate       # Windows

# Installer les dependances
pip install -r requirements.txt

# Configurer l'environnement
cp .env.example .env
# Editer .env avec vos valeurs (DATABASE_URL, SECRET_KEY, etc.)

# Appliquer les migrations
alembic upgrade head

# Lancer le serveur
uvicorn main:app --reload --port 8000
```

L'API est accessible sur :

| URL | Description |
|-----|-------------|
| http://localhost:8000 | API |
| http://localhost:8000/docs | Swagger UI (documentation interactive) |
| http://localhost:8000/redoc | ReDoc (documentation alternative) |
| http://localhost:8000/health | Healthcheck |

### Avec Docker

```bash
docker compose up
```

Demarre **PostgreSQL 16**, **Redis 7** et l'**API** sur le port 8000.

## Tests

```bash
pytest --cov=app -v
```

**182 tests** couvrant les 11 domaines fonctionnels :

| Module | Tests | Couverture |
|--------|:-----:|------------|
| Users | 15 | Profil, mot de passe, quotas |
| Admin | 19 | CRUD utilisateurs, roles, audit |
| Studies | 18 | CRUD etudes, filtres, pagination |
| Insights | 20 | CRUD insights, liaison etudes |
| Reports | 25 | CRUD rapports, telechargement PDF |
| Dashboard | 10 | Stats agregees |
| Blog | 34 | CRUD articles, SEO, publication |
| Newsletter | 14 | Inscription, confirmation, campagnes |
| Contacts | 16 | Formulaire, validation |
| Payments | 6 | Checkout, callback (3 skipped — sandbox PayDunya) |

Le CI exige un minimum de **40% de couverture** pour merger.

## Structure du projet

```
afrikalytics-api/
├── main.py                      # App FastAPI, CORS, middleware, init Sentry
├── auth.py                      # JWT : create/decode tokens, hash/verify passwords
├── models.py                    # 12 modeles SQLAlchemy
├── database.py                  # Engine + session SQLAlchemy
├── app/
│   ├── routers/                 # 11 routers par domaine
│   │   ├── auth.py              #   Login, register, 2FA, reset password, logout
│   │   ├── users.py             #   Profil, mot de passe, equipe
│   │   ├── admin.py             #   CRUD admin, roles, audit log
│   │   ├── studies.py           #   CRUD etudes de marche
│   │   ├── insights.py          #   CRUD insights
│   │   ├── reports.py           #   CRUD rapports PDF
│   │   ├── blog.py              #   CRUD articles blog / CMS
│   │   ├── newsletter.py        #   Abonnements et campagnes
│   │   ├── payments.py          #   PayDunya checkout et callbacks
│   │   ├── dashboard.py         #   Statistiques agregees
│   │   └── contacts.py          #   Formulaire de contact
│   ├── schemas/                 # 11 schemas Pydantic v2
│   ├── services/
│   │   ├── email.py             #   Service email (Resend)
│   │   └── audit.py             #   Service audit log
│   ├── dependencies.py          # get_current_user, token blacklist
│   ├── permissions.py           # RBAC : check_admin_permission
│   └── utils.py                 # Validation mot de passe
├── alembic/                     # Migrations de base de donnees
│   └── versions/                #   Migration initiale (12 tables)
├── tests/                       # 182 tests pytest
│   ├── conftest.py              #   Fixtures, CSRF client, mocks
│   └── test_*.py                #   11 fichiers de tests
├── .github/workflows/
│   ├── ci.yml                   # Pipeline CI (ruff, pytest, Bandit)
│   └── claude-code.yml          # Integration Claude Code
├── Dockerfile                   # Python 3.11-slim + healthcheck
├── docker-compose.yml           # PostgreSQL + Redis + API
├── Procfile                     # alembic upgrade head && uvicorn
├── requirements.txt             # Dependances Python
└── .env.example                 # Template variables d'environnement
```

## Endpoints API

### 68 routes organisees en 11 domaines

#### Auth — `/api/auth/`

| Methode | Endpoint | Auth | Description |
|---------|----------|:----:|-------------|
| `POST` | `/register` | Non | Inscription utilisateur |
| `POST` | `/login` | Non | Connexion (retourne JWT) |
| `POST` | `/verify-code` | Non | Verification 2FA (code 6 chiffres) |
| `POST` | `/resend-code` | Non | Renvoyer le code 2FA |
| `POST` | `/forgot-password` | Non | Demande de reinitialisation |
| `POST` | `/reset-password` | Non | Confirmer la reinitialisation |
| `POST` | `/logout` | Oui | Revocation du token JWT |

#### Users — `/api/users/`

| Methode | Endpoint | Auth | Description |
|---------|----------|:----:|-------------|
| `GET` | `/me` | Oui | Profil utilisateur courant |
| `GET` | `/quota` | Oui | Quotas du plan |
| `PUT` | `/change-password` | Oui | Changer le mot de passe |
| `POST` | `/create` | Zapier | Creation via webhook Zapier |
| `GET` | `/equipe` | Oui | Membres de l'equipe (Entreprise) |

#### Admin — `/api/admin/`

| Methode | Endpoint | Auth | Description |
|---------|----------|:----:|-------------|
| `GET` | `/users` | Admin | Lister tous les utilisateurs |
| `POST` | `/users` | super_admin | Creer un administrateur |
| `PUT` | `/users/{id}` | super_admin | Modifier un utilisateur |
| `DELETE` | `/users/{id}` | super_admin | Supprimer un utilisateur |
| `GET` | `/roles` | Admin | Lister les roles disponibles |
| `PUT` | `/users/{id}/toggle-active` | Admin | Activer/desactiver un utilisateur |
| `GET` | `/audit-log` | super_admin | Journal d'audit |

#### Studies — `/api/studies/`

| Methode | Endpoint | Auth | Description |
|---------|----------|:----:|-------------|
| `GET` | `/` | Oui | Lister les etudes (pagine) |
| `GET` | `/active` | Oui | Etudes avec statut "Ouvert" |
| `GET` | `/{id}` | Oui | Detail d'une etude |
| `POST` | `/` | Admin | Creer une etude |
| `PUT` | `/{id}` | Admin | Modifier une etude |
| `DELETE` | `/{id}` | Admin | Supprimer une etude |

#### Insights, Reports, Blog, Newsletter, Payments, Dashboard, Contacts

Consulter la documentation interactive sur **`/docs`** (Swagger UI) pour la liste complete des endpoints.

## Modeles de donnees

| Modele | Description | Champs cles |
|--------|-------------|-------------|
| **User** | Utilisateurs | email, name, plan, admin_role, is_active, parent_user_id |
| **Study** | Etudes de marche | title, category, status (Ouvert/Ferme/Bientot), embed_url |
| **Insight** | Analyses strategiques | study_id, title, summary, key_findings, recommendations |
| **Report** | Rapports PDF | study_id, title, file_url, plan_required, download_count |
| **Subscription** | Abonnements | user_id, plan, status, start_date, end_date |
| **BlogPost** | Articles CMS | title, slug, content, category, status, meta SEO |
| **NewsletterSubscriber** | Abonnes newsletter | email, is_confirmed, confirmation_token |
| **NewsletterCampaign** | Campagnes email | subject, content, sent_count |
| **Contact** | Messages contact | name, email, subject, message |
| **VerificationCode** | Codes 2FA | user_id, code, expires_at |
| **TokenBlacklist** | Tokens revoques | jti, blacklisted_at |
| **AuditLog** | Journal d'audit | admin_id, action, target, details, timestamp |

## Controle d'acces (RBAC)

### Roles administrateur

| Role | Etudes | Insights | Rapports | Utilisateurs | Audit |
|------|:------:|:--------:|:--------:|:------------:|:-----:|
| `super_admin` | Oui | Oui | Oui | Oui | Oui |
| `admin_content` | Oui | Oui | Oui | Non | Non |
| `admin_studies` | Oui | Non | Non | Non | Non |
| `admin_insights` | Non | Oui | Non | Non | Non |
| `admin_reports` | Non | Non | Oui | Non | Non |

### Plans utilisateur

| Plan | Acces etudes | Rapports | Gestion equipe |
|------|:------------:|:--------:|:--------------:|
| `basic` | Limite | Non | Non |
| `professionnel` | Complet | Oui | Non |
| `entreprise` | Complet | Oui | Oui (5 membres max) |

## Securite

| Mesure | Detail |
|--------|--------|
| **JWT** | HS256 avec claim `jti` (UUID v4) pour revocation individuelle |
| **Token blacklist** | Logout invalide le token via `jti` |
| **Mots de passe** | bcrypt + validation stricte (8+ car., majuscule, minuscule, chiffre, special) |
| **Rate limiting** | SlowAPI par adresse IP |
| **CSRF** | Validation du header `X-Requested-With: XMLHttpRequest` |
| **Validation** | `max_length` sur tous les champs string des schemas Pydantic |
| **Audit log** | Journalisation de toutes les actions admin |
| **SAST** | Bandit dans le pipeline CI |
| **Monitoring** | Sentry en production |

## Variables d'environnement

| Variable | Description | Requis | Defaut |
|----------|-------------|:------:|--------|
| `DATABASE_URL` | URL PostgreSQL | Oui | — |
| `SECRET_KEY` | Cle secrete JWT | Oui | — |
| `RESEND_API_KEY` | API Resend (emails transactionnels) | Oui | — |
| `PAYDUNYA_MASTER_KEY` | Cle master PayDunya | Oui | — |
| `PAYDUNYA_PRIVATE_KEY` | Cle privee PayDunya | Oui | — |
| `PAYDUNYA_TOKEN` | Token PayDunya | Oui | — |
| `PAYDUNYA_MODE` | Mode PayDunya | Oui | `test` |
| `SENTRY_DSN` | DSN Sentry (monitoring) | Non | — |
| `ENVIRONMENT` | Environnement d'execution | Non | `development` |
| `FRONTEND_URL` | URL du dashboard (CORS + emails) | Non | — |
| `ZAPIER_SECRET` | Secret webhook Zapier | Non | — |
| `CRON_SECRET` | Secret pour le cron de verification abonnements | Non | — |
| `PORT` | Port du serveur | Non | `8000` |

## Deploiement

| Environnement | Plateforme | Builder | Declencheur |
|---------------|-----------|---------|-------------|
| Production | Railway | Nixpacks | Push sur `main` |

Le `Procfile` execute automatiquement les migrations Alembic avant de lancer le serveur :

```
web: alembic upgrade head && uvicorn main:app --host 0.0.0.0 --port $PORT
```

Le pipeline CI (GitHub Actions) execute : **Lint (ruff)** > **Tests (pytest)** > **Analyse de securite (Bandit)** avant chaque merge.

## Contribution

1. Creer une branche depuis `main` : `git checkout -b feat/ma-fonctionnalite`
2. Respecter les **conventional commits** en anglais (`feat:`, `fix:`, `docs:`, `refactor:`, `test:`, `chore:`)
3. S'assurer que `pytest` passe et que la couverture reste au-dessus de 40%
4. Ouvrir une Pull Request avec une description claire

## Equipe

| | |
|---|---|
| **Organisation** | [Afrikalytics](https://github.com/Afrikalytics) |
| **Email** | software@hcexecutive.net |
| **Localisation** | Dakar, Senegal |

---

<p align="center">
  <strong>Afrikalytics AI</strong> — Business Intelligence pour l'Afrique francophone<br>
  &copy; 2024-2026 Afrikalytics. Tous droits reserves.
</p>
