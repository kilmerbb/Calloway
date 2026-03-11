"""Structured JSON logging with correlation IDs for request tracing.

Usage:
    from app.pipeline.structured_logging import configure_logging, get_correlation_id, set_correlation_id

    # At app startup:
    configure_logging()

    # In middleware or webhook entry:
    set_correlation_id()  # auto-generates UUID
    logger.info("Processing message", extra={"agent_id": "...", "channel": "sms"})

    # All log output is JSON with correlation_id attached.
"""

import json
import logging
import uuid
from contextvars import ContextVar
from datetime import datetime, timezone

# Context variable for request-scoped correlation ID
_correlation_id: ContextVar[str] = ContextVar("correlation_id", default="")


def get_correlation_id() -> str:
    """Get the current correlation ID for this request/task."""
    return _correlation_id.get()


def set_correlation_id(cid: str | None = None) -> str:
    """Set (or generate) a correlation ID for the current context."""
    cid = cid or uuid.uuid4().hex[:12]
    _correlation_id.set(cid)
    return cid


class StructuredFormatter(logging.Formatter):
    """JSON log formatter that includes correlation_id and structured fields."""

    def format(self, record: logging.LogRecord) -> str:
        log_entry = {
            "ts": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ"),
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
            "correlation_id": get_correlation_id(),
        }

        # Add source location for errors
        if record.levelno >= logging.WARNING:
            log_entry["source"] = f"{record.pathname}:{record.lineno}"

        # Include exception info
        if record.exc_info and record.exc_info[0]:
            log_entry["exception"] = self.formatException(record.exc_info)

        # Merge any extra structured fields (agent_id, contact_id, etc.)
        for key in ("agent_id", "contact_id", "channel", "command_type",
                     "model_used", "tokens_used", "latency_ms", "tool_name",
                     "event_type", "conversation_id"):
            val = getattr(record, key, None)
            if val is not None:
                log_entry[key] = str(val)

        return json.dumps(log_entry, default=str)


def configure_logging(level: str = "INFO") -> None:
    """Configure root logger with structured JSON output.

    Call once at application startup. Replaces default handlers on the
    root logger so all loggers in the app emit JSON.
    """
    root = logging.getLogger()
    root.setLevel(getattr(logging, level.upper(), logging.INFO))

    # Remove existing handlers
    for handler in root.handlers[:]:
        root.removeHandler(handler)

    handler = logging.StreamHandler()
    handler.setFormatter(StructuredFormatter())
    root.addHandler(handler)

    # Quiet noisy third-party loggers
    for name in ("uvicorn.access", "httpcore", "httpx", "hpack"):
        logging.getLogger(name).setLevel(logging.WARNING)
