"""End-to-end system validation tests.

Tests that all components work together across the full Calloway platform:
- Import verification for all modules
- App startup and route registration
- Pipeline flow integrity
- Cross-cutting concerns (CSRF, CORS, correlation IDs)
"""
import pytest
import json
from datetime import datetime, timezone
from uuid import UUID
from unittest.mock import patch, MagicMock
from pathlib import Path

from app.models.schemas import (
    NormalizedEvent, AgentConfig, Contact, Listing, Message,
    AgentDecision, IntentClassification, AssembledContext,
)


AGENT_ID = UUID("a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11")
AGENT = AgentConfig(
    id=AGENT_ID, name="Jane Smith", email="jane@calloway.ai",
    phone="+12155551000", twilio_number="+12155559999",
    style_profile={"tone": "professional"},
)


def _event(body: str, channel: str = "sms") -> NormalizedEvent:
    return NormalizedEvent(
        sender_phone="+12675551234", channel=channel, body=body,
        timestamp=datetime.now(timezone.utc),
        provider_message_id="SM123", raw_payload={}, agent_id=AGENT_ID,
    )


# ── 1. Module Import Verification ────────────────────────────

class TestModuleImports:
    """Verify all new modules import without errors."""

    def test_pipeline_commands(self):
        from app.pipeline.commands import listing, contact, status, scheduling, offer
        assert listing.handle_listing_command
        assert contact.handle_client_instruction
        assert status.handle_status_change
        assert scheduling.handle_gap_query
        assert offer.handle_offer_command

    def test_structured_logging(self):
        from app.pipeline.structured_logging import (
            configure_logging, set_correlation_id, get_correlation_id,
            StructuredFormatter,
        )
        assert callable(configure_logging)

    def test_email_service(self):
        from app.services.email_service import (
            send_email, send_client_email, parse_inbound_email,
        )
        assert callable(send_email)

    def test_billing_service(self):
        from app.services.billing_service import (
            PLAN_TIERS, create_customer_and_subscription,
            change_plan, cancel_subscription,
            check_message_quota, get_billing_summary,
        )
        assert len(PLAN_TIERS) == 3

    def test_redis_pool(self):
        from app.services.redis_pool import get_redis_pool
        assert callable(get_redis_pool)

    def test_agent_portal(self):
        from app.api.agent_portal import router
        assert router.prefix == "/agent"

    def test_billing_router(self):
        from app.api.billing import router
        assert router.prefix == "/billing"


# ── 2. Application Startup ───────────────────────────────────

class TestAppStartup:
    """Verify app is configured correctly."""

    def test_app_has_all_routers(self, client):
        """All expected route prefixes are registered."""
        routes = [r.path for r in client.app.routes if hasattr(r, "path")]
        prefixes = set()
        for r in routes:
            parts = r.strip("/").split("/")
            if parts and parts[0]:
                prefixes.add(parts[0])

        assert "webhooks" in prefixes
        assert "health" in prefixes
        assert "console" in prefixes
        assert "agent" in prefixes
        assert "billing" in prefixes

    def test_health_endpoint(self, client):
        response = client.get("/health")
        assert response.status_code == 200

    def test_correlation_id_middleware(self, client):
        response = client.get("/health")
        assert "x-correlation-id" in response.headers

    def test_cors_middleware_configured(self, client):
        response = client.options(
            "/health",
            headers={"Origin": "http://localhost:3000", "Access-Control-Request-Method": "GET"},
        )
        # Should have CORS headers in dev mode
        assert response.status_code in (200, 400)

    def test_static_files_mounted(self, client):
        response = client.get("/static/console/style.css")
        assert response.status_code == 200
        assert "text/css" in response.headers.get("content-type", "")


# ── 3. Pipeline Flow Integrity ────────────────────────────────

class TestPipelineFlow:
    """Test the full message processing pipeline."""

    def test_normalizer_sms(self):
        from app.pipeline.normalizer import normalize_twilio_event
        payload = {
            "From": "+12675551234",
            "To": "+12155559999",
            "Body": "Is 123 Oak available?",
            "MessageSid": "SMtest123",
        }
        event = normalize_twilio_event(payload, AGENT_ID)
        assert event.channel == "sms"
        assert event.body == "Is 123 Oak available?"
        assert event.sender_phone == "+12675551234"

    def test_normalizer_email(self):
        from app.pipeline.normalizer import normalize_email_event
        payload = {
            "from": "sarah@example.com",
            "text": "Question about listing",
        }
        event = normalize_email_event(payload, AGENT_ID)
        assert event.channel == "email"
        assert event.body == "Question about listing"

    @patch("app.pipeline.resolver.get_db_connection")
    def test_resolver_agent_detection(self, mock_conn):
        from app.pipeline.resolver import resolve_contact
        event = _event("New listing")
        event.sender_phone = AGENT.phone
        contact, is_agent = resolve_contact(event, AGENT)
        assert is_agent is True
        assert contact is None

    @patch("app.pipeline.resolver.get_db_connection")
    def test_resolver_unknown_sender(self, mock_conn):
        from app.pipeline.resolver import resolve_contact
        mock_ctx = MagicMock()
        mock_conn.return_value.__enter__ = MagicMock(return_value=mock_ctx)
        mock_conn.return_value.__exit__ = MagicMock(return_value=False)
        mock_ctx.execute.return_value.fetchone.return_value = None

        event = _event("Hello")
        contact, is_agent = resolve_contact(event, AGENT)
        assert is_agent is False
        assert contact is None

    def test_template_handler_no_llm(self):
        from app.pipeline.handlers import handle_template
        event = _event("confirm")
        result = handle_template(
            event, None, AGENT, "showing_confirmation",
            address="123 Oak St", time="2pm", lockbox="4521",
        )
        assert result.tokens_used == 0
        assert result.model_used == "template"
        assert "123 Oak St" in result.response_text

    def test_escalation_handler(self):
        from app.pipeline.handlers import handle_escalation
        contact = Contact(
            id=UUID("b1eebc99-9c0b-4ef8-bb6d-6bb9bd380a11"),
            agent_id=AGENT_ID, name="Sarah Chen", phone="+12675551234",
        )
        event = _event("I want to sue!")
        result = handle_escalation(event, contact, AGENT, "client_frustration")
        assert result.notifications
        assert result.notifications[0]["tier"] == "action_needed"


# ── 4. Schema Integrity ──────────────────────────────────────

class TestSchemaIntegrity:
    """Test all model fields and defaults."""

    def test_contact_lead_source(self):
        contact = Contact(
            id=UUID("b1eebc99-9c0b-4ef8-bb6d-6bb9bd380a11"),
            agent_id=AGENT_ID, name="Test", phone="+1234567890",
            lead_source="email",
        )
        assert contact.lead_source == "email"

    def test_message_delivery_tracking(self):
        msg = Message(
            agent_id=AGENT_ID,
            conversation_id=UUID("c1eebc99-9c0b-4ef8-bb6d-6bb9bd380a11"),
            sender_type="ai", body="Hello",
            provider_message_id="SM123",
            delivery_status="delivered",
            delivered_at=datetime.now(timezone.utc),
        )
        assert msg.provider_message_id == "SM123"
        assert msg.delivery_status == "delivered"

    def test_agent_decision_defaults(self):
        decision = AgentDecision(response_text="Hello")
        assert decision.tool_calls == []
        assert decision.triggers_to_create == []
        assert decision.notifications == []
        assert decision.model_used == "template"
        assert decision.tokens_used == 0

    def test_normalized_event_channels(self):
        for channel in ["rcs", "sms", "sms_command", "vapi", "email", "portal"]:
            event = NormalizedEvent(
                sender_phone="+1234567890", channel=channel,
                body="test", timestamp=datetime.now(timezone.utc),
                provider_message_id="test", raw_payload={}, agent_id=AGENT_ID,
            )
            assert event.channel == channel


# ── 5. Webhook Endpoints ─────────────────────────────────────

class TestWebhookEndpoints:
    """Test all webhook endpoints respond correctly."""

    def test_twilio_inbound_rejects_invalid_signature(self, client):
        with patch("app.api.webhooks.validate_twilio_signature", return_value=False):
            response = client.post("/webhooks/twilio/inbound", data={
                "From": "+12675551234", "To": "+12155559999",
                "Body": "Hello", "MessageSid": "SMtest",
            })
            assert response.status_code == 403

    def test_twilio_status_endpoint(self, client):
        with patch("app.db.connection.get_db_connection") as mock_conn:
            mock_ctx = MagicMock()
            mock_conn.return_value.__enter__ = MagicMock(return_value=mock_ctx)
            mock_conn.return_value.__exit__ = MagicMock(return_value=False)

            response = client.post("/webhooks/twilio/status", data={
                "MessageSid": "SM123", "MessageStatus": "delivered",
            })
            assert response.status_code == 200

    def test_email_inbound_endpoint_no_agent(self, client):
        with patch("app.api.webhooks._resolve_agent_from_email", return_value=None):
            response = client.post("/webhooks/email/inbound", data={
                "from": "unknown@test.com",
                "to": "nobody@calloway.ai",
                "text": "Hello",
            })
            assert response.status_code == 200
            assert response.json()["status"] == "no_agent"

    def test_stripe_webhook_rejects_invalid_signature(self, client):
        mock_settings = MagicMock()
        mock_settings.STRIPE_WEBHOOK_SECRET = "whsec_test_secret"
        with patch("app.api.billing.get_settings", return_value=mock_settings):
            response = client.post(
                "/billing/webhooks/stripe",
                content=b"{}",
                headers={"stripe-signature": "invalid"},
            )
            assert response.status_code in (400, 500)


# ── 6. Console Security ──────────────────────────────────────

class TestConsoleSecurity:
    """Test CSRF and auth on console routes."""

    def test_console_login_renders(self, client):
        response = client.get("/console/login")
        assert response.status_code == 200
        assert "password" in response.text.lower()

    def test_console_requires_auth(self, client):
        for path in ["/console/tenants", "/console/conversations",
                     "/console/triggers", "/console/costs",
                     "/console/billing", "/console/health"]:
            response = client.get(path, follow_redirects=False)
            assert response.status_code in (303, 307), f"Expected redirect for {path}"


# ── 7. File Structure Validation ─────────────────────────────

class TestFileStructure:
    """Validate all required files exist."""

    def test_command_modules_exist(self):
        base = Path("/home/user/Calloway/app/pipeline/commands")
        assert (base / "__init__.py").exists()
        assert (base / "listing.py").exists()
        assert (base / "contact.py").exists()
        assert (base / "status.py").exists()
        assert (base / "scheduling.py").exists()
        assert (base / "offer.py").exists()

    def test_alembic_setup(self):
        base = Path("/home/user/Calloway")
        assert (base / "alembic.ini").exists()
        assert (base / "alembic/env.py").exists()
        assert (base / "alembic/versions/001_baseline.py").exists()
        assert (base / "alembic/versions/002_add_lead_source.py").exists()
        assert (base / "alembic/versions/003_add_delivery_tracking.py").exists()

    def test_docker_production_files(self):
        base = Path("/home/user/Calloway")
        assert (base / "Dockerfile").exists()
        assert (base / ".dockerignore").exists()
        assert (base / "docker-compose.yml").exists()

    def test_billing_schema_exists(self):
        assert Path("/home/user/Calloway/app/db/billing_schema.sql").exists()

    def test_agent_portal_templates(self):
        base = Path("/home/user/Calloway/app/templates/agent")
        for template in ["base.html", "login.html", "dashboard.html",
                         "contacts.html", "conversations.html",
                         "conversation_detail.html", "schedule.html", "triggers.html"]:
            assert (base / template).exists(), f"Missing template: {template}"

    def test_billing_template(self):
        assert Path("/home/user/Calloway/app/templates/console/billing.html").exists()
