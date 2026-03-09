"""Steps 37-42: Tests for seller features — inquiry routing, occupied showing,
activity tracking, DOM alerts, open house cascade."""
import pytest
from datetime import datetime, timezone, timedelta, date
from uuid import UUID, uuid4
from decimal import Decimal
from unittest.mock import patch, MagicMock

from app.models.schemas import Listing, Contact, AgentConfig

AGENT_ID = UUID("a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11")
LISTING_ID = UUID("c1eebc99-9c0b-4ef8-bb6d-6bb9bd380a11")
CONTACT_ID = UUID("b1eebc99-9c0b-4ef8-bb6d-6bb9bd380a11")

MOCK_AGENT = AgentConfig(
    id=AGENT_ID, name="Jane Smith", email="j@e.com", phone="+1",
    twilio_number="+2", style_profile={"tone": "professional"},
    autonomy_rules={"level": "moderate"}, listing_rules={},
)

MOCK_LISTING = Listing(
    id=LISTING_ID, agent_id=AGENT_ID, address="123 Oak St",
    price=475000, beds=3, baths=Decimal("2"), sqft=1800,
    features=["renovated kitchen"], status="active",
    list_date=date(2026, 2, 1),
    access_rules={"type": "vacant", "approval_required": False},
    lockbox="1234",
)

MOCK_OCCUPIED = Listing(
    id=uuid4(), agent_id=AGENT_ID, address="456 Elm St",
    price=350000, beds=4, baths=Decimal("2.5"),
    features=[], status="active", list_date=date(2026, 2, 15),
    access_rules={"type": "occupied", "seller_contact_id": str(CONTACT_ID)},
)

MOCK_CONTACT = Contact(
    id=CONTACT_ID, agent_id=AGENT_ID, name="Sarah Chen",
    phone="+12675551234", role="buyer", lifecycle_stage="active_buyer",
)


# ============================================================
# Step 37: Listing Inquiry Routing
# ============================================================

def test_route_vacant_listing_inquiry():
    from app.tools.seller_tools import route_listing_inquiry

    result = route_listing_inquiry(MOCK_AGENT, MOCK_LISTING, MOCK_CONTACT, "Can I see 123 Oak?")
    assert result["is_occupied"] is False
    assert result["needs_seller_approval"] is False
    assert result["can_auto_respond"] is True


def test_route_occupied_listing_inquiry():
    from app.tools.seller_tools import route_listing_inquiry

    result = route_listing_inquiry(MOCK_AGENT, MOCK_OCCUPIED, MOCK_CONTACT, "Can I see 456 Elm?")
    assert result["is_occupied"] is True
    assert result["needs_seller_approval"] is True
    assert result["can_auto_respond"] is False
    assert result["seller_contact"] == str(CONTACT_ID)


def test_route_agent_inquiry_gets_lockbox():
    from app.tools.seller_tools import route_listing_inquiry

    agent_contact = Contact(
        id=uuid4(), agent_id=AGENT_ID, name="Other Agent",
        phone="+999", role="other_agent", lifecycle_stage="other_agent",
    )
    result = route_listing_inquiry(MOCK_AGENT, MOCK_LISTING, agent_contact, "Lockbox for 123 Oak?")
    assert result["lockbox_code"] == "1234"


def test_route_buyer_no_lockbox():
    from app.tools.seller_tools import route_listing_inquiry

    result = route_listing_inquiry(MOCK_AGENT, MOCK_LISTING, MOCK_CONTACT, "Can I see it?")
    assert result["lockbox_code"] is None


# ============================================================
# Step 38: Occupied Home Showing
# ============================================================

@patch("app.tools.seller_tools.get_seller_for_listing")
@patch("app.tools.showings.get_db_connection")
def test_request_occupied_showing(mock_show_conn, mock_seller):
    from app.tools.seller_tools import request_occupied_showing

    seller = Contact(
        id=uuid4(), agent_id=AGENT_ID, name="Mr. Homeowner",
        phone="+111", role="seller", lifecycle_stage="active_seller",
    )
    mock_seller.return_value = seller

    # Mock showings DB for create_showing_hold
    show_id = uuid4()
    now = datetime.now(timezone.utc)
    show_row = {
        "id": show_id, "agent_id": AGENT_ID, "contact_id": CONTACT_ID,
        "listing_id": MOCK_OCCUPIED.id, "start_time": datetime(2026, 3, 10, 11, 0, tzinfo=timezone.utc),
        "end_time": datetime(2026, 3, 10, 12, 0, tzinfo=timezone.utc),
        "status": "hold", "hold_expires_at": now + timedelta(minutes=30),
        "calendar_event_id": None, "requesting_agent_id": None,
        "feedback": None, "created_at": now,
    }
    ctx = MagicMock()
    ctx.execute.return_value.fetchone.return_value = show_row
    mock_show_conn.return_value.__enter__ = MagicMock(return_value=ctx)
    mock_show_conn.return_value.__exit__ = MagicMock(return_value=False)

    result = request_occupied_showing(
        MOCK_AGENT, MOCK_OCCUPIED, MOCK_CONTACT,
        datetime(2026, 3, 10, 11, 0, tzinfo=timezone.utc),
    )

    assert result["needs_seller_approval"] is True
    assert result["seller_name"] == "Mr. Homeowner"
    assert result["notification"]["tier"] == "action_needed"
    assert "Mr. Homeowner" in result["notification"]["body"]


@patch("app.tools.seller_tools.get_db_connection")
def test_get_seller_for_listing(mock_conn):
    from app.tools.seller_tools import get_seller_for_listing

    seller_row = {
        "id": uuid4(), "agent_id": AGENT_ID, "name": "Seller Smith",
        "phone": "+111", "email": None, "role": "seller",
        "lifecycle_stage": "active_seller", "linked_listing_id": LISTING_ID,
        "preferences": {}, "notes": None, "last_contact_at": None,
        "silent_mode": False, "created_at": None, "updated_at": None,
    }
    ctx = MagicMock()
    ctx.execute.return_value.fetchone.return_value = seller_row
    mock_conn.return_value.__enter__ = MagicMock(return_value=ctx)
    mock_conn.return_value.__exit__ = MagicMock(return_value=False)

    result = get_seller_for_listing(AGENT_ID, LISTING_ID)
    assert result is not None
    assert result.name == "Seller Smith"


# ============================================================
# Step 39: Listing Activity Tracker
# ============================================================

@patch("app.tools.seller_tools.get_db_connection")
def test_get_listing_activity(mock_conn):
    from app.tools.seller_tools import get_listing_activity

    now = datetime.now(timezone.utc)
    ctx = MagicMock()
    showings = [
        {"contact_name": "Sarah", "start_time": now, "status": "confirmed",
         "feedback": "Loved the kitchen", "created_at": now},
        {"contact_name": "Mike", "start_time": now, "status": "cancelled",
         "feedback": None, "created_at": now},
    ]
    ctx.execute.return_value.fetchall.return_value = showings
    ctx.execute.return_value.fetchone.side_effect = [
        {"address": "123 Oak St"},  # listing address
        {"cnt": 5},  # inquiry count
    ]
    mock_conn.return_value.__enter__ = MagicMock(return_value=ctx)
    mock_conn.return_value.__exit__ = MagicMock(return_value=False)

    result = get_listing_activity(AGENT_ID, LISTING_ID)
    assert result["showings_total"] == 2
    assert result["showings_confirmed"] == 1
    assert result["showings_cancelled"] == 1
    assert result["inquiries"] == 5
    assert len(result["feedback"]) == 1
    assert result["feedback"][0]["feedback"] == "Loved the kitchen"


# ============================================================
# Step 40: DOM Alerter
# ============================================================

def test_dom_alert_30_days():
    from app.tools.seller_tools import check_dom_status

    listing = Listing(
        id=uuid4(), agent_id=AGENT_ID, address="123 Oak",
        price=475000, status="active",
        list_date=datetime.now(timezone.utc).date() - timedelta(days=30),
    )
    alert = check_dom_status(listing)
    assert alert is not None
    assert alert["dom"] == 30
    assert "pricing strategy" in alert["recommendation"].lower()


def test_dom_alert_60_days():
    from app.tools.seller_tools import check_dom_status

    listing = Listing(
        id=uuid4(), agent_id=AGENT_ID, address="789 Elm",
        price=350000, status="active",
        list_date=datetime.now(timezone.utc).date() - timedelta(days=60),
    )
    alert = check_dom_status(listing)
    assert alert is not None
    assert alert["threshold_hit"] == 60


def test_dom_no_alert_new_listing():
    from app.tools.seller_tools import check_dom_status

    listing = Listing(
        id=uuid4(), agent_id=AGENT_ID, address="New Place",
        price=300000, status="active",
        list_date=datetime.now(timezone.utc).date() - timedelta(days=5),
    )
    alert = check_dom_status(listing)
    assert alert is None


def test_dom_no_alert_no_list_date():
    from app.tools.seller_tools import check_dom_status

    listing = Listing(
        id=uuid4(), agent_id=AGENT_ID, address="No Date",
        price=300000, status="active", list_date=None,
    )
    alert = check_dom_status(listing)
    assert alert is None


def test_format_dom_alert():
    from app.tools.seller_tools import format_dom_alert

    alert = {
        "address": "123 Oak St", "dom": 45, "price": 475000,
        "recommendation": "Strong recommendation for price adjustment.",
    }
    text = format_dom_alert(alert)
    assert "123 Oak St" in text
    assert "45 days" in text
    assert "$475,000" in text


# ============================================================
# Step 41: Open House
# ============================================================

@patch("app.tools.contacts.get_db_connection")
@patch("app.tools.triggers.get_db_connection")
@patch("app.tools.seller_tools.get_db_connection")
def test_schedule_open_house(mock_conn, mock_trig_conn, mock_contacts_conn):
    from app.tools.seller_tools import schedule_open_house
    from app.models.schemas import Trigger

    # Mock seller_tools DB (open_house_dates query + update)
    ctx = MagicMock()
    ctx.execute.return_value.fetchone.return_value = {"open_house_dates": []}
    mock_conn.return_value.__enter__ = MagicMock(return_value=ctx)
    mock_conn.return_value.__exit__ = MagicMock(return_value=False)

    # Mock trigger creation DB
    now = datetime.now(timezone.utc)
    trig_row = {
        "id": uuid4(), "agent_id": AGENT_ID, "entity_type": "listing",
        "entity_id": LISTING_ID, "trigger_type": "open_house",
        "scheduled_at": now, "action_type": "send_message",
        "recurrence": None, "message_template": "test",
        "autonomy_level": "auto", "status": "pending",
        "notes": None, "created_at": now,
    }
    trig_ctx = MagicMock()
    trig_ctx.execute.return_value.fetchone.side_effect = [
        None, trig_row, None, trig_row, None, trig_row, None, trig_row, None, trig_row,
    ]
    mock_trig_conn.return_value.__enter__ = MagicMock(return_value=trig_ctx)
    mock_trig_conn.return_value.__exit__ = MagicMock(return_value=False)

    # Mock contacts DB (search_contacts)
    contacts_ctx = MagicMock()
    contacts_ctx.execute.return_value.fetchall.return_value = [{
        "id": CONTACT_ID, "agent_id": AGENT_ID, "name": "Sarah Chen",
        "phone": "+12675551234", "email": None, "role": "buyer",
        "lifecycle_stage": "active_buyer", "linked_listing_id": None,
        "preferences": {}, "notes": None, "last_contact_at": None,
        "silent_mode": False, "created_at": None, "updated_at": None,
    }]
    mock_contacts_conn.return_value.__enter__ = MagicMock(return_value=contacts_ctx)
    mock_contacts_conn.return_value.__exit__ = MagicMock(return_value=False)

    oh_date = datetime(2026, 3, 15, 13, 0, tzinfo=timezone.utc)
    result = schedule_open_house(MOCK_AGENT, MOCK_LISTING, oh_date)

    assert result["triggers_created"] == 5
    assert result["matching_buyers"] == 1
    assert result["address"] == "123 Oak St"


@patch("app.tools.seller_tools.get_db_connection")
def test_get_open_house_attendees(mock_conn):
    from app.tools.seller_tools import get_open_house_attendees

    ctx = MagicMock()
    ctx.execute.return_value.fetchall.return_value = [
        {"name": "Sarah", "phone": "+123", "email": "s@e.com",
         "start_time": datetime(2026, 3, 15, 13, 0)},
        {"name": "Mike", "phone": "+456", "email": None,
         "start_time": datetime(2026, 3, 15, 13, 30)},
    ]
    mock_conn.return_value.__enter__ = MagicMock(return_value=ctx)
    mock_conn.return_value.__exit__ = MagicMock(return_value=False)

    attendees = get_open_house_attendees(AGENT_ID, LISTING_ID)
    assert len(attendees) == 2
    assert attendees[0]["name"] == "Sarah"
    assert attendees[1]["email"] is None


# ============================================================
# E2E: Full seller workflow
# ============================================================

def test_e2e_dom_check_and_format():
    """Test: check DOM → format alert for a listing."""
    from app.tools.seller_tools import check_dom_status, format_dom_alert

    # Check DOM (listing is from Feb 1 = ~36 days)
    alert = check_dom_status(MOCK_LISTING)
    assert alert is not None
    assert alert["dom"] >= 30

    # Format alert
    text = format_dom_alert(alert)
    assert "123 Oak St" in text
    assert "$475,000" in text
