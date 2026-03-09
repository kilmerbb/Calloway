"""Steps 32-35: Tests for daily scanner, morning briefing, seller report, proactive follow-up."""
import pytest
from datetime import datetime, timezone, timedelta, time, date
from uuid import UUID, uuid4
from unittest.mock import patch, MagicMock

from app.models.schemas import AgentConfig, Contact

AGENT_ID = UUID("a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11")

MOCK_AGENT = AgentConfig(
    id=AGENT_ID, name="Jane Smith", email="jane@example.com",
    phone="+12675550100", twilio_number="+12675550101",
    brokerage="Test Realty", market="Philadelphia",
    style_profile={"tone": "professional"},
    autonomy_rules={"level": "moderate"},
    listing_rules={"dom_alert_days": [30, 60, 90]},
)


# ============================================================
# Daily scanner tests (Step 32)
# ============================================================

@patch("app.worker.daily_scanner.analyze_contact_gaps")
@patch("app.worker.daily_scanner._check_dom_alerts")
@patch("app.worker.daily_scanner._find_proactive_followups")
@patch("app.worker.daily_scanner._create_gap_trigger")
@patch("app.worker.daily_scanner._create_dom_alert_trigger")
@patch("app.worker.daily_scanner._create_followup_trigger")
def test_scan_agent(mock_followup_trig, mock_dom_trig, mock_gap_trig,
                    mock_proactive, mock_dom, mock_gaps):
    from app.worker.daily_scanner import scan_agent

    mock_gaps.return_value = [
        {"contact": Contact(id=uuid4(), agent_id=AGENT_ID, name="Sarah", phone="+1"),
         "days_since_contact": 10, "lifecycle_stage": "active_buyer",
         "suggested_action": "Send listing alert"},
    ]
    mock_dom.return_value = [
        {"listing_id": uuid4(), "address": "123 Oak", "price": 475000, "dom": 30, "threshold": 30},
    ]
    mock_proactive.return_value = [
        {"contact_id": uuid4(), "name": "New Lead", "phone": "+2", "days_since": 3},
    ]

    result = scan_agent(MOCK_AGENT)
    assert result["gaps_found"] == 1
    assert result["dom_alerts"] == 1
    assert result["proactive_followups"] == 1
    mock_gap_trig.assert_called_once()
    mock_dom_trig.assert_called_once()
    mock_followup_trig.assert_called_once()


@patch("app.worker.daily_scanner.analyze_contact_gaps")
@patch("app.worker.daily_scanner._check_dom_alerts")
@patch("app.worker.daily_scanner._find_proactive_followups")
def test_scan_agent_nothing_found(mock_proactive, mock_dom, mock_gaps):
    from app.worker.daily_scanner import scan_agent

    mock_gaps.return_value = []
    mock_dom.return_value = []
    mock_proactive.return_value = []

    result = scan_agent(MOCK_AGENT)
    assert result["gaps_found"] == 0
    assert result["dom_alerts"] == 0
    assert result["proactive_followups"] == 0


# ============================================================
# Morning briefing tests (Step 33)
# ============================================================

@patch("app.worker.daily_scanner.get_db_connection")
@patch("app.worker.daily_scanner.analyze_contact_gaps")
@patch("app.worker.daily_scanner._check_dom_alerts")
def test_compile_morning_briefing(mock_dom, mock_gaps, mock_conn):
    from app.worker.daily_scanner import compile_morning_briefing

    mock_gaps.return_value = []
    mock_dom.return_value = []

    ctx = MagicMock()
    # showings, triggers, new_leads
    ctx.execute.return_value.fetchall.side_effect = [
        [{"start_time": datetime(2026, 3, 9, 11, 0), "contact_name": "Sarah Chen",
          "address": "123 Oak St", "status": "confirmed"}],
        [{"trigger_type": "follow_up", "message_template": "Check in with Mike",
          "scheduled_at": datetime(2026, 3, 9, 14, 0)}],
        [],
    ]
    mock_conn.return_value.__enter__ = MagicMock(return_value=ctx)
    mock_conn.return_value.__exit__ = MagicMock(return_value=False)

    briefing = compile_morning_briefing(MOCK_AGENT)
    assert briefing["agent_name"] == "Jane Smith"
    assert len(briefing["showings_today"]) == 1
    assert briefing["showings_today"][0]["client"] == "Sarah Chen"
    assert len(briefing["triggers_today"]) == 1


def test_format_briefing_text():
    from app.worker.daily_scanner import format_briefing_text

    briefing = {
        "agent_name": "Jane Smith",
        "date": "Monday, March 09",
        "showings_today": [
            {"time": "11:00 AM", "client": "Sarah Chen", "address": "123 Oak St", "status": "confirmed"},
        ],
        "triggers_today": [
            {"type": "follow_up", "message": "Check in with Mike", "time": "02:00 PM"},
        ],
        "gaps": [
            {"name": "John Doe", "days": 15, "action": "Send listing alert"},
        ],
        "new_leads": [],
        "dom_alerts": [],
    }

    text = format_briefing_text(briefing)
    assert "Jane Smith" in text
    assert "Sarah Chen" in text
    assert "123 Oak St" in text
    assert "Check in with Mike" in text
    assert "John Doe" in text
    assert "No showings" not in text  # has a showing


def test_format_briefing_text_empty_day():
    from app.worker.daily_scanner import format_briefing_text

    briefing = {
        "agent_name": "Jane Smith",
        "date": "Monday, March 09",
        "showings_today": [],
        "triggers_today": [],
        "gaps": [],
        "new_leads": [],
        "dom_alerts": [],
    }

    text = format_briefing_text(briefing)
    assert "No showings today" in text


# ============================================================
# Seller report tests (Step 34)
# ============================================================

@patch("app.worker.daily_scanner.get_db_connection")
def test_compile_seller_report(mock_conn):
    from app.worker.daily_scanner import compile_seller_report

    listing_id = uuid4()
    ctx = MagicMock()
    ctx.execute.return_value.fetchone.side_effect = [
        # listing
        {"id": listing_id, "address": "123 Oak St", "price": 475000,
         "status": "active", "list_date": date(2026, 2, 1),
         "agent_id": AGENT_ID},
        # showings count
        {"cnt": 3},
        # inquiries count
        {"cnt": 5},
    ]
    ctx.execute.return_value.fetchall.return_value = [
        {"name": "Sarah", "feedback": "Loved the kitchen"},
    ]
    mock_conn.return_value.__enter__ = MagicMock(return_value=ctx)
    mock_conn.return_value.__exit__ = MagicMock(return_value=False)

    report = compile_seller_report(MOCK_AGENT, listing_id)
    assert report["listing"]["address"] == "123 Oak St"
    assert report["showings_count"] == 3
    assert report["inquiries_count"] == 5
    assert len(report["feedback_summary"]) == 1


@patch("app.worker.daily_scanner.get_db_connection")
def test_compile_seller_report_not_found(mock_conn):
    from app.worker.daily_scanner import compile_seller_report

    ctx = MagicMock()
    ctx.execute.return_value.fetchone.return_value = None
    mock_conn.return_value.__enter__ = MagicMock(return_value=ctx)
    mock_conn.return_value.__exit__ = MagicMock(return_value=False)

    report = compile_seller_report(MOCK_AGENT, uuid4())
    assert report["listing"] is None


def test_format_seller_report():
    from app.worker.daily_scanner import format_seller_report

    report = {
        "listing": {"address": "123 Oak St", "price": 475000, "status": "active"},
        "period": "Mar 02 - Mar 09",
        "showings_count": 3,
        "inquiries_count": 5,
        "feedback_summary": [{"client": "Sarah", "feedback": "Loved the kitchen"}],
        "dom": 36,
    }

    text = format_seller_report(report)
    assert "123 Oak St" in text
    assert "DOM: 36" in text
    assert "$475,000" in text
    assert "Loved the kitchen" in text


def test_format_seller_report_not_found():
    from app.worker.daily_scanner import format_seller_report

    report = {
        "listing": None,
        "period": "Mar 02 - Mar 09",
        "showings_count": 0,
        "inquiries_count": 0,
        "feedback_summary": [],
        "dom": 0,
    }

    text = format_seller_report(report)
    assert text == "Listing not found."


# ============================================================
# DOM alert check test
# ============================================================

@patch("app.worker.daily_scanner.get_db_connection")
def test_check_dom_alerts(mock_conn):
    from app.worker.daily_scanner import _check_dom_alerts

    today = datetime.now(timezone.utc).date()
    ctx = MagicMock()
    ctx.execute.return_value.fetchall.return_value = [
        {
            "id": uuid4(), "address": "123 Oak St", "price": 475000,
            "list_date": today - timedelta(days=30), "status": "active",
        },
        {
            "id": uuid4(), "address": "456 Elm St", "price": 350000,
            "list_date": today - timedelta(days=15), "status": "active",
        },
    ]
    mock_conn.return_value.__enter__ = MagicMock(return_value=ctx)
    mock_conn.return_value.__exit__ = MagicMock(return_value=False)

    alerts = _check_dom_alerts(MOCK_AGENT)
    # Only 123 Oak (30 days) should trigger; 456 Elm (15 days) should not
    assert len(alerts) == 1
    assert alerts[0]["address"] == "123 Oak St"
    assert alerts[0]["dom"] == 30


# ============================================================
# Proactive follow-up test (Step 35)
# ============================================================

@patch("app.worker.daily_scanner.get_db_connection")
def test_find_proactive_followups(mock_conn):
    from app.worker.daily_scanner import _find_proactive_followups

    now = datetime.now(timezone.utc)
    ctx = MagicMock()
    ctx.execute.return_value.fetchall.return_value = [
        {
            "id": uuid4(), "name": "Cool Lead", "phone": "+1234567890",
            "last_contact_at": now - timedelta(days=3),
        },
    ]
    mock_conn.return_value.__enter__ = MagicMock(return_value=ctx)
    mock_conn.return_value.__exit__ = MagicMock(return_value=False)

    followups = _find_proactive_followups(MOCK_AGENT)
    assert len(followups) == 1
    assert followups[0]["name"] == "Cool Lead"
