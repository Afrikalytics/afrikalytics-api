# 🚀 Afrikalytics API

Backend API pour Afrikalytics AI - Intelligence d'Affaires pour l'Afrique

## 📁 Structure

```
afrikalytics-api/
├── main.py           # Application FastAPI principale
├── database.py       # Configuration base de données
├── models.py         # Modèles SQLAlchemy
├── auth.py           # Authentification JWT
├── requirements.txt  # Dépendances Python
├── Procfile          # Commande de démarrage Railway
├── railway.json      # Configuration Railway
└── .env.example      # Variables d'environnement exemple
```

## 🔧 Installation Locale

```bash
# 1. Créer un environnement virtuel
python -m venv venv
source venv/bin/activate  # Linux/Mac
venv\Scripts\activate     # Windows

# 2. Installer les dépendances
pip install -r requirements.txt

# 3. Copier les variables d'environnement
cp .env.example .env

# 4. Lancer le serveur
uvicorn main:app --reload
```

Le serveur sera accessible sur : **http://localhost:8000**

Documentation API : **http://localhost:8000/docs**

## 🚂 Déploiement Railway

1. Créer un compte sur [Railway](https://railway.app)
2. Connecter GitHub
3. New Project → Deploy from GitHub repo
4. Sélectionner `afrikalytics-api`
5. Ajouter PostgreSQL (Add Plugin → PostgreSQL)
6. Railway déploiera automatiquement !

### Variables d'environnement Railway

Dans Railway → Variables, ajouter :

```
SECRET_KEY=votre-clé-secrète-très-longue
ZAPIER_SECRET=votre-secret-zapier
ENVIRONMENT=production
```

## 📚 Endpoints API

| Méthode | Endpoint | Description |
|---------|----------|-------------|
| GET | `/` | Info API |
| GET | `/health` | Health check |
| POST | `/api/users/create` | Créer user (Zapier) |
| POST | `/api/auth/login` | Connexion |
| GET | `/api/users/me` | User connecté |
| PUT | `/api/users/{id}/deactivate` | Désactiver user |

## 🔗 Workflow Zapier

1. **Trigger:** WooCommerce New Order
2. **Action:** POST vers `/api/users/create`

```json
{
  "email": "user@example.com",
  "name": "Jean Dupont",
  "plan": "professional",
  "order_id": "12345"
}
```

Headers:
```
X-Zapier-Secret: votre-secret-zapier
```

## 👥 Équipe

- **Email:** software@hcexecutive.net
- **Localisation:** Dakar, Sénégal

---

© 2024 Afrikalytics AI. Tous droits réservés.
