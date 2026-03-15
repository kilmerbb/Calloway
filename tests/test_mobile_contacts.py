"""Tests for mobile contacts API endpoints."""

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


def _make_contact_row(
    contact_id="c001",
    name="Jane Doe",
    phone="+15551234567",
    email="jane@example.com",
    role="buyer",
    lifecycle_stage="active",
    lead_source="zillow",
    last_contact_at=None,
    created_at=None,
):
    return {
        "id": contact_id,
        "name": name,
        "phone": phone,
        "email": email,
        "role": role,
        "lifecycle_stage": lifecycle_stage,
        "lead_source": lead_source,
        "last_contact_at": last_contact_at or datetime(2026, 3, 10, 12, 0, tzinfo=timezone.utc),
        "created_at": created_at or datetime(2026, 1, 1, 0, 0, tzinfo=timezone.utc),
    }


# -----------------------------------------------------------------------
# GET /api/v1/mobile/contacts — list contacts
# -----------------------------------------------------------------------


class TestListContacts:
    """Tests for the list_contacts endpoint."""

    @patch("app.api.mobile.contacts.get_async_db_connection")
    def test_list_contacts_basic(self, mock_get_conn):
        """Returns contacts with pagination metadata."""
        row = _make_contact_row()
        mock_conn = MagicMock()
        # First execute: count query
        count_result = AsyncMock()
        count_result.fetchone = AsyncMock(return_value={"total": 1})
        # Second execute: data query
        data_result = AsyncMock()
        data_result.fetchall = AsyncMock(return_value=[row])
        mock_conn.execute = AsyncMock(side_effect=[count_result, data_result])
        mock_get_conn.return_value = _make_async_cm(mock_conn)

        client = TestClient(app)
        resp = client.get("/api/v1/mobile/contacts")

        assert resp.status_code == 200
        body = resp.json()
        assert len(body["data"]) == 1
        assert body["data"][0]["name"] == "Jane Doe"
        assert body["pagination"]["total"] == 1
        assert body["pagination"]["page"] == 1
        assert body["pagination"]["per_page"] == 25

    @patch("app.api.mobile.contacts.get_async_db_connection")
    def test_list_contacts_pagination(self, mock_get_conn):
        """Respects page and per_page query params."""
        mock_conn = MagicMock()
        count_result = AsyncMock()
        count_result.fetchone = AsyncMock(return_value={"total": 50})
        data_result = AsyncMock()
        data_result.fetchall = AsyncMock(return_value=[_make_contact_row()])
        mock_conn.execute = AsyncMock(side_effect=[count_result, data_result])
        mock_get_conn.return_value = _make_async_cm(mock_conn)

        client = TestClient(app)
        resp = client.get("/api/v1/mobile/contacts?page=2&per_page=10")

        assert resp.status_code == 200
        body = resp.json()
        assert body["pagination"]["page"] == 2
        assert body["pagination"]["per_page"] == 10
        assert body["pagination"]["pages"] == 5  # ceil(50/10)

        # Verify offset passed to data query (second execute call)
        data_call_params = mock_conn.execute.call_args_list[1][0][1]
        assert data_call_params[-1] == 10  # offset = (2-1)*10 = 10
        assert data_call_params[-2] == 10  # per_page

    @patch("app.api.mobile.contacts.get_async_db_connection")
    def test_list_contacts_empty(self, mock_get_conn):
        """Returns empty list when no contacts match."""
        mock_conn = MagicMock()
        count_result = AsyncMock()
        count_result.fetchone = AsyncMock(return_value={"total": 0})
        data_result = AsyncMock()
        data_result.fetchall = AsyncMock(return_value=[])
        mock_conn.execute = AsyncMock(side_effect=[count_result, data_result])
        mock_get_conn.return_value = _make_async_cm(mock_conn)

        client = TestClient(app)
        resp = client.get("/api/v1/mobile/contacts")

        assert resp.status_code == 200
        body = resp.json()
        assert body["data"] == []
        assert body["pagination"]["total"] == 0
        assert body["pagination"]["pages"] == 0

    def test_list_contacts_search_too_short(self):
        """Rejects search terms shorter than 2 characters."""
        client = TestClient(app)
        resp = client.get("/api/v1/mobile/contacts?search=a")

        assert resp.status_code == 422
        assert "at least 2 characters" in resp.json()["detail"]

    @patch("app.api.mobile.contacts.get_async_db_connection")
    def test_list_contacts_search(self, mock_get_conn):
        """Search term is passed as ILIKE parameter."""
        mock_conn = MagicMock()
        count_result = AsyncMock()
        count_result.fetchone = AsyncMock(return_value={"total": 1})
        data_result = AsyncMock()
        data_result.fetchall = AsyncMock(return_value=[_make_contact_row()])
        mock_conn.execute = AsyncMock(side_effect=[count_result, data_result])
        mock_get_conn.return_value = _make_async_cm(mock_conn)

        client = TestClient(app)
        resp = client.get("/api/v1/mobile/contacts?search=jane")

        assert resp.status_code == 200
        # Verify ILIKE pattern in count query params
        count_params = mock_conn.execute.call_args_list[0][0][1]
        # params = [agent_id, like_pattern, like_pattern, like_pattern]
        assert count_params[1] == "%jane%"
        assert count_params[2] == "%jane%"
        assert count_params[3] == "%jane%"

    @patch("app.api.mobile.contacts.get_async_db_connection")
    def test_list_contacts_search_wildcard_escaping(self, mock_get_conn):
        """ILIKE wildcards (%, _) and backslashes are escaped in search."""
        mock_conn = MagicMock()
        count_result = AsyncMock()
        count_result.fetchone = AsyncMock(return_value={"total": 0})
        data_result = AsyncMock()
        data_result.fetchall = AsyncMock(return_value=[])
        mock_conn.execute = AsyncMock(side_effect=[count_result, data_result])
        mock_get_conn.return_value = _make_async_cm(mock_conn)

        client = TestClient(app)
        resp = client.get("/api/v1/mobile/contacts?search=100%_off")

        assert resp.status_code == 200
        count_params = mock_conn.execute.call_args_list[0][0][1]
        # % -> \%, _ -> \_ in the like pattern
        expected_pattern = "%100\\%\\_off%"
        assert count_params[1] == expected_pattern

    @patch("app.api.mobile.contacts.get_async_db_connection")
    def test_list_contacts_search_backslash_escaping(self, mock_get_conn):
        """Backslashes in search are escaped before wildcards."""
        mock_conn = MagicMock()
        count_result = AsyncMock()
        count_result.fetchone = AsyncMock(return_value={"total": 0})
        data_result = AsyncMock()
        data_result.fetchall = AsyncMock(return_value=[])
        mock_conn.execute = AsyncMock(side_effect=[count_result, data_result])
        mock_get_conn.return_value = _make_async_cm(mock_conn)

        client = TestClient(app)
        resp = client.get("/api/v1/mobile/contacts?search=a\\b")

        assert resp.status_code == 200
        count_params = mock_conn.execute.call_args_list[0][0][1]
        expected_pattern = "%a\\\\b%"
        assert count_params[1] == expected_pattern

    @patch("app.api.mobile.contacts.get_async_db_connection")
    def test_list_contacts_filter_role(self, mock_get_conn):
        """Filters contacts by role."""
        mock_conn = MagicMock()
        count_result = AsyncMock()
        count_result.fetchone = AsyncMock(return_value={"total": 1})
        data_result = AsyncMock()
        data_result.fetchall = AsyncMock(return_value=[_make_contact_row(role="seller")])
        mock_conn.execute = AsyncMock(side_effect=[count_result, data_result])
        mock_get_conn.return_value = _make_async_cm(mock_conn)

        client = TestClient(app)
        resp = client.get("/api/v1/mobile/contacts?role=seller")

        assert resp.status_code == 200
        # Verify role param in count query
        count_params = mock_conn.execute.call_args_list[0][0][1]
        assert "seller" in count_params

    @patch("app.api.mobile.contacts.get_async_db_connection")
    def test_list_contacts_filter_lead_source(self, mock_get_conn):
        """Filters contacts by lead_source."""
        mock_conn = MagicMock()
        count_result = AsyncMock()
        count_result.fetchone = AsyncMock(return_value={"total": 1})
        data_result = AsyncMock()
        data_result.fetchall = AsyncMock(return_value=[_make_contact_row(lead_source="referral")])
        mock_conn.execute = AsyncMock(side_effect=[count_result, data_result])
        mock_get_conn.return_value = _make_async_cm(mock_conn)

        client = TestClient(app)
        resp = client.get("/api/v1/mobile/contacts?lead_source=referral")

        assert resp.status_code == 200
        count_params = mock_conn.execute.call_args_list[0][0][1]
        assert "referral" in count_params

    @patch("app.api.mobile.contacts.get_async_db_connection")
    def test_list_contacts_filter_lifecycle_stage(self, mock_get_conn):
        """Filters contacts by lifecycle_stage."""
        mock_conn = MagicMock()
        count_result = AsyncMock()
        count_result.fetchone = AsyncMock(return_value={"total": 1})
        data_result = AsyncMock()
        data_result.fetchall = AsyncMock(return_value=[_make_contact_row(lifecycle_stage="nurture")])
        mock_conn.execute = AsyncMock(side_effect=[count_result, data_result])
        mock_get_conn.return_value = _make_async_cm(mock_conn)

        client = TestClient(app)
        resp = client.get("/api/v1/mobile/contacts?lifecycle_stage=nurture")

        assert resp.status_code == 200
        count_params = mock_conn.execute.call_args_list[0][0][1]
        assert "nurture" in count_params

    @patch("app.api.mobile.contacts.get_async_db_connection")
    def test_list_contacts_multiple_filters(self, mock_get_conn):
        """Combines role, lead_source, and search filters."""
        mock_conn = MagicMock()
        count_result = AsyncMock()
        count_result.fetchone = AsyncMock(return_value={"total": 1})
        data_result = AsyncMock()
        data_result.fetchall = AsyncMock(return_value=[_make_contact_row()])
        mock_conn.execute = AsyncMock(side_effect=[count_result, data_result])
        mock_get_conn.return_value = _make_async_cm(mock_conn)

        client = TestClient(app)
        resp = client.get("/api/v1/mobile/contacts?role=buyer&lead_source=zillow&search=jane")

        assert resp.status_code == 200
        count_params = mock_conn.execute.call_args_list[0][0][1]
        # agent_id, role, lead_source, search x3
        assert len(count_params) == 6
        assert count_params[0] == AGENT_ID
        assert count_params[1] == "buyer"
        assert count_params[2] == "zillow"
        assert count_params[3] == "%jane%"


# -----------------------------------------------------------------------
# GET /api/v1/mobile/contacts/{contact_id} — contact detail
# -----------------------------------------------------------------------


class TestGetContact:
    """Tests for the get_contact endpoint."""

    @patch("app.api.mobile.contacts.get_async_db_connection")
    def test_get_contact_detail(self, mock_get_conn):
        """Returns contact with lead_preferences, conversations, showings."""
        contact_row = {
            "id": "c001",
            "name": "Jane Doe",
            "phone": "+15551234567",
            "email": "jane@example.com",
            "role": "buyer",
            "lifecycle_stage": "active",
            "lead_source": "zillow",
            "notes": "Prefers text",
            "last_contact_at": datetime(2026, 3, 10, 12, 0, tzinfo=timezone.utc),
            "language_detected": "en",
            "interaction_count": 12,
            "created_at": datetime(2026, 1, 1, 0, 0, tzinfo=timezone.utc),
            # lead_preferences fields
            "areas": ["Downtown", "Midtown"],
            "timeline": "3 months",
            "preapproved": True,
            "property_type": "condo",
            "bedrooms_min": 2,
            "bathrooms_min": 1.5,
            "price_min": 200000.0,
            "price_max": 500000.0,
        }
        conversation_rows = [
            {
                "id": "conv001",
                "channel": "sms",
                "stage": "active",
                "last_message_at": datetime(2026, 3, 10, 12, 0, tzinfo=timezone.utc),
                "last_message_preview": "Hey, any updates?",
            }
        ]
        showing_rows = [
            {
                "id": "show001",
                "start_time": datetime(2026, 3, 20, 14, 0, tzinfo=timezone.utc),
                "end_time": datetime(2026, 3, 20, 15, 0, tzinfo=timezone.utc),
                "status": "confirmed",
                "listing_address": "123 Main St",
            }
        ]

        mock_conn = MagicMock()
        contact_result = AsyncMock()
        contact_result.fetchone = AsyncMock(return_value=contact_row)
        conv_result = AsyncMock()
        conv_result.fetchall = AsyncMock(return_value=conversation_rows)
        showing_result = AsyncMock()
        showing_result.fetchall = AsyncMock(return_value=showing_rows)
        mock_conn.execute = AsyncMock(
            side_effect=[contact_result, conv_result, showing_result]
        )
        mock_get_conn.return_value = _make_async_cm(mock_conn)

        client = TestClient(app)
        resp = client.get("/api/v1/mobile/contacts/c001")

        assert resp.status_code == 200
        body = resp.json()
        assert body["contact"]["id"] == "c001"
        assert body["contact"]["name"] == "Jane Doe"
        assert body["contact"]["interaction_count"] == 12

        # Lead preferences
        assert body["lead_preferences"] is not None
        assert body["lead_preferences"]["timeline"] == "3 months"
        assert body["lead_preferences"]["preapproved"] is True
        assert body["lead_preferences"]["price_max"] == 500000.0

        # Conversations
        assert len(body["recent_conversations"]) == 1
        assert body["recent_conversations"][0]["channel"] == "sms"

        # Showings
        assert len(body["upcoming_showings"]) == 1
        assert body["upcoming_showings"][0]["listing_address"] == "123 Main St"

    @patch("app.api.mobile.contacts.get_async_db_connection")
    def test_get_contact_no_preferences(self, mock_get_conn):
        """Returns null lead_preferences when all preference fields are None."""
        contact_row = {
            "id": "c002",
            "name": "Bob Smith",
            "phone": "+15559876543",
            "email": None,
            "role": "seller",
            "lifecycle_stage": "new",
            "lead_source": "walk-in",
            "notes": None,
            "last_contact_at": None,
            "language_detected": None,
            "interaction_count": 0,
            "created_at": datetime(2026, 2, 1, 0, 0, tzinfo=timezone.utc),
            # All preference fields None
            "areas": None,
            "timeline": None,
            "preapproved": None,
            "property_type": None,
            "bedrooms_min": None,
            "bathrooms_min": None,
            "price_min": None,
            "price_max": None,
        }

        mock_conn = MagicMock()
        contact_result = AsyncMock()
        contact_result.fetchone = AsyncMock(return_value=contact_row)
        conv_result = AsyncMock()
        conv_result.fetchall = AsyncMock(return_value=[])
        showing_result = AsyncMock()
        showing_result.fetchall = AsyncMock(return_value=[])
        mock_conn.execute = AsyncMock(
            side_effect=[contact_result, conv_result, showing_result]
        )
        mock_get_conn.return_value = _make_async_cm(mock_conn)

        client = TestClient(app)
        resp = client.get("/api/v1/mobile/contacts/c002")

        assert resp.status_code == 200
        body = resp.json()
        assert body["lead_preferences"] is None
        assert body["recent_conversations"] == []
        assert body["upcoming_showings"] == []

    @patch("app.api.mobile.contacts.get_async_db_connection")
    def test_get_contact_not_found(self, mock_get_conn):
        """Returns 404 when contact does not exist."""
        mock_conn = MagicMock()
        contact_result = AsyncMock()
        contact_result.fetchone = AsyncMock(return_value=None)
        mock_conn.execute = AsyncMock(return_value=contact_result)
        mock_get_conn.return_value = _make_async_cm(mock_conn)

        client = TestClient(app)
        resp = client.get("/api/v1/mobile/contacts/nonexistent-id")

        assert resp.status_code == 404
        assert resp.json()["detail"] == "Contact not found"
