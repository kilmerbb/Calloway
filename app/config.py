import logging
import sys

from pydantic_settings import BaseSettings
from functools import lru_cache

logger = logging.getLogger(__name__)


class Settings(BaseSettings):
    # Supabase
    SUPABASE_URL: str = ""
    SUPABASE_SERVICE_KEY: str = ""

    # Twilio
    TWILIO_ACCOUNT_SID: str = ""
    TWILIO_AUTH_TOKEN: str = ""

    # Google OAuth
    GOOGLE_CLIENT_ID: str = ""
    GOOGLE_CLIENT_SECRET: str = ""

    # Anthropic
    ANTHROPIC_API_KEY: str = ""

    # Vapi
    VAPI_API_KEY: str = ""

    # Firebase
    FIREBASE_SERVER_KEY: str = ""

    # Stripe
    STRIPE_SECRET_KEY: str = ""
    STRIPE_WEBHOOK_SECRET: str = ""

    # Redis
    REDIS_URL: str = "redis://localhost:6379/0"

    # Console
    CONSOLE_PASSWORD: str = "changeme"
    CONSOLE_SESSION_SECRET: str = "console-secret-change-in-production"

    # CORS — comma-separated allowed origins (e.g. "https://app.calloway.ai,https://admin.calloway.ai")
    CORS_ALLOWED_ORIGINS: str = ""

    # Environment
    ENVIRONMENT: str = "development"

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}

    def validate_production_secrets(self) -> None:
        """Refuse to start in production with default credentials."""
        if self.ENVIRONMENT == "development":
            return
        errors = []
        if self.CONSOLE_PASSWORD == "changeme":
            errors.append("CONSOLE_PASSWORD is still the default 'changeme'")
        if self.CONSOLE_SESSION_SECRET == "console-secret-change-in-production":
            errors.append("CONSOLE_SESSION_SECRET is still the default")
        if errors:
            for e in errors:
                logger.critical(f"SECURITY: {e}")
            sys.exit(1)


@lru_cache
def get_settings() -> Settings:
    settings = Settings()
    settings.validate_production_secrets()
    return settings
