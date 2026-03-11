"""Tests for structured JSON logging and correlation middleware."""
import json
import logging
import pytest
from unittest.mock import patch

from app.pipeline.structured_logging import (
    StructuredFormatter,
    get_correlation_id,
    set_correlation_id,
)


def test_set_and_get_correlation_id():
    """set_correlation_id stores and get_correlation_id retrieves."""
    cid = set_correlation_id("test-abc-123")
    assert cid == "test-abc-123"
    assert get_correlation_id() == "test-abc-123"


def test_auto_generate_correlation_id():
    """set_correlation_id auto-generates when no value passed."""
    cid = set_correlation_id()
    assert len(cid) == 12  # hex UUID prefix
    assert get_correlation_id() == cid


def test_structured_formatter_produces_json():
    """StructuredFormatter outputs valid JSON."""
    formatter = StructuredFormatter()
    record = logging.LogRecord(
        name="test.logger",
        level=logging.INFO,
        pathname="test.py",
        lineno=42,
        msg="Test message",
        args=(),
        exc_info=None,
    )

    set_correlation_id("fmt-test-123")
    output = formatter.format(record)

    parsed = json.loads(output)
    assert parsed["msg"] == "Test message"
    assert parsed["level"] == "INFO"
    assert parsed["logger"] == "test.logger"
    assert parsed["correlation_id"] == "fmt-test-123"
    assert "ts" in parsed


def test_structured_formatter_includes_extra_fields():
    """Extra structured fields are included in JSON output."""
    formatter = StructuredFormatter()
    record = logging.LogRecord(
        name="test", level=logging.INFO,
        pathname="test.py", lineno=1,
        msg="Tool call", args=(), exc_info=None,
    )
    record.agent_id = "agent-123"
    record.tool_name = "lookup_contact"

    output = formatter.format(record)
    parsed = json.loads(output)

    assert parsed["agent_id"] == "agent-123"
    assert parsed["tool_name"] == "lookup_contact"


def test_structured_formatter_includes_source_on_warning():
    """Warnings and errors include source file location."""
    formatter = StructuredFormatter()
    record = logging.LogRecord(
        name="test", level=logging.WARNING,
        pathname="/app/test.py", lineno=99,
        msg="Something wrong", args=(), exc_info=None,
    )

    output = formatter.format(record)
    parsed = json.loads(output)

    assert "source" in parsed
    assert "99" in parsed["source"]


def test_correlation_middleware_returns_header(client):
    """CorrelationMiddleware sets x-correlation-id on responses."""
    response = client.get("/health")
    assert "x-correlation-id" in response.headers
    assert len(response.headers["x-correlation-id"]) > 0


def test_correlation_middleware_accepts_incoming_id(client):
    """CorrelationMiddleware uses incoming x-correlation-id if provided."""
    response = client.get("/health", headers={"x-correlation-id": "custom-id-xyz"})
    assert response.headers["x-correlation-id"] == "custom-id-xyz"
