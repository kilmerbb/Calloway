import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.config import get_settings
from app.api.webhooks import router as webhooks_router
from app.api.health import router as health_router
from app.api.conversations import router as conversations_router
from app.api.onboarding import router as onboarding_router
from app.api.console import router as console_router
from app.api.harness import router as harness_router
from app.api.billing import router as billing_router
from app.db.connection import init_pool, close_pool
from app.services.redis_pool import get_redis_pool

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup — initialize connection pools
    init_pool()
    logger.info("Database connection pool initialized")
    yield
    # Shutdown — clean up connection pools
    close_pool()
    pool = get_redis_pool()
    pool.close()
    logger.info("Connection pools closed")


settings = get_settings()

app = FastAPI(
    title="Calloway",
    description="AI operational assistant for solo real estate agents",
    version="1.0.0",
    lifespan=lifespan,
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

app.include_router(webhooks_router)
app.include_router(health_router)
app.include_router(conversations_router)
app.include_router(onboarding_router)
app.include_router(console_router)
app.include_router(harness_router)
app.include_router(billing_router)

# Static files for console
STATIC_DIR = Path(__file__).resolve().parent / "static"
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")
