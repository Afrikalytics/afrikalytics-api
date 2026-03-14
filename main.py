from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.base import BaseHTTPMiddleware
from datetime import datetime
import os

import sentry_sdk
from sentry_sdk.integrations.fastapi import FastApiIntegration
from sentry_sdk.integrations.sqlalchemy import SqlalchemyIntegration

# Initialize Sentry
sentry_dsn = os.getenv("SENTRY_DSN")
if sentry_dsn:
    sentry_sdk.init(
        dsn=sentry_dsn,
        integrations=[
            FastApiIntegration(),
            SqlalchemyIntegration(),
        ],
        traces_sample_rate=0.1,  # 10% des transactions
        profiles_sample_rate=0.1,
        environment=os.getenv("ENVIRONMENT", "development"),
        release=f"afrikalytics-api@{os.getenv('RAILWAY_GIT_COMMIT_SHA', 'local')}",
        send_default_pii=False,  # RGPD : pas de PII par defaut
    )

# Rate limiting
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from app.rate_limit import limiter

from database import engine  # noqa: F401 — kept for potential direct usage
from models import Base  # noqa: F401 — kept so models are registered

# Routers modulaires
from app.routers.auth import router as auth_router
from app.routers.users import router as users_router
from app.routers.admin import router as admin_router
from app.routers.studies import router as studies_router
from app.routers.dashboard import router as dashboard_router
from app.routers.insights import router as insights_router
from app.routers.reports import router as reports_router
from app.routers.contacts import router as contacts_router
from app.routers.blog import router as blog_router
from app.routers.newsletter import router as newsletter_router
from app.routers.payments import router as payments_router

# Database tables are managed by Alembic migrations
# Run: alembic upgrade head
# For existing databases: alembic stamp head

app = FastAPI(
    title="Afrikalytics API",
    description="Backend API pour Afrikalytics AI - Intelligence d'Affaires pour l'Afrique",
    version="1.0.0"
)

# Rate limiter
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)


# --- CSRF Protection Middleware ---
# Require X-Requested-With header on state-changing requests (POST, PUT, DELETE, PATCH).
# Browsers block cross-origin custom headers unless explicitly allowed by CORS preflight,
# so this acts as a lightweight CSRF guard (double-submit header pattern).
class CSRFMiddleware(BaseHTTPMiddleware):
    EXEMPT_PATHS = (
        "/api/paydunya/webhook",
        "/api/newsletter/confirm",
        "/api/newsletter/unsubscribe",
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
allowed_origins = [
    os.getenv("FRONTEND_URL", "https://afrikalytics.vercel.app"),
    "https://afrikalytics.com",
    "https://www.afrikalytics.com",
    "https://afrikalytics-website.vercel.app",
    "https://dashboard.afrikalytics.com",
    "https://afrikalytics-dashboard.vercel.app",
    "http://localhost:3000",
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*", "X-Requested-With"],
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
        "status": "online",
        "docs": "/docs"
    }


@app.get("/health")
def health_check():
    return {"status": "healthy", "timestamp": datetime.utcnow()}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=int(os.getenv("PORT", 8000)))
