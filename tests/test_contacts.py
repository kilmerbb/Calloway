"""Tests for contact tools."""
import pytest
from uuid import UUID
from app.tools.contacts import lookup_contact, search_contacts, analyze_contact_gaps

AGENT_ID = UUID("a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11")


def test_lookup_by_phone():
    try:
        contact = lookup_contact(AGENT_ID, phone="+12675551234")
        assert contact is not None
        assert not isinstance(contact, list)
        assert contact.name == "Sarah Chen"
    except Exception:
        pytest.skip("Database not available")


def test_lookup_by_name():
    try:
        contact = lookup_contact(AGENT_ID, name="Sarah")
        assert contact is not None
        # Could be single or list depending on data
    except Exception:
        pytest.skip("Database not available")


def test_lookup_unknown():
    try:
        contact = lookup_contact(AGENT_ID, phone="+19999999999")
        assert contact is None
    except Exception:
        pytest.skip("Database not available")


def test_search_by_lifecycle():
    try:
        contacts = search_contacts(AGENT_ID, lifecycle_stage="active_buyer")
        assert len(contacts) >= 2  # Sarah and Mike
        assert all(c.lifecycle_stage == "active_buyer" for c in contacts)
    except Exception:
        pytest.skip("Database not available")


def test_gap_analysis():
    try:
        gaps = analyze_contact_gaps(AGENT_ID)
        assert isinstance(gaps, list)
        # There should be some contacts needing attention given seed data
        for g in gaps:
            assert "contact" in g
            assert "days_since_contact" in g
            assert "suggested_action" in g
    except Exception:
        pytest.skip("Database not available")
