"""Tests for app/services/console_queries.py — query layer unit tests.

Tests all public sync functions and key async functions with mocked DB connections.
Matches project patterns from test_console.py and test_triggers.py.
"""
import json
import pytest
from datetime import datetime, timezone, date, timedelta
from uuid import uuid4
from unittest.mock import patch, MagicMock, AsyncMock

from app.services.console_queries import set_console_context, clear_console_context

AGENT_ID = str(uuid4())
CONV_ID = str(uuid4())
TRIGGER_ID = str(uuid4())
CONTACT_ID = str(uuid4())


@pytest.fixture(autouse=True)
def _set_console_auth_context():
    """Set console auth context for every test so @console_authorized passes."""
    set_console_context({"source": "test", "test": True})
    yield
    clear_console_context()


# ============================================================
# Helper: build a mock sync DB context manager
# ============================================================

def _mock_sync_conn(mock_conn, ctx=None):
    """Wire up mock_conn as a context manager returning ctx."""
    if ctx is None:
        ctx = MagicMock()
    mock_conn.return_value.__enter__ = MagicMock(return_value=ctx)
    mock_conn.return_value.__exit__ = MagicMock(return_value=False)
    return ctx


# ============================================================
# 1. get_system_pulse
# ============================================================

@patch("app.services.console_queries.get_db_connection")
def test_get_system_pulse_success(mock_conn):
    from app.services.console_queries import get_system_pulse

    ctx = MagicMock()
    ctx.execute.return_value.fetchone.side_effect = [
        {"cnt": 5},        # agents count
        {"cnt": 200},      # msgs_today
        {"cnt": 350},      # msgs_24h
        {"cnt": 3},        # errors_24h
        {"cost": 1250},    # cost in cents
    ]
    _mock_sync_conn(mock_conn, ctx)

    result = get_system_pulse()
    assert result["total_agents"] == 5
    assert result["messages_today"] == 200
    assert result["messages_24h"] == 350
    assert result["errors_24h"] == 3
    assert result["cost_today_dollars"] == 12.50


@patch("app.services.console_queries.get_db_connection")
def test_get_system_pulse_error_returns_defaults(mock_conn):
    from app.services.console_queries import get_system_pulse

    mock_conn.side_effect = Exception("DB down")
    result = get_system_pulse()
    assert result["total_agents"] == 0
    assert result["messages_today"] == 0
    assert result["cost_today_dollars"] == 0


@patch("app.services.console_queries.get_db_connection")
def test_get_system_pulse_none_rows(mock_conn):
    """COALESCE behavior: None fetchone results produce zeros."""
    from app.services.console_queries import get_system_pulse

    ctx = MagicMock()
    ctx.execute.return_value.fetchone.side_effect = [
        None, None, None, None, None,
    ]
    _mock_sync_conn(mock_conn, ctx)

    result = get_system_pulse()
    assert result["total_agents"] == 0
    assert result["messages_today"] == 0
    assert result["cost_today_dollars"] == 0


# ============================================================
# 2. get_recent_activity
# ============================================================

@patch("app.services.console_queries.get_db_connection")
def test_get_recent_activity_success(mock_conn):
    from app.services.console_queries import get_recent_activity

    rows = [
        {"created_at": datetime.now(timezone.utc), "sender_type": "client",
         "body": "Hello", "agent_name": "Agent 1", "contact_name": "Sarah",
         "ai_generated": False, "model_used": None},
    ]
    ctx = MagicMock()
    ctx.execute.return_value.fetchall.return_value = rows
    _mock_sync_conn(mock_conn, ctx)

    result = get_recent_activity(limit=10)
    assert len(result) == 1
    assert result[0]["body"] == "Hello"


@patch("app.services.console_queries.get_db_connection")
def test_get_recent_activity_empty(mock_conn):
    from app.services.console_queries import get_recent_activity

    ctx = MagicMock()
    ctx.execute.return_value.fetchall.return_value = None
    _mock_sync_conn(mock_conn, ctx)

    result = get_recent_activity()
    assert result == []


@patch("app.services.console_queries.get_db_connection")
def test_get_recent_activity_error(mock_conn):
    from app.services.console_queries import get_recent_activity

    mock_conn.side_effect = Exception("DB down")
    result = get_recent_activity()
    assert result == []


# ============================================================
# 3. get_agents_needing_attention
# ============================================================

@patch("app.services.console_queries.get_db_connection")
def test_get_agents_needing_attention_success(mock_conn):
    from app.services.console_queries import get_agents_needing_attention

    ctx = MagicMock()
    ctx.execute.return_value.fetchall.side_effect = [
        [{"id": AGENT_ID, "name": "Agent 1", "error_count": 5}],  # error_agents
        [],  # inactive_agents
    ]
    _mock_sync_conn(mock_conn, ctx)

    result = get_agents_needing_attention()
    assert len(result["error_agents"]) == 1
    assert result["error_agents"][0]["error_count"] == 5
    assert result["inactive_agents"] == []


@patch("app.services.console_queries.get_db_connection")
def test_get_agents_needing_attention_error(mock_conn):
    from app.services.console_queries import get_agents_needing_attention

    mock_conn.side_effect = Exception("DB down")
    result = get_agents_needing_attention()
    assert result == {"error_agents": [], "inactive_agents": []}


# ============================================================
# 4. get_all_agents
# ============================================================

@patch("app.services.console_queries.get_db_connection")
def test_get_all_agents_success(mock_conn):
    from app.services.console_queries import get_all_agents

    rows = [
        {"id": AGENT_ID, "name": "Agent One", "contact_count": 15,
         "messages_today": 42, "last_active": date(2026, 3, 9),
         "errors_24h": 0, "current_status": "available",
         "brokerage": "Test RE", "market": "Philly", "twilio_number": "+15551111"},
    ]
    ctx = MagicMock()
    ctx.execute.return_value.fetchall.return_value = rows
    _mock_sync_conn(mock_conn, ctx)

    agents = get_all_agents()
    assert len(agents) == 1
    assert agents[0]["name"] == "Agent One"
    assert agents[0]["contact_count"] == 15


@patch("app.services.console_queries.get_db_connection")
def test_get_all_agents_empty(mock_conn):
    from app.services.console_queries import get_all_agents

    ctx = MagicMock()
    ctx.execute.return_value.fetchall.return_value = None
    _mock_sync_conn(mock_conn, ctx)

    agents = get_all_agents()
    assert agents == []


@patch("app.services.console_queries.get_db_connection")
def test_get_all_agents_error(mock_conn):
    from app.services.console_queries import get_all_agents

    mock_conn.side_effect = Exception("DB down")
    agents = get_all_agents()
    assert agents == []


# ============================================================
# 5. get_agent_detail
# ============================================================

@patch("app.services.console_queries.get_db_connection")
def test_get_agent_detail_success(mock_conn):
    from app.services.console_queries import get_agent_detail

    ctx = MagicMock()
    agent_row = {"id": AGENT_ID, "name": "Test Agent", "email": "t@t.com"}
    contacts_rows = [{"id": "c1", "name": "Sarah"}]
    listings_rows = [{"id": "l1", "address": "123 Oak St"}]
    msgs_rows = [{"body": "Hello", "sender_type": "client"}]
    triggers_rows = []
    cost_row = {"cost": 500, "msgs": 100}
    errors_row = {"cnt": 2}

    ctx.execute.return_value.fetchone.side_effect = [agent_row, cost_row, errors_row]
    ctx.execute.return_value.fetchall.side_effect = [contacts_rows, listings_rows, msgs_rows, triggers_rows]
    _mock_sync_conn(mock_conn, ctx)

    result = get_agent_detail(AGENT_ID)
    assert result is not None
    assert result["agent"]["name"] == "Test Agent"
    assert len(result["contacts"]) == 1
    assert len(result["listings"]) == 1
    assert result["cost_this_month_dollars"] == 5.0
    assert result["errors_24h"] == 2


@patch("app.services.console_queries.get_db_connection")
def test_get_agent_detail_not_found(mock_conn):
    from app.services.console_queries import get_agent_detail

    ctx = MagicMock()
    ctx.execute.return_value.fetchone.return_value = None
    _mock_sync_conn(mock_conn, ctx)

    result = get_agent_detail("nonexistent-id")
    assert result is None


@patch("app.services.console_queries.get_db_connection")
def test_get_agent_detail_error(mock_conn):
    from app.services.console_queries import get_agent_detail

    mock_conn.side_effect = Exception("DB down")
    result = get_agent_detail(AGENT_ID)
    assert result is None


# ============================================================
# 6. get_recent_conversations
# ============================================================

@patch("app.services.console_queries.get_db_connection")
def test_get_recent_conversations_no_filters(mock_conn):
    from app.services.console_queries import get_recent_conversations

    rows = [
        {"id": CONV_ID, "channel": "sms", "last_message_at": datetime.now(timezone.utc),
         "agent_name": "Agent 1", "contact_name": "Sarah", "phone": "+18005551234",
         "msg_count": 5, "last_message": "Hello"},
    ]
    ctx = MagicMock()
    ctx.execute.return_value.fetchall.return_value = rows
    _mock_sync_conn(mock_conn, ctx)

    result = get_recent_conversations()
    assert len(result) == 1
    assert result[0]["channel"] == "sms"


@patch("app.services.console_queries.get_db_connection")
def test_get_recent_conversations_with_filters(mock_conn):
    """Verify filter parameters generate correct WHERE clauses."""
    from app.services.console_queries import get_recent_conversations

    ctx = MagicMock()
    ctx.execute.return_value.fetchall.return_value = []
    _mock_sync_conn(mock_conn, ctx)

    get_recent_conversations(agent_id=AGENT_ID, channel="sms", search="Sarah")

    call_args = ctx.execute.call_args
    sql = call_args[0][0]
    params = call_args[0][1]

    assert "cv.agent_id = %s" in sql
    assert "cv.channel = %s" in sql
    assert "ILIKE" in sql
    assert AGENT_ID in params
    assert "sms" in params
    assert "%Sarah%" in params


@patch("app.services.console_queries.get_db_connection")
def test_get_recent_conversations_error(mock_conn):
    from app.services.console_queries import get_recent_conversations

    mock_conn.side_effect = Exception("DB down")
    result = get_recent_conversations()
    assert result == []


# ============================================================
# 7. get_conversation_detail
# ============================================================

@patch("app.services.console_queries.get_db_connection")
def test_get_conversation_detail_success(mock_conn):
    from app.services.console_queries import get_conversation_detail

    conv_row = {"id": CONV_ID, "agent_id": AGENT_ID, "agent_name": "Agent 1",
                "contact_name": "Sarah", "contact_phone": "+1555",
                "role": "buyer", "lifecycle_stage": "active",
                "contact_id": CONTACT_ID}
    msgs = [{"body": "Hi", "sender_type": "client"}]
    tools = [{"tool_name": "lookup_contact"}]
    triggers = [{"id": TRIGGER_ID, "status": "pending"}]

    ctx = MagicMock()
    ctx.execute.return_value.fetchone.return_value = conv_row
    ctx.execute.return_value.fetchall.side_effect = [msgs, tools, triggers]
    # Make conv_row dict-subscriptable for .get()
    conv_row_mock = MagicMock()
    conv_row_mock.__getitem__ = lambda s, k: conv_row[k]
    conv_row_mock.get = lambda k, d=None: conv_row.get(k, d)

    ctx.execute.return_value.fetchone.return_value = conv_row_mock
    _mock_sync_conn(mock_conn, ctx)

    result = get_conversation_detail(CONV_ID)
    assert result is not None
    assert result["messages"] == msgs
    assert result["tool_executions"] == tools


@patch("app.services.console_queries.get_db_connection")
def test_get_conversation_detail_not_found(mock_conn):
    from app.services.console_queries import get_conversation_detail

    ctx = MagicMock()
    ctx.execute.return_value.fetchone.return_value = None
    _mock_sync_conn(mock_conn, ctx)

    result = get_conversation_detail("nonexistent")
    assert result is None


@patch("app.services.console_queries.get_db_connection")
def test_get_conversation_detail_no_contact(mock_conn):
    """When contact_id is None, triggers query is skipped."""
    from app.services.console_queries import get_conversation_detail

    conv_row = MagicMock()
    conv_row.get.return_value = None  # contact_id is None

    ctx = MagicMock()
    ctx.execute.return_value.fetchone.return_value = conv_row
    ctx.execute.return_value.fetchall.side_effect = [
        [{"body": "Hi"}],  # messages
        [],  # tool_execs
    ]
    _mock_sync_conn(mock_conn, ctx)

    result = get_conversation_detail(CONV_ID)
    assert result is not None
    assert result["triggers"] == []
    # Only 2 fetchall calls (messages + tool_execs), no triggers query
    assert ctx.execute.return_value.fetchall.call_count == 2


@patch("app.services.console_queries.get_db_connection")
def test_get_conversation_detail_error(mock_conn):
    from app.services.console_queries import get_conversation_detail

    mock_conn.side_effect = Exception("DB down")
    result = get_conversation_detail(CONV_ID)
    assert result is None


# ============================================================
# 8. get_trigger_queue
# ============================================================

@patch("app.services.console_queries.get_db_connection")
def test_get_trigger_queue_no_filters(mock_conn):
    from app.services.console_queries import get_trigger_queue

    rows = [{"id": TRIGGER_ID, "agent_name": "Agent 1", "status": "pending"}]
    ctx = MagicMock()
    ctx.execute.return_value.fetchall.return_value = rows
    _mock_sync_conn(mock_conn, ctx)

    result = get_trigger_queue()
    assert len(result) == 1


@patch("app.services.console_queries.get_db_connection")
def test_get_trigger_queue_with_status_filter(mock_conn):
    """Verify status filter generates correct WHERE clause."""
    from app.services.console_queries import get_trigger_queue

    ctx = MagicMock()
    ctx.execute.return_value.fetchall.return_value = []
    _mock_sync_conn(mock_conn, ctx)

    get_trigger_queue(status="error", agent_id=AGENT_ID)

    sql = ctx.execute.call_args[0][0]
    params = ctx.execute.call_args[0][1]
    assert "t.status = %s" in sql
    assert "t.agent_id = %s" in sql
    assert "error" in params
    assert AGENT_ID in params


@patch("app.services.console_queries.get_db_connection")
def test_get_trigger_queue_error(mock_conn):
    from app.services.console_queries import get_trigger_queue

    mock_conn.side_effect = Exception("DB down")
    result = get_trigger_queue()
    assert result == []


# ============================================================
# 9. retry_trigger
# ============================================================

@patch("app.services.console_queries.get_db_connection")
def test_retry_trigger_success(mock_conn):
    from app.services.console_queries import retry_trigger

    ctx = MagicMock()
    _mock_sync_conn(mock_conn, ctx)

    retry_trigger(TRIGGER_ID)
    ctx.execute.assert_called_once()
    assert "pending" in str(ctx.execute.call_args)
    ctx.commit.assert_called_once()


@patch("app.services.console_queries.get_db_connection")
def test_retry_trigger_error_no_raise(mock_conn):
    """retry_trigger swallows exceptions (logs only)."""
    from app.services.console_queries import retry_trigger

    mock_conn.side_effect = Exception("DB down")
    retry_trigger(TRIGGER_ID)  # Should not raise


# ============================================================
# 10. cancel_trigger
# ============================================================

@patch("app.services.console_queries.get_db_connection")
def test_cancel_trigger_success(mock_conn):
    from app.services.console_queries import cancel_trigger

    ctx = MagicMock()
    _mock_sync_conn(mock_conn, ctx)

    cancel_trigger(TRIGGER_ID)
    ctx.execute.assert_called_once()
    assert "cancelled" in str(ctx.execute.call_args)
    ctx.commit.assert_called_once()


# ============================================================
# 11. fire_trigger_now
# ============================================================

@patch("app.services.console_queries.get_db_connection")
def test_fire_trigger_now_success(mock_conn):
    from app.services.console_queries import fire_trigger_now

    ctx = MagicMock()
    _mock_sync_conn(mock_conn, ctx)

    fire_trigger_now(TRIGGER_ID)
    ctx.execute.assert_called_once()
    sql = ctx.execute.call_args[0][0]
    assert "scheduled_at = now()" in sql
    assert "status = 'pending'" in sql
    ctx.commit.assert_called_once()


@patch("app.services.console_queries.get_db_connection")
def test_fire_trigger_now_error_no_raise(mock_conn):
    from app.services.console_queries import fire_trigger_now

    mock_conn.side_effect = Exception("DB down")
    fire_trigger_now(TRIGGER_ID)  # Should not raise


# ============================================================
# 12. get_recent_errors
# ============================================================

@patch("app.services.console_queries.get_db_connection")
def test_get_recent_errors_success(mock_conn):
    from app.services.console_queries import get_recent_errors

    tool_errors = [{"agent_name": "Agent 1", "error_message": "timeout"}]
    app_errors = [{"module": "pipeline", "message": "crash"}]

    ctx = MagicMock()
    ctx.execute.return_value.fetchall.side_effect = [tool_errors, app_errors]
    _mock_sync_conn(mock_conn, ctx)

    result = get_recent_errors()
    assert len(result["tool_errors"]) == 1
    assert len(result["app_errors"]) == 1


@patch("app.services.console_queries.get_db_connection")
def test_get_recent_errors_with_agent_filter(mock_conn):
    from app.services.console_queries import get_recent_errors

    ctx = MagicMock()
    ctx.execute.return_value.fetchall.side_effect = [[], []]
    _mock_sync_conn(mock_conn, ctx)

    get_recent_errors(agent_id=AGENT_ID)
    sql = ctx.execute.call_args_list[0][0][0]
    assert "te.agent_id = %s" in sql


@patch("app.services.console_queries.get_db_connection")
def test_get_recent_errors_db_down(mock_conn):
    from app.services.console_queries import get_recent_errors

    mock_conn.side_effect = Exception("DB down")
    result = get_recent_errors()
    assert result == {"tool_errors": [], "app_errors": []}


# ============================================================
# 13. log_error
# ============================================================

@patch("app.services.console_queries.get_db_connection")
def test_log_error_success(mock_conn):
    from app.services.console_queries import log_error

    ctx = MagicMock()
    _mock_sync_conn(mock_conn, ctx)

    log_error("test_module", "error", "Something broke", agent_id=AGENT_ID,
              context={"key": "value"})
    ctx.execute.assert_called_once()
    ctx.commit.assert_called_once()
    # Verify context was JSON-serialized
    params = ctx.execute.call_args[0][1]
    assert json.loads(params[-1]) == {"key": "value"}


@patch("app.services.console_queries.get_db_connection")
def test_log_error_no_context(mock_conn):
    from app.services.console_queries import log_error

    ctx = MagicMock()
    _mock_sync_conn(mock_conn, ctx)

    log_error("mod", "warning", "Msg")
    params = ctx.execute.call_args[0][1]
    # context should be None when not provided
    assert params[-1] is None


@patch("app.services.console_queries.get_db_connection")
def test_log_error_swallows_exception(mock_conn):
    from app.services.console_queries import log_error

    mock_conn.side_effect = Exception("DB down")
    log_error("mod", "error", "msg")  # Should not raise


# ============================================================
# 14. get_cost_summary
# ============================================================

@patch("app.services.console_queries.get_db_connection")
def test_get_cost_summary_success(mock_conn):
    from app.services.console_queries import get_cost_summary

    row = {
        "total_llm_cost": 1000, "total_sms_cost": 500, "total_voice_cost": 250,
        "total_sms_segments": 200, "total_messages": 3000,
        "total_voice": 120, "total_showings": 25, "total_llm_calls": 800,
    }
    daily = [{"date": date(2026, 3, 1), "cost": 100, "messages": 50,
              "sms_cost": 20, "voice_cost": 10}]

    ctx = MagicMock()
    ctx.execute.return_value.fetchone.return_value = row
    ctx.execute.return_value.fetchall.return_value = daily
    _mock_sync_conn(mock_conn, ctx)

    result = get_cost_summary(days=30)
    assert result["total_cost_dollars"] == 17.50  # (1000+500+250)/100
    assert result["llm_cost_dollars"] == 10.0
    assert result["sms_cost_dollars"] == 5.0
    assert result["voice_cost_dollars"] == 2.50
    assert result["total_messages"] == 3000
    assert result["total_voice_minutes"] == 120.0
    assert result["total_showings"] == 25
    assert result["total_llm_calls"] == 800
    assert len(result["daily"]) == 1


@patch("app.services.console_queries.get_db_connection")
def test_get_cost_summary_error(mock_conn):
    from app.services.console_queries import get_cost_summary

    mock_conn.side_effect = Exception("DB down")
    result = get_cost_summary()
    assert result["total_cost_dollars"] == 0
    assert result["daily"] == []


# ============================================================
# 15. get_cost_by_agent
# ============================================================

@patch("app.services.console_queries.get_db_connection")
def test_get_cost_by_agent_success(mock_conn):
    from app.services.console_queries import get_cost_by_agent

    rows = [
        {"name": "Agent One", "messages": 1500, "llm_calls": 400,
         "tokens": 500000, "llm_cost_cents": 2000, "sms_cost_cents": 300,
         "voice_cost_cents": 200, "sms_segments": 100, "voice_minutes": 60},
    ]
    ctx = MagicMock()
    ctx.execute.return_value.fetchall.return_value = rows
    _mock_sync_conn(mock_conn, ctx)

    result = get_cost_by_agent(days=30)
    assert len(result) == 1
    assert result[0]["name"] == "Agent One"
    assert result[0]["cost_dollars"] == 25.0  # (2000+300+200)/100
    assert result[0]["llm_cost_dollars"] == 20.0
    assert result[0]["sms_cost_dollars"] == 3.0
    assert result[0]["voice_cost_dollars"] == 2.0
    assert result[0]["cost_per_message"] == round(2500 / 1500 / 100, 4)


@patch("app.services.console_queries.get_db_connection")
def test_get_cost_by_agent_zero_messages(mock_conn):
    """cost_per_message uses max(msgs, 1) to avoid division by zero."""
    from app.services.console_queries import get_cost_by_agent

    rows = [
        {"name": "Agent Zero", "messages": 0, "llm_calls": 0,
         "tokens": 0, "llm_cost_cents": 100, "sms_cost_cents": 0,
         "voice_cost_cents": 0, "sms_segments": 0, "voice_minutes": 0},
    ]
    ctx = MagicMock()
    ctx.execute.return_value.fetchall.return_value = rows
    _mock_sync_conn(mock_conn, ctx)

    result = get_cost_by_agent()
    assert result[0]["cost_per_message"] == round(100 / 1 / 100, 4)


@patch("app.services.console_queries.get_db_connection")
def test_get_cost_by_agent_error(mock_conn):
    from app.services.console_queries import get_cost_by_agent

    mock_conn.side_effect = Exception("DB down")
    result = get_cost_by_agent()
    assert result == []


# ============================================================
# 16. get_model_tier_breakdown
# ============================================================

@patch("app.services.console_queries.get_db_connection")
def test_get_model_tier_breakdown_success(mock_conn):
    from app.services.console_queries import get_model_tier_breakdown

    rows = [
        {"model": "template", "cnt": 500},
        {"model": "haiku", "cnt": 300},
        {"model": "sonnet", "cnt": 200},
    ]
    ctx = MagicMock()
    ctx.execute.return_value.fetchall.return_value = rows
    _mock_sync_conn(mock_conn, ctx)

    result = get_model_tier_breakdown(days=30)
    assert result["_total"] == 1000
    assert result["template"]["count"] == 500
    assert result["template"]["pct"] == 50.0
    assert result["haiku"]["pct"] == 30.0
    assert result["sonnet"]["pct"] == 20.0


@patch("app.services.console_queries.get_db_connection")
def test_get_model_tier_breakdown_empty(mock_conn):
    from app.services.console_queries import get_model_tier_breakdown

    ctx = MagicMock()
    ctx.execute.return_value.fetchall.return_value = []
    _mock_sync_conn(mock_conn, ctx)

    result = get_model_tier_breakdown()
    assert result["_total"] == 0


@patch("app.services.console_queries.get_db_connection")
def test_get_model_tier_breakdown_error(mock_conn):
    from app.services.console_queries import get_model_tier_breakdown

    mock_conn.side_effect = Exception("DB down")
    result = get_model_tier_breakdown()
    assert result == {"_total": 0}


# ============================================================
# 17. get_health_overview
# ============================================================

@patch("app.services.console_queries.get_db_connection")
def test_get_health_overview_db_green(mock_conn):
    """When DB is reachable, database service is green."""
    from app.services.console_queries import get_health_overview

    ctx = MagicMock()
    _mock_sync_conn(mock_conn, ctx)

    # get_settings is imported inside the function body via app.config
    with patch("redis.from_url") as mock_redis, \
         patch("app.config.get_settings") as mock_settings:
        mock_settings.return_value.REDIS_URL = "redis://localhost"
        mock_redis.return_value.ping.return_value = True

        result = get_health_overview()
        assert result["services"]["database"] == "green"
        assert result["services"]["redis"] == "green"
        assert "pipeline" in result


@patch("app.services.console_queries.get_db_connection")
def test_get_health_overview_db_red(mock_conn):
    """When DB is down, database service is red."""
    from app.services.console_queries import get_health_overview

    mock_conn.side_effect = Exception("DB down")

    result = get_health_overview()
    assert result["services"]["database"] == "red"


# ============================================================
# 18. get_health_status_color
# ============================================================

@patch("app.services.console_queries.get_db_connection")
def test_get_health_status_color_green(mock_conn):
    from app.services.console_queries import get_health_status_color

    ctx = MagicMock()
    _mock_sync_conn(mock_conn, ctx)

    result = get_health_status_color()
    assert result == "green"


@patch("app.services.console_queries.get_db_connection")
def test_get_health_status_color_red(mock_conn):
    from app.services.console_queries import get_health_status_color

    mock_conn.side_effect = Exception("DB down")
    result = get_health_status_color()
    assert result == "red"


# ============================================================
# 19. create_agent_from_wizard
# ============================================================

def test_create_agent_from_wizard_missing_fields():
    from app.services.console_queries import create_agent_from_wizard

    with pytest.raises(ValueError, match="Missing required field"):
        create_agent_from_wizard({"name": "Test"})


def test_create_agent_from_wizard_missing_email():
    from app.services.console_queries import create_agent_from_wizard

    with pytest.raises(ValueError, match="Missing required field: email"):
        create_agent_from_wizard({"name": "Test", "phone": "+1555",
                                  "twilio_number": "+1556"})


@patch("app.services.console_queries.get_db_connection")
def test_create_agent_from_wizard_duplicate_twilio(mock_conn):
    from app.services.console_queries import create_agent_from_wizard

    ctx = MagicMock()
    ctx.execute.return_value.fetchone.return_value = {"id": "existing"}
    _mock_sync_conn(mock_conn, ctx)

    with pytest.raises(ValueError, match="already assigned"):
        create_agent_from_wizard({
            "name": "Test", "email": "t@t.com",
            "phone": "+1555", "twilio_number": "+1555dup",
        })


@patch("app.services.console_queries.get_db_connection")
def test_create_agent_from_wizard_success(mock_conn):
    from app.services.console_queries import create_agent_from_wizard

    agent_id = str(uuid4())
    ctx = MagicMock()
    # First fetchone: check existing twilio (None), second: INSERT RETURNING id
    ctx.execute.return_value.fetchone.side_effect = [None, {"id": agent_id}]
    _mock_sync_conn(mock_conn, ctx)

    result = create_agent_from_wizard({
        "name": "New Agent", "email": "new@test.com",
        "phone": "+15551234", "twilio_number": "+15559876",
        "tone": "friendly", "autonomy_level": "autonomous",
    })
    assert result["agent_id"] == agent_id
    assert result["agent_name"] == "New Agent"
    assert isinstance(result["checklist"], list)
    assert len(result["checklist"]) == 10
    ctx.commit.assert_called_once()


# ============================================================
# 20. create_agent_tenant
# ============================================================

def test_create_agent_tenant_missing_fields():
    from app.services.console_queries import create_agent_tenant

    with pytest.raises(ValueError, match="Missing required field"):
        create_agent_tenant({"name": "Test"})


@patch("app.services.console_queries.get_db_connection")
def test_create_agent_tenant_duplicate_twilio(mock_conn):
    from app.services.console_queries import create_agent_tenant

    ctx = MagicMock()
    ctx.execute.return_value.fetchone.return_value = {"id": "existing"}
    _mock_sync_conn(mock_conn, ctx)

    with pytest.raises(ValueError, match="already assigned"):
        create_agent_tenant({
            "name": "Test", "email": "t@t.com",
            "phone": "+1555", "twilio_number": "+1555dup",
        })


@patch("app.services.console_queries.get_db_connection")
def test_create_agent_tenant_success(mock_conn):
    from app.services.console_queries import create_agent_tenant

    agent_id = str(uuid4())
    ctx = MagicMock()
    ctx.execute.return_value.fetchone.side_effect = [None, {"id": agent_id}]
    _mock_sync_conn(mock_conn, ctx)

    result = create_agent_tenant({
        "name": "New Agent", "email": "new@test.com",
        "phone": "+15551234", "twilio_number": "+15559876",
    })
    assert result == agent_id
    ctx.commit.assert_called_once()


# ============================================================
# 21. update_agent_tenant
# ============================================================

@patch("app.services.console_queries.get_db_connection")
def test_update_agent_tenant_success(mock_conn):
    from app.services.console_queries import update_agent_tenant

    ctx = MagicMock()
    _mock_sync_conn(mock_conn, ctx)

    with patch("app.services.console_queries.invalidate_agent_cache", create=True):
        update_agent_tenant(AGENT_ID, {
            "name": "Updated Agent", "email": "up@t.com",
            "phone": "+1555", "tone": "casual",
        })
    ctx.execute.assert_called_once()
    ctx.commit.assert_called_once()
    # Verify style_profile JSON was built correctly
    params = ctx.execute.call_args[0][1]
    style = json.loads(params[6])  # style_profile param position
    assert style["tone"] == "casual"


@patch("app.services.console_queries.get_db_connection")
def test_update_agent_tenant_error_raises(mock_conn):
    from app.services.console_queries import update_agent_tenant

    mock_conn.side_effect = Exception("DB down")
    with pytest.raises(ValueError, match="Failed to update agent"):
        update_agent_tenant(AGENT_ID, {"name": "Test"})


# ============================================================
# 22. deactivate_agent
# ============================================================

@patch("app.services.console_queries.get_db_connection")
def test_deactivate_agent_success(mock_conn):
    from app.services.console_queries import deactivate_agent

    ctx = MagicMock()
    _mock_sync_conn(mock_conn, ctx)

    deactivate_agent(AGENT_ID)
    assert ctx.execute.call_count == 2  # agent update + trigger cancel
    ctx.commit.assert_called_once()

    first_sql = ctx.execute.call_args_list[0][0][0]
    assert "deactivated" in first_sql
    second_sql = ctx.execute.call_args_list[1][0][0]
    assert "cancelled" in second_sql


@patch("app.services.console_queries.get_db_connection")
def test_deactivate_agent_error_no_raise(mock_conn):
    from app.services.console_queries import deactivate_agent

    mock_conn.side_effect = Exception("DB down")
    deactivate_agent(AGENT_ID)  # Should not raise


# ============================================================
# 23. send_test_sms
# ============================================================

@patch("app.services.console_queries.get_db_connection")
def test_send_test_sms_agent_not_found(mock_conn):
    from app.services.console_queries import send_test_sms

    ctx = MagicMock()
    ctx.execute.return_value.fetchone.return_value = None
    _mock_sync_conn(mock_conn, ctx)

    # Should not raise when agent not found (no-op)
    send_test_sms(AGENT_ID)


@patch("app.services.console_queries.get_db_connection")
@patch("app.services.console_queries.send_sms", create=True)
def test_send_test_sms_success(mock_sms, mock_conn):
    from app.services.console_queries import send_test_sms

    ctx = MagicMock()
    ctx.execute.return_value.fetchone.return_value = {
        "phone": "+15551234", "twilio_number": "+15559876", "name": "Test Agent",
    }
    _mock_sync_conn(mock_conn, ctx)

    with patch("app.services.twilio_service.send_sms") as mock_send:
        send_test_sms(AGENT_ID)
        mock_send.assert_called_once()


@patch("app.services.console_queries.get_db_connection")
def test_send_test_sms_error_raises(mock_conn):
    from app.services.console_queries import send_test_sms

    mock_conn.side_effect = Exception("DB down")
    with pytest.raises(RuntimeError, match="Test SMS failed"):
        send_test_sms(AGENT_ID)


# ============================================================
# 24. run_manual_scan
# ============================================================

@patch("app.services.console_queries.get_db_connection")
def test_run_manual_scan_error_no_raise(mock_conn):
    """run_manual_scan swallows exceptions."""
    from app.services.console_queries import run_manual_scan

    # Force import to fail gracefully
    with patch("app.worker.daily_scanner.scan_agent", side_effect=Exception("fail")), \
         patch("app.services.agent_config.get_agent_by_id", return_value={"id": AGENT_ID}):
        run_manual_scan(AGENT_ID)  # Should not raise


# ============================================================
# Async function tests
# ============================================================

@pytest.mark.asyncio
async def test_async_get_system_pulse_success():
    from app.services.console_queries import async_get_system_pulse

    mock_conn = AsyncMock()
    mock_cur = AsyncMock()
    mock_cur.fetchone.side_effect = [
        {"cnt": 5}, {"cnt": 200}, {"cnt": 350}, {"cnt": 3}, {"cost": 1250},
    ]
    mock_conn.execute.return_value = mock_cur

    with patch("app.services.console_queries.get_async_db_connection") as mock_get:
        mock_get.return_value.__aenter__ = AsyncMock(return_value=mock_conn)
        mock_get.return_value.__aexit__ = AsyncMock(return_value=False)

        result = await async_get_system_pulse()
        assert result["total_agents"] == 5
        assert result["cost_today_dollars"] == 12.50


@pytest.mark.asyncio
async def test_async_get_system_pulse_error():
    from app.services.console_queries import async_get_system_pulse

    with patch("app.services.console_queries.get_async_db_connection") as mock_get:
        mock_get.return_value.__aenter__ = AsyncMock(side_effect=Exception("DB down"))
        mock_get.return_value.__aexit__ = AsyncMock(return_value=False)

        result = await async_get_system_pulse()
        assert result["total_agents"] == 0


@pytest.mark.asyncio
async def test_async_get_health_status_color_green():
    from app.services.console_queries import async_get_health_status_color

    mock_conn = AsyncMock()
    with patch("app.services.console_queries.get_async_db_connection") as mock_get:
        mock_get.return_value.__aenter__ = AsyncMock(return_value=mock_conn)
        mock_get.return_value.__aexit__ = AsyncMock(return_value=False)

        result = await async_get_health_status_color()
        assert result == "green"


@pytest.mark.asyncio
async def test_async_get_health_status_color_red():
    from app.services.console_queries import async_get_health_status_color

    with patch("app.services.console_queries.get_async_db_connection") as mock_get:
        mock_get.return_value.__aenter__ = AsyncMock(side_effect=Exception("DB down"))
        mock_get.return_value.__aexit__ = AsyncMock(return_value=False)

        result = await async_get_health_status_color()
        assert result == "red"


@pytest.mark.asyncio
async def test_async_update_kb_settings_invalid_policy():
    from app.services.console_queries import async_update_kb_settings

    with pytest.raises(ValueError, match="Invalid KB policy"):
        await async_update_kb_settings(AGENT_ID, "invalid_policy")


@pytest.mark.asyncio
async def test_async_update_kb_settings_success():
    from app.services.console_queries import async_update_kb_settings

    mock_conn = AsyncMock()
    with patch("app.services.console_queries.get_async_db_connection") as mock_get:
        mock_get.return_value.__aenter__ = AsyncMock(return_value=mock_conn)
        mock_get.return_value.__aexit__ = AsyncMock(return_value=False)

        await async_update_kb_settings(AGENT_ID, "auto_remove", default_ttl=90)
        mock_conn.execute.assert_called_once()
        mock_conn.commit.assert_called_once()


@pytest.mark.asyncio
async def test_async_remove_kb_item_success():
    from app.services.console_queries import async_remove_kb_item

    mock_conn = AsyncMock()
    mock_cur = AsyncMock()
    mock_cur.fetchall.return_value = [{"id": "1"}, {"id": "2"}, {"id": "3"}]
    mock_conn.execute.return_value = mock_cur

    with patch("app.services.console_queries.get_async_db_connection") as mock_get:
        mock_get.return_value.__aenter__ = AsyncMock(return_value=mock_conn)
        mock_get.return_value.__aexit__ = AsyncMock(return_value=False)

        count = await async_remove_kb_item(AGENT_ID, "listing", "src-1")
        assert count == 3
        mock_conn.commit.assert_called_once()


@pytest.mark.asyncio
async def test_async_deactivate_agent():
    from app.services.console_queries import async_deactivate_agent

    mock_conn = AsyncMock()
    with patch("app.services.console_queries.get_async_db_connection") as mock_get:
        mock_get.return_value.__aenter__ = AsyncMock(return_value=mock_conn)
        mock_get.return_value.__aexit__ = AsyncMock(return_value=False)

        await async_deactivate_agent(AGENT_ID)
        assert mock_conn.execute.call_count == 2
        mock_conn.commit.assert_called_once()


# ============================================================
# Authorization guard tests
# ============================================================

def test_sync_function_raises_without_context():
    """Sync query functions raise AuthorizationError without console context."""
    from app.services.console_queries import get_system_pulse, AuthorizationError
    clear_console_context()
    with pytest.raises(AuthorizationError):
        get_system_pulse()


@pytest.mark.asyncio
async def test_async_function_raises_without_context():
    """Async query functions raise AuthorizationError without console context."""
    from app.services.console_queries import async_get_system_pulse, AuthorizationError
    clear_console_context()
    with pytest.raises(AuthorizationError):
        await async_get_system_pulse()


def test_context_set_and_cleared():
    """set_console_context / clear_console_context round-trip works."""
    from app.services.console_queries import require_console_context, AuthorizationError
    clear_console_context()
    with pytest.raises(AuthorizationError):
        require_console_context()
    set_console_context({"source": "test"})
    ctx = require_console_context()
    assert ctx["source"] == "test"
    clear_console_context()
    with pytest.raises(AuthorizationError):
        require_console_context()
