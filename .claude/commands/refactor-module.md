---
description: Extraire un domaine fonctionnel du monolithe main.py vers un module separe
argument_hint: <domaine: auth|users|admin|studies|insights|reports|blog|newsletter|payments|dashboard>
---

# Refactor Module Command

## Objectif
Extraire le domaine `$ARGUMENTS` du fichier monolithique `main.py` vers des modules separes.

## Etapes

### 1. Analyse
- Lire `main.py` et identifier tous les elements lies au domaine `$ARGUMENTS` :
  - Endpoints (routes FastAPI)
  - Schemas Pydantic (request/response models)
  - Logique metier (fonctions helper)
  - Dependencies (imports necessaires)
- Lister les dependances vers d'autres domaines

### 2. Extraction
Creer les fichiers suivants (si non existants) :

```
app/routers/$ARGUMENTS.py     # APIRouter avec les endpoints
app/schemas/$ARGUMENTS.py     # Pydantic models
app/services/$ARGUMENTS.py    # Logique metier (si necessaire)
```

### 3. Migration
1. Copier les endpoints dans le router
2. Copier les schemas dans le fichier schemas
3. Extraire la logique metier dans services
4. Mettre a jour les imports
5. Enregistrer le router dans `main.py` : `app.include_router(router, prefix="/api/$ARGUMENTS")`
6. Supprimer le code extrait de `main.py`

### 4. Verification
- [ ] Les URLs des endpoints n'ont pas change
- [ ] Les formats de reponse sont identiques
- [ ] Les imports sont corrects
- [ ] Pas de circular imports
- [ ] Le serveur demarre sans erreur : `uvicorn main:app --reload`

### 5. Resume
```
📦 Module extrait : $ARGUMENTS
─────────────────────────────
Endpoints migres  : X
Schemas extraits  : X
Lignes deplacees  : X
main.py reduit de : X lignes
Verification      : ✅ OK | ❌ Echec
```
