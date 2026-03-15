from datetime import datetime, timezone

import sentry_sdk
from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse
from sentry_sdk.integrations.fastapi import FastApiIntegration
from sentry_sdk.integrations.sqlalchemy import SqlalchemyIntegration
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from starlette.middleware.base import BaseHTTPMiddleware

from app.config import get_settings
from app.rate_limit import limiter
from app.routers.admin import router as admin_router
from app.routers.auth import router as auth_router
from app.routers.blog import router as blog_router
from app.routers.contacts import router as contacts_router
from app.routers.dashboard import router as dashboard_router
from app.routers.insights import router as insights_router
from app.routers.newsletter import router as newsletter_router
from app.routers.payments import router as payments_router
from app.routers.reports import router as reports_router
from app.routers.studies import router as studies_router
from app.routers.users import router as users_router
from app.database import engine  # noqa: F401 — kept for potential direct usage
from app.models import Base  # noqa: F401 — kept so models are registered

settings = get_settings()

# Initialize Sentry
if settings.sentry_dsn:
    sentry_sdk.init(
        dsn=settings.sentry_dsn,
        integrations=[
            FastApiIntegration(),
            SqlalchemyIntegration(),
        ],
        traces_sample_rate=0.1,  # 10% des transactions
        profiles_sample_rate=0.1,
        environment=settings.environment,
        release=f"afrikalytics-api@{settings.railway_git_commit_sha}",
        send_default_pii=False,  # RGPD : pas de PII par defaut
    )

# Database tables are managed by Alembic migrations
# Run: alembic upgrade head
# For existing databases: alembic stamp head

app = FastAPI(
    title="Afrikalytics API",
    description=(
        "Backend API pour Afrikalytics AI - Intelligence d'Affaires pour l'Afrique.\n\n"
        "**Versioning:** All endpoints are available under `/api/v1/`. "
        "Legacy `/api/` paths redirect to `/api/v1/` with HTTP 307."
    ),
    version="1.0.0",
)

# Rate limiter
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)


# --- Security Headers Middleware ---
# Added BEFORE other middlewares so it executes AFTER them (FastAPI reverse order),
# ensuring security headers are present on every response.
@app.middleware("http")
async def security_headers_middleware(request: Request, call_next):
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["X-XSS-Protection"] = "1; mode=block"
    response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
    return response


# --- API Versioning Middleware ---
# Rewrite /api/v1/... to /api/... internally so existing route decorators match.
# This allows clients to use the versioned URL (/api/v1/...) while keeping
# route definitions unchanged in individual routers.
@app.middleware("http")
async def api_version_rewrite(request: Request, call_next):
    path = request.url.path
    if path.startswith("/api/v1/"):
        new_path = "/api/" + path[len("/api/v1/"):]
        request.scope["path"] = new_path
    return await call_next(request)


# --- Backward-Compatibility Redirect ---
# Redirect legacy /api/... requests (without version prefix) to /api/v1/...
# Uses 307 Temporary Redirect to preserve the HTTP method (POST, PUT, DELETE, etc.).
# External webhook callbacks are exempt (providers may not follow POST redirects).
_REDIRECT_EXEMPT_PATHS = (
    "/api/paydunya/webhook",
    "/api/newsletter/confirm",
    "/api/newsletter/unsubscribe",
)


@app.middleware("http")
async def api_version_redirect(request: Request, call_next):
    path = request.url.path
    # Redirect /api/xxx to /api/v1/xxx, but NOT /api/v1/xxx (already versioned)
    # and NOT exempt paths (external webhooks/callbacks)
    if path.startswith("/api/") and not path.startswith("/api/v1/"):
        if not any(path.startswith(p) for p in _REDIRECT_EXEMPT_PATHS):
            new_path = "/api/v1/" + path[len("/api/"):]
            # Preserve query string if present
            query = request.url.query
            redirect_url = new_path + (f"?{query}" if query else "")
            return RedirectResponse(url=redirect_url, status_code=307)
    return await call_next(request)


# --- CSRF Protection Middleware ---
# Require X-Requested-With header on state-changing requests (POST, PUT, DELETE, PATCH).
# Browsers block cross-origin custom headers unless explicitly allowed by CORS preflight,
# so this acts as a lightweight CSRF guard (double-submit header pattern).
class CSRFMiddleware(BaseHTTPMiddleware):
    EXEMPT_PATHS = (
        "/api/paydunya/webhook",
        "/api/newsletter/confirm",
        "/api/newsletter/unsubscribe",
        "/api/v1/paydunya/webhook",
        "/api/v1/newsletter/confirm",
        "/api/v1/newsletter/unsubscribe",
    )

    async def dispatch(self, request: Request, call_next):
        if request.method in ("POST", "PUT", "DELETE", "PATCH"):
            path = request.url.path
            exempt = any(path.startswith(p) for p in self.EXEMPT_PATHS)
            if not exempt:
                xrw = request.headers.get("x-requested-with", "")
                if xrw != "XMLHttpRequest":
                    return Response(
                        content='{"detail":"Missing or invalid X-Requested-With header"}',
                        status_code=403,
                        media_type="application/json",
                    )
        response = await call_next(request)
        return response


app.add_middleware(CSRFMiddleware)

# CORS — restricted to known origins only (no wildcard)
# Use ALLOWED_ORIGINS env var (comma-separated) for flexibility, with sensible defaults.
_default_origins = [
    "https://afrikalytics-dashboard.vercel.app",
    "https://afrikalytics.com",
    "https://www.afrikalytics.com",
    "https://dashboard.afrikalytics.com",
    "https://afrikalytics.vercel.app",
    "https://afrikalytics-website.vercel.app",
    "http://localhost:3000",
]

if settings.allowed_origins:
    allowed_origins = [o.strip() for o in settings.allowed_origins.split(",") if o.strip()]
else:
    allowed_origins = list(_default_origins)

# Add FRONTEND_URL / NEXT_PUBLIC_API_URL origin if set and not already present
for _extra in (settings.frontend_url, settings.next_public_api_url):
    if _extra and _extra not in allowed_origins:
        allowed_origins.append(_extra)

# Regex to allow only Afrikalytics Vercel preview deployments (https://afrikalytics*.vercel.app)
_origin_regex = r"https://afrikalytics[a-zA-Z0-9\-]*\.vercel\.app"

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_origin_regex=_origin_regex,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "X-Requested-With"],
)

# Enregistrer les routers
app.include_router(auth_router)
app.include_router(users_router)
app.include_router(admin_router)
app.include_router(studies_router)
app.include_router(dashboard_router)
app.include_router(insights_router)
app.include_router(reports_router)
app.include_router(contacts_router)
app.include_router(blog_router)
app.include_router(newsletter_router)
app.include_router(payments_router)


# Routes racine
@app.get("/")
def read_root():
    return {
        "message": "Bienvenue sur l'API Afrikalytics AI",
        "version": "1.0.0",
        "api_version": "v1",
        "status": "online",
        "docs": "/docs",
        "endpoints": "/api/v1/"
    }


@app.get("/health")
def health_check():
    return {"status": "healthy", "timestamp": datetime.now(timezone.utc)}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=settings.port)
