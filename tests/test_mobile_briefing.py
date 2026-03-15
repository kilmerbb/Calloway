"""Tests for mobile briefing and schedule API endpoints."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime, timezone

from fastapi.testclient import TestClient

from app.main import app
from app.api.mobile.deps import get_current_agent

AGENT_ID = "12345678-1234-1234-1234-123456789012"


@pytest.fixture(autouse=True)
def override_auth():
    app.dependency_overrides[get_current_agent] = lambda: AGENT_ID
    yield
    app.dependency_overrides.clear()


def _make_async_cm(mock_conn):
    """Wrap a mock connection in an async context manager."""
    cm = MagicMock()
    cm.__aenter__ = AsyncMock(return_value=mock_conn)
    cm.__aexit__ = AsyncMock(return_value=False)
    return cm


# -----------------------------------------------------------------------
# GET /api/v1/mobile/briefing/today
# -----------------------------------------------------------------------


class TestBriefingToday:
    """Tests for the get_briefing_today endpoint."""

    @patch("app.api.mobile.briefing.get_async_db_connection")
    def test_briefing_returns_all_sections(self, mock_get_conn):
        """Briefing response contains all 6 sections."""
        showing_row = {
            "id": "s001",
            "start_time": datetime(2026, 3, 15, 14, 0, tzinfo=timezone.utc),
            "end_time": datetime(2026, 3, 15, 15, 0, tzinfo=timezone.utc),
            "status": "confirmed",
            "contact_name": "Jane Doe",
            "listing_address": "123 Main St",
        }
        approval_row = {
            "trigger_id": "t001",
            "trigger_type": "follow_up",
            "message_template": "Just checking in...",
            "scheduled_at": datetime(2026, 3, 15, 10, 0, tzinfo=timezone.utc),
            "contact_name": "Bob Smith",
        }
        follow_up_row = {
            "trigger_id": "t002",
            "trigger_type": "gap_follow_up",
            "scheduled_at": datetime(2026, 3, 15, 11, 0, tzinfo=timezone.utc),
            "message_template": "Haven't heard from you...",
            "contact_name": "Alice Jones",
        }
        lead_row = {
            "id": "l001",
            "name": "New Lead",
            "phone": "+15551112222",
            "lead_source": "zillow",
        }

        # _get_agent_timezone makes its own connection
        tz_conn = MagicMock()
        tz_result = AsyncMock()
        tz_result.fetchone = AsyncMock(return_value={"timezone": "America/New_York"})
        tz_conn.execute = AsyncMock(return_value=tz_result)

        # Each _fetch_* helper creates its own connection via get_async_db_connection
        # showings
        show_conn = MagicMock()
        show_result = AsyncMock()
        show_result.fetchall = AsyncMock(return_value=[showing_row])
        show_conn.execute = AsyncMock(return_value=show_result)

        # approvals
        appr_conn = MagicMock()
        appr_result = AsyncMock()
        appr_result.fetchall = AsyncMock(return_value=[approval_row])
        appr_conn.execute = AsyncMock(return_value=appr_result)

        # follow_ups
        fu_conn = MagicMock()
        fu_result = AsyncMock()
        fu_result.fetchall = AsyncMock(return_value=[follow_up_row])
        fu_conn.execute = AsyncMock(return_value=fu_result)

        # new_leads
        nl_conn = MagicMock()
        nl_result = AsyncMock()
        nl_result.fetchall = AsyncMock(return_value=[lead_row])
        nl_conn.execute = AsyncMock(return_value=nl_result)

        # messages count
        msg_conn = MagicMock()
        msg_result = AsyncMock()
        msg_result.fetchone = AsyncMock(return_value={"cnt": 7})
        msg_conn.execute = AsyncMock(return_value=msg_result)

        # txn count
        txn_conn = MagicMock()
        txn_result = AsyncMock()
        txn_result.fetchone = AsyncMock(return_value={"cnt": 3})
        txn_conn.execute = AsyncMock(return_value=txn_result)

        # Return connections in order: tz, showings, approvals, follow_ups, leads, msgs, txns
        mock_get_conn.return_value = _make_async_cm(tz_conn)
        mock_get_conn.side_effect = [
            _make_async_cm(tz_conn),
            _make_async_cm(show_conn),
            _make_async_cm(appr_conn),
            _make_async_cm(fu_conn),
            _make_async_cm(nl_conn),
            _make_async_cm(msg_conn),
            _make_async_cm(txn_conn),
        ]

        client = TestClient(app)
        resp = client.get("/api/v1/mobile/briefing/today")

        assert resp.status_code == 200
        body = resp.json()

        # All 6 sections present
        assert "showings_today" in body
        assert "pending_approvals" in body
        assert "follow_ups_due" in body
        assert "new_leads_since_yesterday" in body
        assert "messages_received_today" in body
        assert "active_transaction_count" in body

        # Verify data
        assert len(body["showings_today"]) == 1
        assert body["showings_today"][0]["contact_name"] == "Jane Doe"

        assert len(body["pending_approvals"]) == 1
        assert body["pending_approvals"][0]["trigger_type"] == "follow_up"

        assert len(body["follow_ups_due"]) == 1
        assert body["follow_ups_due"][0]["trigger_type"] == "gap_follow_up"

        assert len(body["new_leads_since_yesterday"]) == 1
        assert body["new_leads_since_yesterday"][0]["name"] == "New Lead"

        assert body["messages_received_today"] == 7
        assert body["active_transaction_count"] == 3

    @patch("app.api.mobile.briefing.get_async_db_connection")
    def test_briefing_timezone_aware(self, mock_get_conn):
        """Briefing uses agent's configured timezone."""
        # tz connection returns Pacific timezone
        tz_conn = MagicMock()
        tz_result = AsyncMock()
        tz_result.fetchone = AsyncMock(return_value={"timezone": "America/Los_Angeles"})
        tz_conn.execute = AsyncMock(return_value=tz_result)

        # All other helpers return empty/zero results
        def _empty_list_conn():
            conn = MagicMock()
            result = AsyncMock()
            result.fetchall = AsyncMock(return_value=[])
            conn.execute = AsyncMock(return_value=result)
            return conn

        def _zero_count_conn():
            conn = MagicMock()
            result = AsyncMock()
            result.fetchone = AsyncMock(return_value={"cnt": 0})
            conn.execute = AsyncMock(return_value=result)
            return conn

        mock_get_conn.side_effect = [
            _make_async_cm(tz_conn),           # _get_agent_timezone
            _make_async_cm(_empty_list_conn()), # showings
            _make_async_cm(_empty_list_conn()), # approvals
            _make_async_cm(_empty_list_conn()), # follow_ups
            _make_async_cm(_empty_list_conn()), # new_leads
            _make_async_cm(_zero_count_conn()), # msg count
            _make_async_cm(_zero_count_conn()), # txn count
        ]

        client = TestClient(app)
        resp = client.get("/api/v1/mobile/briefing/today")

        assert resp.status_code == 200
        body = resp.json()
        assert body["timezone"] == "America/Los_Angeles"
        assert body["date"]  # non-empty date string

    @patch("app.api.mobile.briefing.get_async_db_connection")
    def test_briefing_empty_results(self, mock_get_conn):
        """Briefing with no data returns empty lists and zero counts."""
        tz_conn = MagicMock()
        tz_result = AsyncMock()
        tz_result.fetchone = AsyncMock(return_value={"timezone": "America/New_York"})
        tz_conn.execute = AsyncMock(return_value=tz_result)

        def _empty_conn():
            conn = MagicMock()
            result = AsyncMock()
            result.fetchall = AsyncMock(return_value=[])
            conn.execute = AsyncMock(return_value=result)
            return conn

        def _zero_conn():
            conn = MagicMock()
            result = AsyncMock()
            result.fetchone = AsyncMock(return_value={"cnt": 0})
            conn.execute = AsyncMock(return_value=result)
            return conn

        mock_get_conn.side_effect = [
            _make_async_cm(tz_conn),
            _make_async_cm(_empty_conn()),
            _make_async_cm(_empty_conn()),
            _make_async_cm(_empty_conn()),
            _make_async_cm(_empty_conn()),
            _make_async_cm(_zero_conn()),
            _make_async_cm(_zero_conn()),
        ]

        client = TestClient(app)
        resp = client.get("/api/v1/mobile/briefing/today")

        assert resp.status_code == 200
        body = resp.json()
        assert body["showings_today"] == []
        assert body["pending_approvals"] == []
        assert body["follow_ups_due"] == []
        assert body["new_leads_since_yesterday"] == []
        assert body["messages_received_today"] == 0
        assert body["active_transaction_count"] == 0


# -----------------------------------------------------------------------
# GET /api/v1/mobile/schedule/today
# -----------------------------------------------------------------------


class TestScheduleToday:
    """Tests for the get_schedule_today endpoint."""

    @patch("app.api.mobile.briefing.get_async_db_connection")
    def test_schedule_returns_events(self, mock_get_conn):
        """Schedule returns showing events for today."""
        event_row = {
            "id": "s001",
            "start_time": datetime(2026, 3, 15, 14, 0, tzinfo=timezone.utc),
            "end_time": datetime(2026, 3, 15, 15, 0, tzinfo=timezone.utc),
            "status": "confirmed",
            "contact_name": "Jane Doe",
            "contact_id": "c001",
            "listing_address": "123 Main St",
            "listing_id": "lst001",
        }

        # _get_agent_timezone
        tz_conn = MagicMock()
        tz_result = AsyncMock()
        tz_result.fetchone = AsyncMock(return_value={"timezone": "America/New_York"})
        tz_conn.execute = AsyncMock(return_value=tz_result)

        # Schedule query
        sched_conn = MagicMock()
        sched_result = AsyncMock()
        sched_result.fetchall = AsyncMock(return_value=[event_row])
        sched_conn.execute = AsyncMock(return_value=sched_result)

        mock_get_conn.side_effect = [
            _make_async_cm(tz_conn),
            _make_async_cm(sched_conn),
        ]

        client = TestClient(app)
        resp = client.get("/api/v1/mobile/schedule/today")

        assert resp.status_code == 200
        body = resp.json()
        assert body["timezone"] == "America/New_York"
        assert body["date"]  # non-empty

        assert len(body["events"]) == 1
        event = body["events"][0]
        assert event["type"] == "showing"
        assert event["id"] == "s001"
        assert event["status"] == "confirmed"
        assert event["contact_name"] == "Jane Doe"
        assert event["contact_id"] == "c001"
        assert event["listing_address"] == "123 Main St"
        assert event["listing_id"] == "lst001"

    @patch("app.api.mobile.briefing.get_async_db_connection")
    def test_schedule_excludes_cancelled(self, mock_get_conn):
        """Schedule query filters out cancelled showings (verified via SQL)."""
        # _get_agent_timezone
        tz_conn = MagicMock()
        tz_result = AsyncMock()
        tz_result.fetchone = AsyncMock(return_value={"timezone": "America/Chicago"})
        tz_conn.execute = AsyncMock(return_value=tz_result)

        # Schedule query returns only non-cancelled
        confirmed_event = {
            "id": "s001",
            "start_time": datetime(2026, 3, 15, 14, 0, tzinfo=timezone.utc),
            "end_time": datetime(2026, 3, 15, 15, 0, tzinfo=timezone.utc),
            "status": "confirmed",
            "contact_name": "Jane Doe",
            "contact_id": "c001",
            "listing_address": "123 Main St",
            "listing_id": "lst001",
        }
        sched_conn = MagicMock()
        sched_result = AsyncMock()
        sched_result.fetchall = AsyncMock(return_value=[confirmed_event])
        sched_conn.execute = AsyncMock(return_value=sched_result)

        mock_get_conn.side_effect = [
            _make_async_cm(tz_conn),
            _make_async_cm(sched_conn),
        ]

        client = TestClient(app)
        resp = client.get("/api/v1/mobile/schedule/today")

        assert resp.status_code == 200
        body = resp.json()
        assert len(body["events"]) == 1

        # Verify the SQL query contains the NOT IN ('cancelled') filter
        sql_query = sched_conn.execute.call_args[0][0]
        assert "cancelled" in sql_query
        assert "NOT IN" in sql_query

    @patch("app.api.mobile.briefing.get_async_db_connection")
    def test_schedule_empty(self, mock_get_conn):
        """Schedule with no events returns empty list."""
        tz_conn = MagicMock()
        tz_result = AsyncMock()
        tz_result.fetchone = AsyncMock(return_value={"timezone": "America/New_York"})
        tz_conn.execute = AsyncMock(return_value=tz_result)

        sched_conn = MagicMock()
        sched_result = AsyncMock()
        sched_result.fetchall = AsyncMock(return_value=[])
        sched_conn.execute = AsyncMock(return_value=sched_result)

        mock_get_conn.side_effect = [
            _make_async_cm(tz_conn),
            _make_async_cm(sched_conn),
        ]

        client = TestClient(app)
        resp = client.get("/api/v1/mobile/schedule/today")

        assert resp.status_code == 200
        body = resp.json()
        assert body["events"] == []
