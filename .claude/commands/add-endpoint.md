---
description: Ajouter un nouvel endpoint API en suivant les conventions du projet
argument_hint: <METHOD /api/path - description>
---

# Add Endpoint Command

## Objectif
Creer un nouvel endpoint API : `$ARGUMENTS`

## Etapes

### 1. Analyse
- Parser la specification : methode HTTP, path, description
- Identifier le domaine fonctionnel (auth, users, studies, etc.)
- Verifier qu'aucun endpoint existant ne fait deja la meme chose

### 2. Implementation

#### Schema Pydantic (si POST/PUT)
```python
from pydantic import BaseModel, Field

class EndpointRequest(BaseModel):
    # Definir les champs avec validation
    field: str = Field(..., min_length=1, max_length=255)

class EndpointResponse(BaseModel):
    # Definir la reponse
    id: int
    message: str
```

#### Endpoint
```python
@app.post("/api/path", status_code=201, response_model=EndpointResponse)
async def endpoint_name(
    request: EndpointRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)  # si auth requise
):
    """Description de l'endpoint."""
    # Implementation
    pass
```

### 3. Checklist
- [ ] Pydantic schema pour validation input
- [ ] Auth required si endpoint protege
- [ ] RBAC check si endpoint admin
- [ ] Status code HTTP correct (200, 201, 204, 400, 401, 403, 404)
- [ ] Gestion des erreurs (try/except, HTTPException)
- [ ] Rate limiting si endpoint sensible
- [ ] Type hints sur tous les parametres

### 4. Documentation
- L'endpoint apparait dans Swagger UI (`/docs`)
- Docstring decrit le comportement
- Response model documente la reponse

### 5. Impact frontend
Si ce nouvel endpoint sera consomme par le dashboard, noter :
```
📡 Nouvel endpoint cree : [METHOD] /api/path
Frontend : a integrer dans afrikalytics-dashboard
```
