# Skill: Explore API Codebase

Exploration approfondie du code backend pour comprendre l'architecture et les dependances.

## Processus

1. **Structure** : Lister `app/routers/`, `app/schemas/`, `app/services/`, `models.py`
2. **Endpoints** : Compter et lister tous les decorateurs `@router.*` dans chaque router
3. **Models** : Lister toutes les classes SQLAlchemy dans `models.py`
4. **Schemas** : Lister tous les schemas Pydantic par domaine
5. **Dependencies** : Analyser `app/dependencies.py` et `app/permissions.py`
6. **Services** : Lister les services dans `app/services/`
7. **Config** : Verifier `database.py`, `auth.py`, `.env.example`
8. **Securite** : Scanner les patterns dangereux (hardcoded secrets, SQL raw, etc.)

## Output

Generer un rapport markdown avec :
- Nombre total d'endpoints par router
- Nombre de models et schemas
- Couverture des type hints
- Problemes detectes (securite, qualite)
- Recommandations d'amelioration
