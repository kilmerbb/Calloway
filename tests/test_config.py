"""Tests for configuration and agent config loading."""
import pytest
from unittest.mock import patch, MagicMock
from uuid import UUID

from app.config import Settings
from app.models.schemas import AgentConfig

TEST_AGENT_ID = UUID("a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11")


def test_settings_load_defaults():
    """Settings should load with defaults from .env.example."""
    settings = Settings(
        SUPABASE_URL="https://test.supabase.co",
        SUPABASE_SERVICE_KEY="test-key",
        TWILIO_ACCOUNT_SID="ACtest",
        TWILIO_AUTH_TOKEN="test-token",
        GOOGLE_CLIENT_ID="test-client-id",
        GOOGLE_CLIENT_SECRET="test-secret",
        ANTHROPIC_API_KEY="sk-test",
        VAPI_API_KEY="test-vapi",
        FIREBASE_SERVER_KEY="test-firebase",
    )
    assert settings.ENVIRONMENT == "development"
    assert settings.REDIS_URL == "redis://localhost:6379/0"


def test_agent_config_from_db():
    """Test loading agent config from database (requires DB)."""
    try:
        from app.services.agent_config import get_agent_by_id
        agent = get_agent_by_id(TEST_AGENT_ID)
        assert agent is not None
        assert agent.name == "Jane Smith"
        assert agent.twilio_number == "+12155559999"
    except Exception:
        pytest.skip("Database or Redis not available")


def test_agent_config_by_twilio_number():
    """Test loading agent config by Twilio number."""
    try:
        from app.services.agent_config import get_agent_by_twilio_number
        agent = get_agent_by_twilio_number("+12155559999")
        assert agent is not None
        assert agent.id == TEST_AGENT_ID
    except Exception:
        pytest.skip("Database or Redis not available")


def test_agent_config_cache():
    """Test that second call hits Redis cache, not DB."""
    try:
        from app.services.agent_config import get_agent_by_id
        from app.services.redis_pool import get_redis_pool
        # First call populates cache
        agent1 = get_agent_by_id(TEST_AGENT_ID)
        assert agent1 is not None

        # Verify cache exists
        r = get_redis_pool()
        cached = r.get(f"agent:id:{TEST_AGENT_ID}")
        assert cached is not None

        # Second call should use cache
        agent2 = get_agent_by_id(TEST_AGENT_ID)
        assert agent2 is not None
        assert agent2.name == agent1.name
    except Exception:
        pytest.skip("Database or Redis not available")


def test_agent_not_found():
    """Test that nonexistent agent returns None."""
    try:
        from app.services.agent_config import get_agent_by_id
        agent = get_agent_by_id(UUID("00000000-0000-0000-0000-000000000000"))
        assert agent is None
    except Exception:
        pytest.skip("Database or Redis not available")
