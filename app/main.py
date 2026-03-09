from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.webhooks import router as webhooks_router
from app.api.health import router as health_router
from app.api.conversations import router as conversations_router
from app.api.onboarding import router as onboarding_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    yield
    # Shutdown


app = FastAPI(
    title="Solo Realtor AI",
    description="AI operational assistant for solo real estate agents",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(webhooks_router)
app.include_router(health_router)
app.include_router(conversations_router)
app.include_router(onboarding_router)
