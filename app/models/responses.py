"""Structured return types for console query functions.

These TypedDicts document the shape of dicts returned by
``app.services.console_queries`` and provide static-analysis support
via mypy / pyright without changing any runtime behaviour.
"""
from __future__ import annotations

from typing import Any, TypedDict


# ── get_system_pulse() ────────────────────────────────────────────

class SystemPulse(TypedDict):
    total_agents: int
    messages_today: int
    messages_24h: int
    errors_24h: int
    cost_today_dollars: float


# ── get_recent_activity() ─────────────────────────────────────────

class ActivityEntry(TypedDict):
    created_at: Any  # datetime from DB
    sender_type: str
    body: str | None
    agent_name: str
    contact_name: str | None
    ai_generated: bool
    model_used: str | None


# ── get_all_agents() ──────────────────────────────────────────────

class AgentSummary(TypedDict, total=False):
    """Agent row with joined summary stats.

    ``total=False`` because the base ``agents.*`` columns vary and are
    driver-dependent.  The four explicitly-joined aggregates are always
    present.
    """
    # Joined aggregates (always present)
    contact_count: int
    messages_today: int
    last_active: Any  # date | None
    errors_24h: int


# ── get_agent_detail() ────────────────────────────────────────────

class AgentDetail(TypedDict):
    agent: dict[str, Any]
    contacts: list[dict[str, Any]]
    listings: list[dict[str, Any]]
    recent_messages: list[dict[str, Any]]
    pending_triggers: list[dict[str, Any]]
    cost_this_month_dollars: float
    messages_this_month: int
    errors_24h: int


# ── get_recent_conversations() ────────────────────────────────────

class ConversationRow(TypedDict):
    id: Any  # UUID
    channel: str | None
    last_message_at: Any  # datetime | None
    agent_name: str
    contact_name: str | None
    phone: str | None
    msg_count: int
    last_message: str | None


# ── get_conversation_detail() ─────────────────────────────────────

class ConversationDetail(TypedDict):
    conversation: dict[str, Any]
    messages: list[dict[str, Any]]
    tool_executions: list[dict[str, Any]]
    triggers: list[dict[str, Any]]


# ── get_trigger_queue() ──────────────────────────────────────────

class TriggerRow(TypedDict, total=False):
    """Trigger row with joined agent name.

    ``total=False`` because ``triggers.*`` columns are driver-dependent.
    ``agent_name`` is always present from the JOIN.
    """
    agent_name: str


# ── get_recent_errors() ──────────────────────────────────────────

class ErrorSummary(TypedDict):
    tool_errors: list[dict[str, Any]]
    app_errors: list[dict[str, Any]]


# ── get_cost_summary() ───────────────────────────────────────────

class CostSummary(TypedDict):
    total_cost_dollars: float
    llm_cost_dollars: float
    sms_cost_dollars: float
    voice_cost_dollars: float
    total_sms_segments: int
    total_messages: int
    total_voice_minutes: float
    total_showings: int
    total_llm_calls: int
    daily: list[dict[str, Any]]


# ── get_health_overview() ────────────────────────────────────────

class PipelineStats(TypedDict):
    avg_latency_ms: int
    p50_ms: int
    p95_ms: int


class HealthOverview(TypedDict):
    services: dict[str, str]
    pipeline: PipelineStats
