import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from starlette.middleware.base import BaseHTTPMiddleware

from app.config import get_settings
from app.api.webhooks import router as webhooks_router
from app.api.health import router as health_router
from app.api.conversations import router as conversations_router
from app.api.onboarding import router as onboarding_router
from app.api.console import router as console_router
from app.api.harness import router as harness_router
from app.api.billing import router as billing_router
from app.api.agent_portal import router as agent_portal_router
from app.api.mobile import router as mobile_router
from app.db.connection import init_pool, close_pool, init_async_pool, close_async_pool
from app.services.redis_pool import get_redis_pool
from app.pipeline.structured_logging import configure_logging, set_correlation_id
from app.services.console_queries import AuthorizationError

# Configure structured JSON logging before anything else logs
configure_logging()

logger = logging.getLogger(__name__)


class CorrelationMiddleware(BaseHTTPMiddleware):
    """Attach a correlation ID to every inbound request."""

    async def dispatch(self, request: Request, call_next):
        # Use incoming header if present; otherwise generate one
        cid = request.headers.get("x-correlation-id")
        cid = set_correlation_id(cid)
        response = await call_next(request)
        response.headers["x-correlation-id"] = cid
        return response


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_pool()
    await init_async_pool()
    logger.info("Database connection pools initialized (sync + async)")
    yield
    await close_async_pool()
    close_pool()
    pool = get_redis_pool()
    pool.close()
    logger.info("Connection pools closed")


settings = get_settings()

OPENAPI_TAGS = [
    {"name": "health", "description": "Service health checks and operational metrics."},
    {"name": "webhooks", "description": "Inbound message and voice webhooks (Twilio, Vapi, SendGrid)."},
    {"name": "billing", "description": "Stripe payment webhooks."},
    {"name": "onboarding", "description": "Agent provisioning and onboarding checklist."},
    {"name": "console", "description": "Operator console -- admin dashboard, customers, messages, automations, billing, health, and knowledge base."},
    {"name": "conversations", "description": "Token-authenticated conversation deep-link views."},
    {"name": "agent-portal", "description": "Agent-facing mobile portal -- dashboard, contacts, conversations, schedule, triggers, transactions, scores, and campaigns."},
    {"name": "harness", "description": "Testing harness -- message injection, trace history, scenario runner."},
    {"name": "mobile-auth", "description": "Mobile app authentication — login, token refresh, logout."},
]

app = FastAPI(
    title="Calloway API",
    description=(
        "AI operational assistant for solo real estate agents. "
        "Automates client communication, lead management, scheduling, "
        "and business intelligence.\n\n"
        "**Swagger UI:** `/docs`  |  **ReDoc:** `/redoc`  |  "
        "**OpenAPI JSON:** `/openapi.json`"
    ),
    version="1.0.0",
    lifespan=lifespan,
    openapi_tags=OPENAPI_TAGS,
)

# CORS — explicit origins in production, permissive in development
_origins = (
    [o.strip() for o in settings.CORS_ALLOWED_ORIGINS.split(",") if o.strip()]
    if settings.CORS_ALLOWED_ORIGINS
    else []
)
if settings.ENVIRONMENT == "development" and not _origins:
    _origins = ["http://localhost:3000", "http://localhost:8000"]

app.add_middleware(
    CORSMiddleware,
    allow_origins=_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.add_middleware(CorrelationMiddleware)


@app.exception_handler(AuthorizationError)
async def authorization_error_handler(request: Request, exc: AuthorizationError):
    """Return 403 for unauthenticated console query access."""
    from fastapi.responses import JSONResponse
    logger.warning(f"AuthorizationError on {request.url.path}: {exc}")
    return JSONResponse(
        status_code=403,
        content={"detail": "Access denied. Authentication required."},
    )


app.include_router(webhooks_router)
app.include_router(health_router)
app.include_router(conversations_router)
app.include_router(onboarding_router)
app.include_router(console_router)
app.include_router(harness_router)
app.include_router(billing_router)
app.include_router(agent_portal_router)
app.include_router(mobile_router)

# Static files for console
STATIC_DIR = Path(__file__).resolve().parent / "static"
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")
