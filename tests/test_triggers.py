"""Step 31: Tests for trigger tools, cascade creator, and trigger worker."""
import pytest
from datetime import datetime, timezone, timedelta
from uuid import UUID, uuid4
from unittest.mock import patch, MagicMock

from app.models.schemas import Trigger

AGENT_ID = UUID("a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11")
CONTACT_ID = UUID("b1eebc99-9c0b-4ef8-bb6d-6bb9bd380a11")
LISTING_ID = UUID("c1eebc99-9c0b-4ef8-bb6d-6bb9bd380a11")


# ============================================================
# Trigger tool tests
# ============================================================

@patch("app.tools.triggers.get_db_connection")
def test_create_trigger_new(mock_conn):
    from app.tools.triggers import create_trigger

    trigger_id = uuid4()
    now = datetime.now(timezone.utc)
    row = {
        "id": trigger_id, "agent_id": AGENT_ID, "entity_type": "contact",
        "entity_id": CONTACT_ID, "trigger_type": "follow_up",
        "scheduled_at": now + timedelta(days=1), "action_type": "notify_agent",
        "recurrence": None, "message_template": "Follow up with client",
        "autonomy_level": "ask_agent", "status": "pending",
        "notes": None, "created_at": now,
    }

    ctx = MagicMock()
    ctx.execute.return_value.fetchone.side_effect = [None, row]
    mock_conn.return_value.__enter__ = MagicMock(return_value=ctx)
    mock_conn.return_value.__exit__ = MagicMock(return_value=False)

    result = create_trigger(
        AGENT_ID, "contact", CONTACT_ID, "follow_up",
        now + timedelta(days=1), "notify_agent",
        message_template="Follow up with client",
    )
    assert isinstance(result, Trigger)
    assert result.trigger_type == "follow_up"


@patch("app.tools.triggers.get_db_connection")
def test_create_trigger_duplicate_skipped(mock_conn):
    from app.tools.triggers import create_trigger

    trigger_id = uuid4()
    now = datetime.now(timezone.utc)
    existing = {"id": trigger_id}
    full_row = {
        "id": trigger_id, "agent_id": AGENT_ID, "entity_type": "contact",
        "entity_id": CONTACT_ID, "trigger_type": "follow_up",
        "scheduled_at": now, "action_type": "notify_agent",
        "recurrence": None, "message_template": None,
        "autonomy_level": "ask_agent", "status": "pending",
        "notes": None, "created_at": now,
    }

    ctx = MagicMock()
    ctx.execute.return_value.fetchone.side_effect = [existing, full_row]
    mock_conn.return_value.__enter__ = MagicMock(return_value=ctx)
    mock_conn.return_value.__exit__ = MagicMock(return_value=False)

    result = create_trigger(
        AGENT_ID, "contact", CONTACT_ID, "follow_up", now, "notify_agent",
    )
    assert isinstance(result, Trigger)


@patch("app.tools.triggers.get_db_connection")
def test_get_triggers(mock_conn):
    from app.tools.triggers import get_triggers

    now = datetime.now(timezone.utc)
    rows = [
        {
            "id": uuid4(), "agent_id": AGENT_ID, "entity_type": "contact",
            "entity_id": CONTACT_ID, "trigger_type": "follow_up",
            "scheduled_at": now, "action_type": "notify_agent",
            "recurrence": None, "message_template": None,
            "autonomy_level": "ask_agent", "status": "pending",
            "notes": None, "created_at": now,
        }
    ]

    ctx = MagicMock()
    ctx.execute.return_value.fetchall.return_value = rows
    mock_conn.return_value.__enter__ = MagicMock(return_value=ctx)
    mock_conn.return_value.__exit__ = MagicMock(return_value=False)

    result = get_triggers(AGENT_ID)
    assert len(result) == 1
    assert result[0].trigger_type == "follow_up"


@patch("app.tools.triggers.get_db_connection")
def test_get_triggers_with_contact_filter(mock_conn):
    from app.tools.triggers import get_triggers

    ctx = MagicMock()
    ctx.execute.return_value.fetchall.return_value = []
    mock_conn.return_value.__enter__ = MagicMock(return_value=ctx)
    mock_conn.return_value.__exit__ = MagicMock(return_value=False)

    result = get_triggers(AGENT_ID, contact_id=CONTACT_ID)
    assert result == []
    # Verify the query included entity_id filter
    call_args = ctx.execute.call_args
    assert "entity_id" in call_args[0][0]


# ============================================================
# Cascade tests
# ============================================================

@patch("app.tools.triggers.create_trigger")
def test_cascade_transaction_deadlines(mock_create):
    from app.tools.triggers import create_trigger_cascade

    mock_create.return_value = Trigger(
        id=uuid4(), agent_id=AGENT_ID, entity_type="contact",
        entity_id=CONTACT_ID, trigger_type="deadline",
        scheduled_at=datetime.now(timezone.utc), action_type="both",
        status="pending",
    )

    now = datetime.now(timezone.utc)
    deadlines = {
        "inspection": (now + timedelta(days=10)).isoformat(),
        "appraisal": (now + timedelta(days=20)).isoformat(),
    }

    result = create_trigger_cascade(
        AGENT_ID, "transaction_deadlines", CONTACT_ID, now,
        params={"deadlines": deadlines},
    )
    # 4 triggers per deadline × 2 deadlines = 8
    assert len(result) == 8
    assert mock_create.call_count == 8


@patch("app.tools.triggers.create_trigger")
def test_cascade_open_house(mock_create):
    from app.tools.triggers import create_trigger_cascade

    mock_create.return_value = Trigger(
        id=uuid4(), agent_id=AGENT_ID, entity_type="listing",
        entity_id=LISTING_ID, trigger_type="open_house",
        scheduled_at=datetime.now(timezone.utc), action_type="send_message",
        status="pending",
    )

    base = datetime.now(timezone.utc) + timedelta(days=5)
    result = create_trigger_cascade(AGENT_ID, "open_house", LISTING_ID, base)
    # 5 triggers: -2d, morning, +1d, +2d, +3d
    assert len(result) == 5
    assert mock_create.call_count == 5


@patch("app.tools.triggers.create_trigger")
def test_cascade_post_close(mock_create):
    from app.tools.triggers import create_trigger_cascade

    mock_create.return_value = Trigger(
        id=uuid4(), agent_id=AGENT_ID, entity_type="contact",
        entity_id=CONTACT_ID, trigger_type="review_request",
        scheduled_at=datetime.now(timezone.utc), action_type="send_message",
        status="pending",
    )

    base = datetime.now(timezone.utc)
    result = create_trigger_cascade(AGENT_ID, "post_close", CONTACT_ID, base)
    # 5 triggers: 7d, 30d, 180d, 365d, 730d
    assert len(result) == 5
    assert mock_create.call_count == 5


@patch("app.tools.triggers.create_trigger")
def test_cascade_unknown_type(mock_create):
    from app.tools.triggers import create_trigger_cascade

    result = create_trigger_cascade(
        AGENT_ID, "unknown_cascade", CONTACT_ID, datetime.now(timezone.utc),
    )
    assert result == []
    assert mock_create.call_count == 0


# ============================================================
# Trigger worker tests
# ============================================================

@patch("app.worker.trigger_worker.get_db_connection")
@patch("app.worker.trigger_worker._fire_trigger")
def test_process_due_triggers(mock_fire, mock_conn):
    from app.worker.trigger_worker import process_due_triggers

    now = datetime.now(timezone.utc)
    rows = [
        {
            "id": uuid4(), "agent_id": AGENT_ID, "entity_type": "contact",
            "entity_id": CONTACT_ID, "trigger_type": "follow_up",
            "scheduled_at": now - timedelta(minutes=5), "action_type": "notify_agent",
            "recurrence": None, "message_template": "Follow up",
            "autonomy_level": "ask_agent", "status": "pending",
            "notes": None, "created_at": now,
        }
    ]

    ctx = MagicMock()
    ctx.execute.return_value.fetchall.return_value = rows
    mock_conn.return_value.__enter__ = MagicMock(return_value=ctx)
    mock_conn.return_value.__exit__ = MagicMock(return_value=False)

    fired = process_due_triggers()
    assert fired == 1
    assert mock_fire.call_count == 1


@patch("app.worker.trigger_worker.get_db_connection")
def test_process_due_triggers_none_due(mock_conn):
    from app.worker.trigger_worker import process_due_triggers

    ctx = MagicMock()
    ctx.execute.return_value.fetchall.return_value = []
    mock_conn.return_value.__enter__ = MagicMock(return_value=ctx)
    mock_conn.return_value.__exit__ = MagicMock(return_value=False)

    fired = process_due_triggers()
    assert fired == 0


@patch("app.worker.trigger_worker.get_db_connection")
def test_revert_expired_statuses(mock_conn):
    from app.worker.trigger_worker import revert_expired_statuses

    ctx = MagicMock()
    ctx.execute.return_value.fetchall.return_value = [{"id": uuid4()}]
    mock_conn.return_value.__enter__ = MagicMock(return_value=ctx)
    mock_conn.return_value.__exit__ = MagicMock(return_value=False)

    count = revert_expired_statuses()
    assert count == 1


@patch("app.worker.trigger_worker._increment_triggers_fired")
@patch("app.worker.trigger_worker._mark_trigger")
@patch("app.worker.trigger_worker._notify_agent")
def test_fire_trigger_notify(mock_notify, mock_mark, mock_incr):
    from app.worker.trigger_worker import _fire_trigger

    trigger = Trigger(
        id=uuid4(), agent_id=AGENT_ID, entity_type="contact",
        entity_id=CONTACT_ID, trigger_type="follow_up",
        scheduled_at=datetime.now(timezone.utc), action_type="notify_agent",
        status="pending",
    )

    _fire_trigger(trigger)
    mock_notify.assert_called_once()
    mock_mark.assert_called_once_with(trigger.id, "fired")
    mock_incr.assert_called_once_with(AGENT_ID)


@patch("app.worker.trigger_worker._increment_triggers_fired")
@patch("app.worker.trigger_worker._mark_trigger")
@patch("app.worker.trigger_worker._create_next_recurrence")
@patch("app.worker.trigger_worker._send_trigger_message")
def test_fire_trigger_with_recurrence(mock_send, mock_recur, mock_mark, mock_incr):
    from app.worker.trigger_worker import _fire_trigger

    trigger = Trigger(
        id=uuid4(), agent_id=AGENT_ID, entity_type="contact",
        entity_id=CONTACT_ID, trigger_type="anniversary",
        scheduled_at=datetime.now(timezone.utc), action_type="send_message",
        recurrence="annually", message_template="Happy homeversary!",
        status="pending",
    )

    _fire_trigger(trigger)
    mock_send.assert_called_once()
    mock_recur.assert_called_once_with(trigger)
    mock_mark.assert_called_once_with(trigger.id, "fired")


@patch("app.worker.trigger_worker.get_db_connection")
def test_create_next_recurrence_annually(mock_conn):
    from app.worker.trigger_worker import _create_next_recurrence

    now = datetime.now(timezone.utc)
    trigger = Trigger(
        id=uuid4(), agent_id=AGENT_ID, entity_type="contact",
        entity_id=CONTACT_ID, trigger_type="anniversary",
        scheduled_at=now, action_type="send_message",
        recurrence="annually", message_template="Happy homeversary!",
        status="pending",
    )

    ctx = MagicMock()
    mock_conn.return_value.__enter__ = MagicMock(return_value=ctx)
    mock_conn.return_value.__exit__ = MagicMock(return_value=False)

    _create_next_recurrence(trigger)

    # Verify INSERT was called with scheduled_at = now + 365 days
    call_args = ctx.execute.call_args[0][1]
    next_date = call_args[4]  # scheduled_at is 5th param
    assert next_date == now + timedelta(days=365)
