# Skill: Document API Endpoint

Documente un endpoint FastAPI existant avec OpenAPI metadata.

## Processus

1. Lire le fichier router concerne dans `app/routers/`
2. Pour chaque endpoint :
   - Ajouter `summary` et `description` au decorateur
   - Ajouter `response_model` si manquant
   - Ajouter `status_code` explicite
   - Ajouter `tags` pour le regroupement Swagger
3. Lire le schema Pydantic associe dans `app/schemas/`
4. Pour chaque champ du schema :
   - Ajouter `Field(description="...")` si manquant
   - Ajouter des exemples via `json_schema_extra`
5. Verifier que `http://localhost:8000/docs` affiche correctement

## Exemple

```python
@router.post(
    "/",
    response_model=StudyResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Creer une etude",
    description="Cree une nouvelle etude de marche. Necessite le role admin_studies.",
    tags=["Studies"]
)
async def create_study(study: StudyCreate, current_user: User = Depends(get_current_user)):
    ...
```
