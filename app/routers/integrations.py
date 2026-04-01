"""
Router pour les intégrations SDK et API keys.
5 endpoints : créer/lister/révoquer API keys, embed étude, embed widget.

Security model
--------------
- API keys are NEVER stored in plaintext.  Only the SHA-256 hash is
  persisted (``api_keys.key_hash``).  The first 8 chars (``key_prefix``)
  are kept for display in the user dashboard.
- The full raw key is returned ONCE in the creation response body (HTTP 201).
  After that it is unrecoverable — users must revoke and regenerate.
- Validation on inbound ``X-Api-Key`` headers hashes the provided value and
  compares it against ``key_hash`` using a constant-time comparison (via the
  ``app.security`` module) to prevent timing side-channel attacks.
"""
import html as html_module
import json
import logging
from datetime import datetime, timezone
from typing import List, Optional

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request
from fastapi.responses import HTMLResponse
from sqlalchemy import select, func as sa_func
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import get_current_user
from app.models import ApiKey, Study, User
from app.rate_limit import limiter
from app.schemas.integrations import (
    ApiKeyCreate,
    ApiKeyCreatedResponse,
    ApiKeyListResponse,
    ApiKeyResponse,
    EmbedDataResponse,
    EmbedWidgetResponse,
)
from app.security import generate_api_key, hash_api_key, verify_api_key
from app.services.audit import log_api_key_created, log_api_key_revoked

logger = logging.getLogger(__name__)

router = APIRouter(tags=["integrations"])

# Maximum API keys per user
MAX_KEYS_PER_USER = 10


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _validate_api_key(
    db: Session,
    raw_key_header: str,
    request: Request,
    required_permission: str = "read",
) -> ApiKey:
    """Validate an API key from the ``X-Api-Key`` header.

    Process
    -------
    1. Hash the inbound value with SHA-256.
    2. Look up the row by ``key_hash`` (indexed column).
    3. Verify permissions and allowed origins.
    4. Update ``last_used_at`` and flush (caller commits).

    The raw key is never logged, echoed in error messages, or compared
    using a non-constant-time function.
    """
    if not raw_key_header:
        raise HTTPException(
            status_code=401,
            detail="API key manquante. Ajoutez le header X-Api-Key.",
        )

    # Compute the hash of the inbound key for DB lookup
    incoming_hash = hash_api_key(raw_key_header)

    api_key = db.execute(
        select(ApiKey).where(
            ApiKey.key_hash == incoming_hash,
            ApiKey.is_active.is_(True),
        )
    ).scalar_one_or_none()

    if not api_key:
        # Use a generic message — do not reveal whether the key exists
        raise HTTPException(status_code=401, detail="API key invalide ou révoquée.")

    # Double-check with constant-time comparison (defence-in-depth)
    if not verify_api_key(raw_key_header, api_key.key_hash):
        raise HTTPException(status_code=401, detail="API key invalide ou révoquée.")

    # Check permissions
    permissions = api_key.permissions or ["read"]
    if required_permission not in permissions:
        raise HTTPException(
            status_code=403,
            detail=f"Permission '{required_permission}' non accordée pour cette API key.",
        )

    # Check allowed origins
    origin = request.headers.get("origin")
    if api_key.allowed_origins and origin:
        if origin not in api_key.allowed_origins:
            raise HTTPException(
                status_code=403,
                detail=f"Origine '{origin}' non autorisée pour cette API key.",
            )

    # Record usage timestamp (flush within the request transaction)
    api_key.last_used_at = datetime.now(timezone.utc)
    db.flush()

    return api_key


# ---------------------------------------------------------------------------
# API Key CRUD Endpoints
# ---------------------------------------------------------------------------

@router.post("/api/integrations/keys", response_model=ApiKeyCreatedResponse, status_code=201)
@limiter.limit("10/minute")
def create_api_key(
    request: Request,
    payload: ApiKeyCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Créer une nouvelle API key pour l'utilisateur courant.

    La clé complète n'est visible qu'une seule fois dans la réponse de
    création.  Elle n'est jamais stockée en clair.  Après la création,
    seul le préfixe (8 caractères) est affiché dans le tableau de bord.

    Plan requis : ``professionnel`` ou ``entreprise``.
    """
    # Enforce plan restriction
    if current_user.plan not in ("professionnel", "entreprise"):
        raise HTTPException(
            status_code=403,
            detail="Les intégrations SDK nécessitent un plan Professionnel ou Entreprise.",
        )

    # Enforce per-user key limit
    existing_count = db.execute(
        select(sa_func.count(ApiKey.id)).where(ApiKey.user_id == current_user.id)
    ).scalar() or 0

    if existing_count >= MAX_KEYS_PER_USER:
        raise HTTPException(
            status_code=400,
            detail=f"Limite de {MAX_KEYS_PER_USER} API keys atteinte. Révoquez une clé existante.",
        )

    # Validate permissions (allowlist)
    valid_permissions = {"read", "write"}
    for perm in payload.permissions:
        if perm not in valid_permissions:
            raise HTTPException(
                status_code=400,
                detail=(
                    f"Permission invalide : '{perm}'. "
                    f"Valeurs autorisées : {', '.join(sorted(valid_permissions))}"
                ),
            )

    # Generate key — raw_key is returned to the user ONCE and never persisted
    raw_key, key_hash, key_prefix = generate_api_key()

    api_key = ApiKey(
        user_id=current_user.id,
        key_hash=key_hash,
        key_prefix=key_prefix,
        name=payload.name,
        is_active=True,
        allowed_origins=payload.allowed_origins,
        permissions=payload.permissions,
    )
    db.add(api_key)
    db.flush()  # assign api_key.id before audit log

    # Audit: log prefix, never the raw key
    log_api_key_created(
        db,
        user_id=current_user.id,
        key_name=payload.name,
        key_prefix=key_prefix,
        request=request,
    )

    db.commit()
    db.refresh(api_key)

    # Only log name + prefix — the raw key must not appear in any log line
    logger.info(
        "api_key_created name='%s' prefix=%s user=%s",
        payload.name,
        key_prefix,
        current_user.email,
    )

    # Build response — include the raw key here (it will never be shown again)
    return ApiKeyCreatedResponse(
        id=api_key.id,
        name=api_key.name,
        key=raw_key,          # full key — only in this creation response
        key_prefix=key_prefix,
        is_active=api_key.is_active,
        allowed_origins=api_key.allowed_origins,
        permissions=api_key.permissions or ["read"],
        last_used_at=api_key.last_used_at,
        created_at=api_key.created_at,
    )


@router.get("/api/integrations/keys", response_model=ApiKeyListResponse)
@limiter.limit("30/minute")
def list_api_keys(
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Lister toutes les API keys de l'utilisateur courant.

    Seul le préfixe (8 caractères) est retourné — jamais la clé complète
    ni le hash.
    """
    keys = db.execute(
        select(ApiKey)
        .where(ApiKey.user_id == current_user.id)
        .order_by(ApiKey.created_at.desc())
    ).scalars().all()

    key_responses = [
        ApiKeyResponse(
            id=k.id,
            name=k.name,
            key_prefix=k.key_prefix,
            is_active=k.is_active,
            allowed_origins=k.allowed_origins,
            permissions=k.permissions or ["read"],
            last_used_at=k.last_used_at,
            created_at=k.created_at,
        )
        for k in keys
    ]

    return ApiKeyListResponse(keys=key_responses, total=len(key_responses))


@router.delete("/api/integrations/keys/{key_id}", status_code=200)
@limiter.limit("10/minute")
def revoke_api_key(
    request: Request,
    key_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Révoquer (désactiver) une API key.

    L'action est irréversible.  La clé ne peut pas être réactivée ;
    l'utilisateur doit en créer une nouvelle.
    """
    api_key = db.execute(
        select(ApiKey).where(
            ApiKey.id == key_id,
            ApiKey.user_id == current_user.id,
        )
    ).scalar_one_or_none()

    if not api_key:
        raise HTTPException(status_code=404, detail="API key non trouvée.")

    if not api_key.is_active:
        raise HTTPException(status_code=400, detail="Cette API key est déjà révoquée.")

    api_key.is_active = False
    db.flush()

    log_api_key_revoked(
        db,
        user_id=current_user.id,
        key_id=key_id,
        key_name=api_key.name,
        key_prefix=api_key.key_prefix,
        request=request,
    )

    db.commit()

    logger.info(
        "api_key_revoked name='%s' id=%d prefix=%s user=%s",
        api_key.name,
        key_id,
        api_key.key_prefix,
        current_user.email,
    )

    return {"detail": f"API key '{api_key.name}' révoquée avec succès."}


# ---------------------------------------------------------------------------
# Embed Endpoints (auth via X-Api-Key header)
# ---------------------------------------------------------------------------

@router.get("/api/integrations/embed/{study_id}", response_model=EmbedDataResponse)
@limiter.limit("60/minute")
def get_embed_data(
    request: Request,
    study_id: int,
    x_api_key: Optional[str] = Header(None, alias="X-Api-Key"),
    db: Session = Depends(get_db),
):
    """Retourner les données d'une étude pour l'embed SDK.

    Authentification via le header ``X-Api-Key``.
    """
    _validate_api_key(db, x_api_key, request, required_permission="read")

    study = db.execute(
        select(Study).where(Study.id == study_id, Study.is_active.is_(True))
    ).scalar_one_or_none()

    if not study:
        raise HTTPException(status_code=404, detail="Étude non trouvée ou inactive.")

    db.commit()  # commit the last_used_at update from _validate_api_key

    dataset = study.dataset
    return EmbedDataResponse(
        study_id=study.id,
        title=study.title,
        description=study.description,
        category=study.category,
        data=dataset.data if dataset else None,
        columns=dataset.columns if dataset else None,
        row_count=dataset.row_count if dataset else None,
    )


@router.get("/api/integrations/embed/{study_id}/widget/{widget_type}")
@limiter.limit("60/minute")
def get_embed_widget(
    request: Request,
    study_id: int,
    widget_type: str,
    theme: str = Query("light", regex="^(light|dark)$"),
    x_api_key: Optional[str] = Header(None, alias="X-Api-Key"),
    db: Session = Depends(get_db),
):
    """Retourner les données formatées pour un widget spécifique.

    Peut retourner du JSON (API calls) ou du HTML (iframe embed) selon
    le header ``Accept``.
    """
    _validate_api_key(db, x_api_key, request, required_permission="read")

    study = db.execute(
        select(Study).where(Study.id == study_id, Study.is_active.is_(True))
    ).scalar_one_or_none()

    if not study:
        raise HTTPException(status_code=404, detail="Étude non trouvée ou inactive.")

    valid_widgets = {
        "bar", "line", "area", "pie", "donut", "scatter",
        "radar", "funnel", "stat-card", "table", "kpi",
    }
    if widget_type not in valid_widgets:
        raise HTTPException(
            status_code=400,
            detail=(
                f"Type de widget invalide : '{widget_type}'. "
                f"Types disponibles : {', '.join(sorted(valid_widgets))}"
            ),
        )

    db.commit()  # commit the last_used_at update from _validate_api_key

    # Return HTML for iframe embeds, JSON for API calls
    accept = request.headers.get("accept", "")
    if "text/html" in accept:
        html_content = _render_widget_html(study, widget_type, theme)
        return HTMLResponse(content=html_content)

    dataset = study.dataset
    return EmbedWidgetResponse(
        study_id=study.id,
        widget_type=widget_type,
        title=study.title,
        data=dataset.data if dataset else None,
        columns=dataset.columns if dataset else None,
        config={"type": widget_type, "theme": theme},
        theme=theme,
    )


# ---------------------------------------------------------------------------
# Widget HTML renderer
# ---------------------------------------------------------------------------

def _render_widget_html(study: Study, widget_type: str, theme: str) -> str:
    """Render a self-contained HTML page for iframe embedding with Chart.js."""
    safe_title = html_module.escape(study.title)
    bg_color = "#ffffff" if theme == "light" else "#1f2937"
    text_color = "#111827" if theme == "light" else "#f9fafb"
    grid_color = "rgba(0,0,0,0.1)" if theme == "light" else "rgba(255,255,255,0.1)"

    dataset = study.dataset
    chart_data = dataset.data if dataset else []
    columns = dataset.columns if dataset else []
    label_col = columns[0] if columns else "label"
    value_cols = columns[1:] if len(columns) > 1 else []

    labels = [str(row.get(label_col, "")) for row in chart_data[:50]] if chart_data else []
    datasets = []
    colors = [
        "#2563eb", "#7c3aed", "#059669", "#d97706",
        "#dc2626", "#0891b2", "#4f46e5", "#be185d",
    ]
    for i, col in enumerate(value_cols[:8]):
        datasets.append({
            "label": col,
            "data": [row.get(col, 0) for row in chart_data[:50]],
            "backgroundColor": colors[i % len(colors)] + "99",
            "borderColor": colors[i % len(colors)],
            "borderWidth": 1,
        })

    chart_type_map = {
        "bar": "bar", "line": "line", "area": "line",
        "pie": "pie", "donut": "doughnut",
        "scatter": "scatter", "radar": "radar",
    }
    js_chart_type = chart_type_map.get(widget_type, "bar")

    chart_config = {
        "type": js_chart_type,
        "data": {"labels": labels, "datasets": datasets},
        "options": {
            "responsive": True,
            "maintainAspectRatio": False,
            "plugins": {
                "title": {"display": True, "text": safe_title, "color": text_color},
                "legend": {"labels": {"color": text_color}},
            },
            "scales": {} if js_chart_type in ("pie", "doughnut", "radar") else {
                "x": {"ticks": {"color": text_color}, "grid": {"color": grid_color}},
                "y": {"ticks": {"color": text_color}, "grid": {"color": grid_color}},
            },
        },
    }

    if widget_type == "area":
        for ds in chart_config["data"]["datasets"]:
            ds["fill"] = True

    config_json = json.dumps(chart_config, ensure_ascii=False)

    return f"""<!DOCTYPE html>
<html lang="fr">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{safe_title} — Afrikalytics Widget</title>
<script src="https://cdn.jsdelivr.net/npm/chart.js@4/dist/chart.umd.min.js"></script>
<style>
  * {{ margin: 0; padding: 0; box-sizing: border-box; }}
  body {{ background: {bg_color}; font-family: system-ui, -apple-system, sans-serif; padding: 16px; height: 100vh; }}
  .container {{ width: 100%; height: calc(100vh - 32px); position: relative; }}
  .powered {{ text-align: center; font-size: 11px; color: #9ca3af; margin-top: 8px; }}
  .powered a {{ color: #2563eb; text-decoration: none; }}
</style>
</head>
<body>
<div class="container">
  <canvas id="chart"></canvas>
</div>
<div class="powered">Propulsé par <a href="https://afrikalytics.com" target="_blank" rel="noopener">Afrikalytics</a></div>
<script>
  const ctx = document.getElementById('chart').getContext('2d');
  new Chart(ctx, {config_json});
</script>
</body>
</html>"""
