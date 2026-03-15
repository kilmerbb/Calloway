"""Tests for mobile API conversation endpoints (app/api/mobile/conversations.py)."""

import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from app.api.mobile.deps import get_current_agent
from app.main import app

AGENT_ID = "12345678-1234-1234-1234-123456789012"
CONV_ID = str(uuid.uuid4())
TRIGGER_ID = str(uuid.uuid4())
MSG_ID = str(uuid.uuid4())


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _override_get_current_agent():
    return AGENT_ID


@pytest.fixture(autouse=True)
def override_auth():
    """Override the auth dependency for all tests and clean up after."""
    app.dependency_overrides[get_current_agent] = _override_get_current_agent
    yield
    app.dependency_overrides.pop(get_current_agent, None)


def _make_mock_conn(execute_results=None):
    """Build a mock async DB connection that returns preconfigured results.

    *execute_results* is a list of (fetchone_value, fetchall_value) tuples,
    consumed in order for each ``conn.execute()`` call.  If a value is ``None``
    the corresponding fetch method still returns ``None``.

    The mock also supports ``conn.commit()`` as a no-op coroutine.
    """
    conn = AsyncMock()
    results_iter = iter(execute_results or [])

    async def _execute(*args, **kwargs):
        try:
            fetchone_val, fetchall_val = next(results_iter)
        except StopIteration:
            fetchone_val, fetchall_val = None, []
        cursor = AsyncMock()
        cursor.fetchone = AsyncMock(return_value=fetchone_val)
        cursor.fetchall = AsyncMock(return_value=fetchall_val)
        return cursor

    conn.execute = AsyncMock(side_effect=_execute)
    conn.commit = AsyncMock()
    return conn


def _patch_conn(mock_get_conn, conn):
    """Configure *mock_get_conn* to yield *conn* from a fresh async context
    manager on every call.  This is necessary because endpoints may call
    ``get_async_db_connection()`` multiple times (each ``async with`` is a
    separate invocation).
    """

    @asynccontextmanager
    async def _ctx():
        yield conn

    mock_get_conn.side_effect = lambda: _ctx()


@pytest.fixture()
def client():
    return TestClient(app, raise_server_exceptions=False)


# ===================================================================
# GET /api/v1/mobile/conversations — list_conversations
# ===================================================================

class TestListConversations:
    """MOB-CONV-001"""

    def _conversation_row(self, **overrides):
        row = {
            "id": CONV_ID,
            "contact_id": str(uuid.uuid4()),
            "channel": "sms",
            "stage": "open",
            "last_message_at": datetime.now(timezone.utc),
            "contact_name": "Jane Doe",
            "contact_phone": "+15551234567",
            "last_message_body": "Hi there",
            "unread_count": 2,
            "has_pending_draft": False,
        }
        row.update(overrides)
        return row

    @patch("app.api.mobile.conversations.get_async_db_connection")
    def test_returns_paginated_list(self, mock_get_conn, client):
        row = self._conversation_row()
        conn = _make_mock_conn([
            (None, [row]),          # data query
            ({"total": 1}, None),   # count query
        ])
        _patch_conn(mock_get_conn, conn)

        resp = client.get("/api/v1/mobile/conversations")
        assert resp.status_code == 200
        body = resp.json()
        assert len(body["data"]) == 1
        assert body["data"][0]["id"] == CONV_ID
        assert body["pagination"]["total"] == 1
        assert body["pagination"]["page"] == 1

    @patch("app.api.mobile.conversations.get_async_db_connection")
    def test_filters_by_stage(self, mock_get_conn, client):
        row = self._conversation_row(stage="closed")
        conn = _make_mock_conn([
            (None, [row]),
            ({"total": 1}, None),
        ])
        _patch_conn(mock_get_conn, conn)

        resp = client.get("/api/v1/mobile/conversations?stage=closed")
        assert resp.status_code == 200
        body = resp.json()
        assert body["data"][0]["stage"] == "closed"

    def test_invalid_stage_returns_422(self, client):
        resp = client.get("/api/v1/mobile/conversations?stage=bogus")
        assert resp.status_code == 422

    def test_unauthenticated_returns_401(self):
        """Without the dependency override, the real dep should reject."""
        app.dependency_overrides.pop(get_current_agent, None)
        c = TestClient(app, raise_server_exceptions=False)
        resp = c.get("/api/v1/mobile/conversations")
        assert resp.status_code == 401


# ===================================================================
# GET /api/v1/mobile/conversations/{id}/messages — list_messages
# ===================================================================

class TestListMessages:
    """MOB-CONV-002"""

    def _message_row(self, **overrides):
        row = {
            "id": MSG_ID,
            "sender_type": "client",
            "body": "Hello",
            "ai_generated": False,
            "delivery_status": "delivered",
            "failure_reason": None,
            "created_at": datetime.now(timezone.utc),
        }
        row.update(overrides)
        return row

    @patch("app.api.mobile.conversations.get_async_db_connection")
    def test_returns_paginated_messages(self, mock_get_conn, client):
        msg = self._message_row()
        conn = _make_mock_conn([
            ({"id": CONV_ID}, None),   # ownership check
            (None, [msg]),             # data query
            ({"total": 1}, None),      # count query
            (None, None),              # mark-as-read UPDATE
        ])
        _patch_conn(mock_get_conn, conn)

        resp = client.get(f"/api/v1/mobile/conversations/{CONV_ID}/messages")
        assert resp.status_code == 200
        body = resp.json()
        assert len(body["data"]) == 1
        assert body["data"][0]["id"] == MSG_ID

    @patch("app.api.mobile.conversations.get_async_db_connection")
    def test_marks_conversation_as_read(self, mock_get_conn, client):
        msg = self._message_row()
        conn = _make_mock_conn([
            ({"id": CONV_ID}, None),
            (None, [msg]),
            ({"total": 1}, None),
            (None, None),
        ])
        _patch_conn(mock_get_conn, conn)

        client.get(f"/api/v1/mobile/conversations/{CONV_ID}/messages")

        # The last execute call should be the UPDATE for last_read_at
        update_call = conn.execute.call_args_list[-1]
        assert "UPDATE conversations SET last_read_at" in update_call[0][0]
        conn.commit.assert_called()

    @patch("app.api.mobile.conversations.get_async_db_connection")
    def test_404_for_nonexistent_conversation(self, mock_get_conn, client):
        conn = _make_mock_conn([
            (None, None),  # ownership check returns nothing
        ])
        _patch_conn(mock_get_conn, conn)

        fake_id = str(uuid.uuid4())
        resp = client.get(f"/api/v1/mobile/conversations/{fake_id}/messages")
        assert resp.status_code == 404

    @patch("app.api.mobile.conversations.get_async_db_connection")
    def test_cursor_pagination_with_before(self, mock_get_conn, client):
        msg = self._message_row()
        cursor_msg_id = str(uuid.uuid4())
        conn = _make_mock_conn([
            ({"id": CONV_ID}, None),   # ownership check
            (None, [msg]),             # data (cursor query)
            ({"total": 5}, None),      # count query
            (None, None),              # mark-as-read
        ])
        _patch_conn(mock_get_conn, conn)

        resp = client.get(
            f"/api/v1/mobile/conversations/{CONV_ID}/messages?before={cursor_msg_id}"
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["pagination"]["total"] == 5

        # Verify the cursor-based query was used (second execute call)
        data_call = conn.execute.call_args_list[1]
        assert "created_at <" in data_call[0][0]


# ===================================================================
# POST /api/v1/mobile/conversations/triggers/{id}/approve
# ===================================================================

class TestApproveTrigger:
    """MOB-CONV-003"""

    def _pending_trigger(self, **overrides):
        trigger = {
            "id": TRIGGER_ID,
            "agent_id": AGENT_ID,
            "status": "pending",
            "autonomy_level": "ask_agent",
            "scheduled_at": datetime.now(timezone.utc) - timedelta(hours=1),
            "message_template": "Hello, following up on your inquiry.",
        }
        trigger.update(overrides)
        return trigger

    @patch("app.api.mobile.conversations.get_async_db_connection")
    def test_approves_pending_trigger(self, mock_get_conn, client):
        trigger = self._pending_trigger()
        conn = _make_mock_conn([
            (trigger, None),   # _get_trigger_for_agent SELECT
            (None, None),      # UPDATE status
        ])
        _patch_conn(mock_get_conn, conn)

        resp = client.post(
            f"/api/v1/mobile/conversations/triggers/{TRIGGER_ID}/approve"
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "approved"
        assert body["trigger_id"] == TRIGGER_ID

    @patch("app.api.mobile.conversations.get_async_db_connection")
    def test_404_for_nonexistent_trigger(self, mock_get_conn, client):
        conn = _make_mock_conn([
            (None, None),  # trigger not found
        ])
        _patch_conn(mock_get_conn, conn)

        fake_id = str(uuid.uuid4())
        resp = client.post(
            f"/api/v1/mobile/conversations/triggers/{fake_id}/approve"
        )
        assert resp.status_code == 404

    @patch("app.api.mobile.conversations.get_async_db_connection")
    def test_409_for_already_processed_trigger(self, mock_get_conn, client):
        trigger = self._pending_trigger(status="approved")
        conn = _make_mock_conn([
            (trigger, None),
        ])
        _patch_conn(mock_get_conn, conn)

        resp = client.post(
            f"/api/v1/mobile/conversations/triggers/{TRIGGER_ID}/approve"
        )
        assert resp.status_code == 409

    @patch("app.api.mobile.conversations.get_async_db_connection")
    def test_410_for_expired_trigger(self, mock_get_conn, client):
        trigger = self._pending_trigger(
            scheduled_at=datetime.now(timezone.utc) - timedelta(hours=25)
        )
        conn = _make_mock_conn([
            (trigger, None),
        ])
        _patch_conn(mock_get_conn, conn)

        resp = client.post(
            f"/api/v1/mobile/conversations/triggers/{TRIGGER_ID}/approve"
        )
        assert resp.status_code == 410


# ===================================================================
# PUT /api/v1/mobile/conversations/triggers/{id}/edit
# ===================================================================

class TestEditTrigger:
    """MOB-CONV-004"""

    def _pending_trigger(self, **overrides):
        trigger = {
            "id": TRIGGER_ID,
            "agent_id": AGENT_ID,
            "status": "pending",
            "autonomy_level": "ask_agent",
            "scheduled_at": datetime.now(timezone.utc) - timedelta(hours=1),
            "message_template": "Original message",
        }
        trigger.update(overrides)
        return trigger

    @patch("app.api.mobile.conversations.get_async_db_connection")
    def test_edits_trigger_body(self, mock_get_conn, client):
        trigger = self._pending_trigger()
        conn = _make_mock_conn([
            (trigger, None),   # _get_trigger_for_agent SELECT
            (None, None),      # UPDATE message_template
        ])
        _patch_conn(mock_get_conn, conn)

        resp = client.put(
            f"/api/v1/mobile/conversations/triggers/{TRIGGER_ID}/edit",
            json={"body": "Updated message body"},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "updated"
        assert body["body"] == "Updated message body"

    @patch("app.api.mobile.conversations.get_async_db_connection")
    def test_empty_body_returns_422(self, mock_get_conn, client):
        # Pydantic validation fires before the endpoint logic
        resp = client.put(
            f"/api/v1/mobile/conversations/triggers/{TRIGGER_ID}/edit",
            json={"body": "   "},
        )
        assert resp.status_code == 422

    @patch("app.api.mobile.conversations.get_async_db_connection")
    def test_body_too_long_returns_422(self, mock_get_conn, client):
        resp = client.put(
            f"/api/v1/mobile/conversations/triggers/{TRIGGER_ID}/edit",
            json={"body": "x" * 1601},
        )
        assert resp.status_code == 422


# ===================================================================
# POST /api/v1/mobile/conversations/triggers/{id}/reject
# ===================================================================

class TestRejectTrigger:
    """MOB-CONV-005"""

    def _pending_trigger(self, **overrides):
        trigger = {
            "id": TRIGGER_ID,
            "agent_id": AGENT_ID,
            "status": "pending",
            "autonomy_level": "ask_agent",
            "scheduled_at": datetime.now(timezone.utc) - timedelta(hours=1),
            "message_template": "Some message",
        }
        trigger.update(overrides)
        return trigger

    @patch("app.api.mobile.conversations.get_async_db_connection")
    def test_rejects_trigger(self, mock_get_conn, client):
        trigger = self._pending_trigger()
        conn = _make_mock_conn([
            (trigger, None),   # _get_trigger_for_agent SELECT
            (None, None),      # UPDATE status to cancelled
        ])
        _patch_conn(mock_get_conn, conn)

        resp = client.post(
            f"/api/v1/mobile/conversations/triggers/{TRIGGER_ID}/reject"
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "rejected"
        assert body["trigger_id"] == TRIGGER_ID

        # Verify the UPDATE set status to 'cancelled'
        update_call = conn.execute.call_args_list[-1]
        assert "cancelled" in str(update_call)
