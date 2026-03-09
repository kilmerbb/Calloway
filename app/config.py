from pydantic_settings import BaseSettings
from functools import lru_cache


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

    # Redis
    REDIS_URL: str = "redis://localhost:6379/0"

    # Console
    CONSOLE_PASSWORD: str = "changeme"
    CONSOLE_SESSION_SECRET: str = "console-secret-change-in-production"

    # Environment
    ENVIRONMENT: str = "development"

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


@lru_cache
def get_settings() -> Settings:
    return Settings()
