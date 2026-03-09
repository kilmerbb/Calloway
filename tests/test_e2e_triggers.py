"""Step 36: E2E trigger system tests — cascade → worker → notification pipeline."""
import pytest
from datetime import datetime, timezone, timedelta
from uuid import UUID, uuid4
from unittest.mock import patch, MagicMock, call

from app.models.schemas import Trigger, AgentConfig, Contact


AGENT_ID = UUID("a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11")
CONTACT_ID = UUID("b1eebc99-9c0b-4ef8-bb6d-6bb9bd380a11")
LISTING_ID = UUID("c1eebc99-9c0b-4ef8-bb6d-6bb9bd380a11")


# Test 1: Full cascade → trigger creation flow
@patch("app.tools.triggers.get_db_connection")
def test_e2e_post_close_cascade_creates_triggers(mock_conn):
    """Post-close cascade creates 5 triggers with correct timing."""
    from app.tools.triggers import create_trigger_cascade

    trigger_count = 0
    created_triggers = []

    def mock_execute_side(*args, **kwargs):
        nonlocal trigger_count
        mock_result = MagicMock()
        if "SELECT id FROM triggers" in args[0]:
            # No duplicates
            mock_result.fetchone.return_value = None
        elif "INSERT INTO triggers" in args[0]:
            trigger_count += 1
            tid = uuid4()
            row = {
                "id": tid, "agent_id": AGENT_ID, "entity_type": "contact",
                "entity_id": CONTACT_ID, "trigger_type": args[1][3],
                "scheduled_at": args[1][4], "action_type": args[1][5],
                "recurrence": args[1][6], "message_template": args[1][7],
                "autonomy_level": args[1][8], "status": "pending",
                "notes": args[1][9], "created_at": datetime.now(timezone.utc),
            }
            mock_result.fetchone.return_value = row
            created_triggers.append(row)
        return mock_result

    ctx = MagicMock()
    ctx.execute.side_effect = mock_execute_side
    mock_conn.return_value.__enter__ = MagicMock(return_value=ctx)
    mock_conn.return_value.__exit__ = MagicMock(return_value=False)

    base_date = datetime(2026, 3, 1, tzinfo=timezone.utc)
    result = create_trigger_cascade(AGENT_ID, "post_close", CONTACT_ID, base_date)

    assert len(result) == 5
    assert trigger_count == 5

    # Check trigger types
    types = [t.trigger_type for t in result]
    assert "review_request" in types
    assert "post_close" in types
    assert types.count("anniversary") == 3

    # Check timing
    dates = sorted([t.scheduled_at for t in result])
    # 7d, 30d, 180d, 365d, 730d
    assert (dates[0] - base_date).days == 7
    assert (dates[-1] - base_date).days == 730


# Test 2: Trigger worker fires and creates recurrence
@patch("app.worker.trigger_worker._increment_triggers_fired")
@patch("app.worker.trigger_worker._mark_trigger")
@patch("app.worker.trigger_worker._send_trigger_message")
@patch("app.worker.trigger_worker.get_db_connection")
def test_e2e_fire_recurring_trigger(mock_conn, mock_send, mock_mark, mock_incr):
    from app.worker.trigger_worker import _fire_trigger, _create_next_recurrence

    now = datetime.now(timezone.utc)
    trigger = Trigger(
        id=uuid4(), agent_id=AGENT_ID, entity_type="contact",
        entity_id=CONTACT_ID, trigger_type="anniversary",
        scheduled_at=now, action_type="send_message",
        recurrence="annually", message_template="Happy homeversary!",
        status="pending",
    )

    # Fire the trigger
    _fire_trigger(trigger)

    # Should have sent message and marked as fired
    mock_send.assert_called_once()
    mock_mark.assert_called_once_with(trigger.id, "fired")

    # Now test recurrence creation
    ctx = MagicMock()
    mock_conn.return_value.__enter__ = MagicMock(return_value=ctx)
    mock_conn.return_value.__exit__ = MagicMock(return_value=False)

    _create_next_recurrence(trigger)

    # Verify next trigger is 365 days later
    insert_args = ctx.execute.call_args[0][1]
    next_scheduled = insert_args[4]
    assert next_scheduled == now + timedelta(days=365)
    assert insert_args[6] == "annually"  # recurrence preserved


# Test 3: Daily scanner → gap analysis → trigger creation
@patch("app.worker.daily_scanner.get_db_connection")
@patch("app.worker.daily_scanner.analyze_contact_gaps")
@patch("app.worker.daily_scanner._check_dom_alerts")
@patch("app.worker.daily_scanner._find_proactive_followups")
@patch("app.tools.triggers.get_db_connection")
def test_e2e_daily_scan_creates_gap_triggers(
    mock_trigger_conn, mock_proactive, mock_dom, mock_gaps, mock_scanner_conn
):
    from app.worker.daily_scanner import scan_agent

    agent = AgentConfig(
        id=AGENT_ID, name="Jane Smith", email="j@e.com", phone="+1",
        twilio_number="+2", style_profile={"tone": "professional"},
        autonomy_rules={"level": "moderate"}, listing_rules={},
    )

    contact = Contact(
        id=CONTACT_ID, agent_id=AGENT_ID, name="Sarah Chen",
        phone="+12675551234", lifecycle_stage="active_buyer",
        last_contact_at=datetime.now(timezone.utc) - timedelta(days=10),
    )

    mock_gaps.return_value = [
        {"contact": contact, "days_since_contact": 10,
         "lifecycle_stage": "active_buyer", "suggested_action": "Send listing alert"},
    ]
    mock_dom.return_value = []
    mock_proactive.return_value = []

    # Mock trigger creation DB
    trigger_ctx = MagicMock()
    trigger_row = {
        "id": uuid4(), "agent_id": AGENT_ID, "entity_type": "contact",
        "entity_id": CONTACT_ID, "trigger_type": "gap_follow_up",
        "scheduled_at": datetime.now(timezone.utc), "action_type": "notify_agent",
        "recurrence": None, "message_template": "test", "autonomy_level": "ask_agent",
        "status": "pending", "notes": None, "created_at": datetime.now(timezone.utc),
    }
    trigger_ctx.execute.return_value.fetchone.side_effect = [None, trigger_row]
    mock_trigger_conn.return_value.__enter__ = MagicMock(return_value=trigger_ctx)
    mock_trigger_conn.return_value.__exit__ = MagicMock(return_value=False)

    result = scan_agent(agent)
    assert result["gaps_found"] == 1
    # Trigger creation should have been called
    assert trigger_ctx.execute.called


# Test 4: Morning briefing end-to-end
@patch("app.worker.daily_scanner.get_db_connection")
@patch("app.worker.daily_scanner.analyze_contact_gaps")
@patch("app.worker.daily_scanner._check_dom_alerts")
def test_e2e_morning_briefing_format(mock_dom, mock_gaps, mock_conn):
    from app.worker.daily_scanner import compile_morning_briefing, format_briefing_text

    mock_gaps.return_value = [
        {"contact": Contact(id=uuid4(), agent_id=AGENT_ID, name="Mike Brown",
                            phone="+1"),
         "days_since_contact": 15, "lifecycle_stage": "active_buyer",
         "suggested_action": "Send listing alert"},
    ]
    mock_dom.return_value = [
        {"listing_id": uuid4(), "address": "456 Elm", "price": 350000, "dom": 60},
    ]

    ctx = MagicMock()
    ctx.execute.return_value.fetchall.side_effect = [
        # showings
        [{"start_time": datetime(2026, 3, 9, 11, 0), "contact_name": "Sarah Chen",
          "address": "123 Oak St", "status": "confirmed"},
         {"start_time": datetime(2026, 3, 9, 14, 0), "contact_name": "Tom Jones",
          "address": "789 Front St", "status": "hold"}],
        # triggers
        [],
        # new leads
        [{"name": "New Person", "phone": "+999", "lifecycle_stage": "new_lead"}],
    ]
    mock_conn.return_value.__enter__ = MagicMock(return_value=ctx)
    mock_conn.return_value.__exit__ = MagicMock(return_value=False)

    agent = AgentConfig(
        id=AGENT_ID, name="Jane Smith", email="j@e.com", phone="+1",
        twilio_number="+2", style_profile={}, autonomy_rules={}, listing_rules={},
    )

    briefing = compile_morning_briefing(agent)
    text = format_briefing_text(briefing)

    # Verify all sections present
    assert "Jane Smith" in text
    assert "Sarah Chen" in text
    assert "Tom Jones" in text
    assert "Mike Brown" in text
    assert "New Person" in text
    assert "456 Elm" in text
    assert "2 showing(s) today" in text
    assert "1 new lead(s)" in text


# Test 5: Open house cascade creates correct sequence
@patch("app.tools.triggers.get_db_connection")
def test_e2e_open_house_cascade_sequence(mock_conn):
    from app.tools.triggers import create_trigger_cascade

    created = []

    def mock_execute_side(*args, **kwargs):
        mock_result = MagicMock()
        if "SELECT id FROM triggers" in args[0]:
            mock_result.fetchone.return_value = None
        elif "INSERT INTO triggers" in args[0]:
            row = {
                "id": uuid4(), "agent_id": AGENT_ID, "entity_type": "listing",
                "entity_id": LISTING_ID, "trigger_type": args[1][3],
                "scheduled_at": args[1][4], "action_type": args[1][5],
                "recurrence": args[1][6], "message_template": args[1][7],
                "autonomy_level": args[1][8], "status": "pending",
                "notes": args[1][9], "created_at": datetime.now(timezone.utc),
            }
            mock_result.fetchone.return_value = row
            created.append(row)
        return mock_result

    ctx = MagicMock()
    ctx.execute.side_effect = mock_execute_side
    mock_conn.return_value.__enter__ = MagicMock(return_value=ctx)
    mock_conn.return_value.__exit__ = MagicMock(return_value=False)

    base_date = datetime(2026, 3, 15, 13, 0, tzinfo=timezone.utc)
    result = create_trigger_cascade(AGENT_ID, "open_house", LISTING_ID, base_date)

    assert len(result) == 5

    # Verify the sequence: -2d promote, morning, +1d attendees, +2d follow-up, +3d report
    sorted_by_time = sorted(result, key=lambda t: t.scheduled_at)
    assert sorted_by_time[0].trigger_type == "open_house"  # -2 days
    assert sorted_by_time[1].trigger_type == "reminder"  # morning of
    assert sorted_by_time[2].trigger_type == "open_house"  # +1 day
    assert sorted_by_time[3].trigger_type == "follow_up"  # +2 days
    assert sorted_by_time[4].trigger_type == "seller_report"  # +3 days


# Test 6: Trigger deduplication prevents double-firing
@patch("app.tools.triggers.get_db_connection")
def test_e2e_trigger_dedup(mock_conn):
    from app.tools.triggers import create_trigger

    existing_id = uuid4()
    now = datetime.now(timezone.utc)
    full_row = {
        "id": existing_id, "agent_id": AGENT_ID, "entity_type": "contact",
        "entity_id": CONTACT_ID, "trigger_type": "follow_up",
        "scheduled_at": now, "action_type": "notify_agent",
        "recurrence": None, "message_template": "test",
        "autonomy_level": "ask_agent", "status": "pending",
        "notes": None, "created_at": now,
    }

    ctx = MagicMock()
    # First call: duplicate found, second call: return full row
    ctx.execute.return_value.fetchone.side_effect = [
        {"id": existing_id},
        full_row,
    ]
    mock_conn.return_value.__enter__ = MagicMock(return_value=ctx)
    mock_conn.return_value.__exit__ = MagicMock(return_value=False)

    result = create_trigger(
        AGENT_ID, "contact", CONTACT_ID, "follow_up", now, "notify_agent",
    )

    # Should return existing trigger, not create new one
    assert result.id == existing_id
    # Should not have called INSERT
    insert_calls = [c for c in ctx.execute.call_args_list if "INSERT" in str(c)]
    assert len(insert_calls) == 0
