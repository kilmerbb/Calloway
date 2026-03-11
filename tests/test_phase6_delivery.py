"""Tests for Phase 6: Delivery status tracking + Dockerfile hardening.

Tests the Twilio status webhook, delivery status schema fields, and
the Docker configuration.
"""
import pytest
from datetime import datetime, timezone
from uuid import UUID
from unittest.mock import patch, MagicMock
from pathlib import Path

from app.models.schemas import Message

AGENT_ID = UUID("a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11")


# ── Message model tests ──────────────────────────────────────

def test_message_has_delivery_fields():
    """Message model includes delivery tracking fields."""
    msg = Message(
        agent_id=AGENT_ID,
        conversation_id=UUID("c1eebc99-9c0b-4ef8-bb6d-6bb9bd380a11"),
        sender_type="ai",
        body="Hello!",
        provider_message_id="SM123abc",
        delivery_status="delivered",
        delivered_at=datetime.now(timezone.utc),
    )
    assert msg.provider_message_id == "SM123abc"
    assert msg.delivery_status == "delivered"
    assert msg.delivered_at is not None
    assert msg.failure_reason is None


def test_message_delivery_defaults():
    """Message delivery_status defaults to 'pending'."""
    msg = Message(
        agent_id=AGENT_ID,
        conversation_id=UUID("c1eebc99-9c0b-4ef8-bb6d-6bb9bd380a11"),
        sender_type="client",
        body="Hi",
    )
    assert msg.delivery_status == "pending"
    assert msg.provider_message_id is None
    assert msg.failure_reason is None


def test_message_failure_fields():
    """Message can track failure reason."""
    msg = Message(
        agent_id=AGENT_ID,
        conversation_id=UUID("c1eebc99-9c0b-4ef8-bb6d-6bb9bd380a11"),
        sender_type="ai",
        body="Test",
        delivery_status="failed",
        failure_reason="30006: Landline or unreachable carrier",
    )
    assert msg.delivery_status == "failed"
    assert "30006" in msg.failure_reason


# ── Twilio status webhook tests ──────────────────────────────

def test_twilio_status_delivered(client):
    """Twilio status callback with 'delivered' updates message."""
    with patch("app.db.connection.get_db_connection") as mock_conn:
        mock_ctx = MagicMock()
        mock_conn.return_value.__enter__ = MagicMock(return_value=mock_ctx)
        mock_conn.return_value.__exit__ = MagicMock(return_value=False)

        response = client.post("/webhooks/twilio/status", data={
            "MessageSid": "SM1234567890",
            "MessageStatus": "delivered",
        })

        assert response.status_code == 200
        assert "Response" in response.text

        # Verify UPDATE was called with delivered status
        update_call = mock_ctx.execute.call_args_list[0]
        sql = update_call[0][0]
        assert "delivery_status" in sql
        assert "delivered_at" in sql


def test_twilio_status_failed(client):
    """Twilio status callback with 'failed' records error details."""
    with patch("app.db.connection.get_db_connection") as mock_conn:
        mock_ctx = MagicMock()
        mock_conn.return_value.__enter__ = MagicMock(return_value=mock_ctx)
        mock_conn.return_value.__exit__ = MagicMock(return_value=False)
        # Return None for the agent lookup query
        mock_ctx.execute.return_value.fetchone.return_value = None

        response = client.post("/webhooks/twilio/status", data={
            "MessageSid": "SM1234567890",
            "MessageStatus": "failed",
            "ErrorCode": "30006",
            "ErrorMessage": "Landline or unreachable carrier",
        })

        assert response.status_code == 200

        # Verify UPDATE was called with failure info
        first_call = mock_ctx.execute.call_args_list[0]
        sql = first_call[0][0]
        assert "failure_reason" in sql


def test_twilio_status_empty_sid(client):
    """Twilio status with empty MessageSid is handled gracefully."""
    response = client.post("/webhooks/twilio/status", data={
        "MessageSid": "",
        "MessageStatus": "delivered",
    })
    assert response.status_code == 200


# ── Dockerfile tests ─────────────────────────────────────────

def test_dockerfile_exists():
    """Dockerfile exists and is properly structured."""
    dockerfile = Path("/home/user/Calloway/Dockerfile")
    assert dockerfile.exists()
    content = dockerfile.read_text()

    # Multi-stage build
    assert "AS builder" in content
    assert "FROM python:3.12-slim" in content

    # Non-root user
    assert "calloway" in content
    assert "USER calloway" in content

    # Health check
    assert "HEALTHCHECK" in content

    # Security settings
    assert "PYTHONUNBUFFERED" in content
    assert "PYTHONDONTWRITEBYTECODE" in content


def test_dockerignore_exists():
    """.dockerignore excludes sensitive and unnecessary files."""
    dockerignore = Path("/home/user/Calloway/.dockerignore")
    assert dockerignore.exists()
    content = dockerignore.read_text()

    assert ".git" in content
    assert ".env" in content
    assert "tests/" in content
