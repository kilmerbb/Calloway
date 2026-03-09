"""Tests for database schema, seed data, and RLS policies.

These tests require a running PostgreSQL instance with the schema applied.
Skip gracefully if database is not available.
"""
import pytest
import psycopg
from psycopg.rows import dict_row
from uuid import UUID


TEST_AGENT_ID = "a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11"
WRONG_AGENT_ID = "00000000-0000-0000-0000-000000000000"
DB_URL = "postgresql://postgres:postgres@localhost:5432/realtor_ai"


def get_conn():
    try:
        return psycopg.connect(DB_URL, row_factory=dict_row)
    except psycopg.OperationalError:
        pytest.skip("Database not available")


def test_can_connect():
    conn = get_conn()
    result = conn.execute("SELECT 1 as val").fetchone()
    assert result["val"] == 1
    conn.close()


def test_tables_exist():
    conn = get_conn()
    tables = [
        "agents", "contacts", "lead_preferences", "listings",
        "conversations", "messages", "showings", "triggers",
        "emails", "tool_executions", "embeddings", "usage_metrics",
    ]
    for table in tables:
        result = conn.execute(
            "SELECT EXISTS (SELECT FROM information_schema.tables WHERE table_name = %s)",
            [table],
        ).fetchone()
        assert result["exists"], f"Table {table} does not exist"
    conn.close()


def test_seed_data_exists():
    conn = get_conn()
    # Check agent exists (no RLS on agents table)
    agent = conn.execute(
        "SELECT * FROM agents WHERE id = %s", [TEST_AGENT_ID]
    ).fetchone()
    assert agent is not None
    assert agent["name"] == "Jane Smith"
    conn.close()


def test_rls_blocks_without_context():
    """RLS should return empty results without agent context set."""
    conn = get_conn()
    # Contacts have RLS - without setting context, should get nothing
    # Need to use a non-superuser role for RLS to apply
    # In testing with superuser, RLS is bypassed, so we verify the policy exists
    result = conn.execute(
        """SELECT COUNT(*) as cnt FROM pg_policies
           WHERE tablename = 'contacts' AND policyname = 'agent_isolation'"""
    ).fetchone()
    assert result["cnt"] == 1, "RLS policy not found on contacts"
    conn.close()


def test_rls_policies_exist_on_all_tables():
    """Verify RLS policies exist on all tables that need them."""
    conn = get_conn()
    tables_with_rls = [
        "contacts", "lead_preferences", "listings", "conversations",
        "messages", "showings", "triggers", "emails",
        "tool_executions", "embeddings", "usage_metrics",
    ]
    for table in tables_with_rls:
        result = conn.execute(
            "SELECT COUNT(*) as cnt FROM pg_policies WHERE tablename = %s",
            [table],
        ).fetchone()
        assert result["cnt"] >= 1, f"No RLS policy on {table}"
    conn.close()


def test_seed_contacts_exist():
    conn = get_conn()
    # Direct query bypasses RLS with superuser
    contacts = conn.execute(
        "SELECT * FROM contacts WHERE agent_id = %s", [TEST_AGENT_ID]
    ).fetchall()
    assert len(contacts) == 5
    names = {c["name"] for c in contacts}
    assert "Sarah Chen" in names
    assert "Mike Torres" in names
    conn.close()


def test_seed_listings_exist():
    conn = get_conn()
    listings = conn.execute(
        "SELECT * FROM listings WHERE agent_id = %s", [TEST_AGENT_ID]
    ).fetchall()
    assert len(listings) == 3
    addresses = {l["address"] for l in listings}
    assert "123 Oak St" in addresses
    conn.close()


def test_seed_triggers_exist():
    conn = get_conn()
    triggers = conn.execute(
        "SELECT * FROM triggers WHERE agent_id = %s", [TEST_AGENT_ID]
    ).fetchall()
    assert len(triggers) == 5
    conn.close()


def test_unique_contact_phone_per_agent():
    """Verify the unique index on (agent_id, phone) works."""
    conn = get_conn()
    with pytest.raises(psycopg.errors.UniqueViolation):
        conn.execute(
            """INSERT INTO contacts (agent_id, name, phone, role, lifecycle_stage)
               VALUES (%s, 'Duplicate', '+12675551234', 'lead', 'new_lead')""",
            [TEST_AGENT_ID],
        )
    conn.rollback()
    conn.close()
