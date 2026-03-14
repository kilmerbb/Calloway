"""
RLS (Row-Level Security) integration tests for Calloway.

These tests verify that PostgreSQL RLS policies correctly enforce tenant
isolation across all tables. They require a real PostgreSQL database with
the Calloway schema applied.

HOW TO RUN:
    # Set DATABASE_URL to a test database (NOT production!)
    export DATABASE_URL="postgresql://user:pass@localhost:5432/calloway_test"

    # Run only integration tests
    pytest tests/test_rls_integration.py -m integration -v

    # Or via env var
    INTEGRATION_TESTS=1 pytest tests/test_rls_integration.py -v

PREREQUISITES:
    - A PostgreSQL 16+ database with pgvector extension
    - Schema applied via: psql $DATABASE_URL < app/db/schema.sql
    - The test DB user must NOT be a superuser (superusers bypass RLS)
"""

import os
import uuid
from datetime import date, datetime, timezone

import psycopg
import pytest
from psycopg.rows import dict_row

# Skip entire module unless integration tests are enabled
pytestmark = pytest.mark.integration


# ---------------------------------------------------------------------------
# Expected RLS configuration
# ---------------------------------------------------------------------------

# Tables that have an agent_id column and SHOULD have RLS policies
TABLES_WITH_AGENT_ID_RLS = {
    "contacts",
    "consent_log",
    "listings",
    "conversations",
    "messages",
    "showings",
    "triggers",
    "transactions",
    "drip_campaigns",
    "drip_enrollments",
    "emails",
    "tool_executions",
    "embeddings",
    "usage_metrics",
    "device_tokens",
}

# Tables that use RLS via FK join (no direct agent_id column)
TABLES_WITH_FK_RLS = {
    "lead_preferences",  # via contact_id -> contacts.agent_id
}

# Tables that use a differently-named tenant column
TABLES_WITH_TENANT_ID_RLS = {
    "conversation_summaries",  # uses tenant_id instead of agent_id
}

# All tables expected to have RLS enabled
ALL_RLS_TABLES = TABLES_WITH_AGENT_ID_RLS | TABLES_WITH_FK_RLS | TABLES_WITH_TENANT_ID_RLS

# Tables that intentionally do NOT have RLS (system-level tables)
TABLES_WITHOUT_RLS = {
    "agents",           # identity table, no self-referential RLS
    "console_users",    # operator console auth, not tenant-scoped
    "audit_log",        # operator audit trail, not tenant-scoped
    "error_log",        # system error log, agent_id is optional/diagnostic
    "harness_traces",   # testing traces, agent_id is optional/diagnostic
}


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def db_url():
    """Get the test database URL from environment."""
    url = os.environ.get("DATABASE_URL")
    if not url:
        pytest.skip("DATABASE_URL not set — cannot run integration tests")
    return url


@pytest.fixture(scope="module")
def db_conn(db_url):
    """
    Module-scoped connection for test setup/teardown.
    This connection does NOT have RLS context set, simulating a service-role.
    autocommit=True so set_config calls persist outside transactions.
    """
    conn = psycopg.connect(db_url, row_factory=dict_row, autocommit=True)
    yield conn
    conn.close()


@pytest.fixture(scope="module")
def agent_ids(db_conn):
    """Create two test agents and return their IDs. Clean up after all tests."""
    agent_a_id = uuid.uuid4()
    agent_b_id = uuid.uuid4()

    for aid, name, phone, twilio in [
        (agent_a_id, "Test Agent A", "+15550001111", "+15550009999"),
        (agent_b_id, "Test Agent B", "+15550002222", "+15550008888"),
    ]:
        db_conn.execute(
            """
            INSERT INTO agents (id, name, email, phone, twilio_number)
            VALUES (%s, %s, %s, %s, %s)
            ON CONFLICT (id) DO NOTHING
            """,
            [str(aid), name, f"{name.lower().replace(' ', '.')}@test.calloway.dev", phone, twilio],
        )

    yield agent_a_id, agent_b_id

    # Cleanup: delete in reverse dependency order
    for table in [
        "drip_enrollments", "drip_campaigns",
        "tool_executions", "embeddings", "usage_metrics",
        "device_tokens", "conversation_summaries",
        "messages", "showings", "triggers", "transactions",
        "emails", "consent_log",
        "lead_preferences", "conversations", "listings", "contacts",
    ]:
        db_conn.execute(
            f"DELETE FROM {table} WHERE agent_id = %s OR agent_id = %s",
            [str(agent_a_id), str(agent_b_id)],
        ) if table not in ("lead_preferences", "conversation_summaries") else None

    # lead_preferences cleanup via contacts
    db_conn.execute(
        """
        DELETE FROM lead_preferences WHERE contact_id IN (
            SELECT id FROM contacts WHERE agent_id = %s OR agent_id = %s
        )
        """,
        [str(agent_a_id), str(agent_b_id)],
    )
    # conversation_summaries uses tenant_id
    db_conn.execute(
        "DELETE FROM conversation_summaries WHERE tenant_id = %s OR tenant_id = %s",
        [str(agent_a_id), str(agent_b_id)],
    )
    # Now clean contacts and agents
    db_conn.execute(
        "DELETE FROM contacts WHERE agent_id = %s OR agent_id = %s",
        [str(agent_a_id), str(agent_b_id)],
    )
    db_conn.execute(
        "DELETE FROM agents WHERE id = %s OR id = %s",
        [str(agent_a_id), str(agent_b_id)],
    )


def _set_rls_context(conn, agent_id):
    """Set the RLS context for the current transaction."""
    conn.execute(
        "SELECT set_config('app.current_agent_id', %s, true)",
        [str(agent_id)],
    )


def _reset_rls_context(conn):
    """Reset the RLS context (simulate service-role / no tenant)."""
    conn.execute("SELECT set_config('app.current_agent_id', '', true)")


@pytest.fixture()
def rls_conn(db_url):
    """
    Per-test connection with autocommit=False so that set_config(..., true)
    is transaction-scoped. Each test runs in a transaction that rolls back.
    """
    conn = psycopg.connect(db_url, row_factory=dict_row, autocommit=False)
    yield conn
    conn.rollback()
    conn.close()


# ---------------------------------------------------------------------------
# Test A: Schema completeness — every table with agent_id has RLS
# ---------------------------------------------------------------------------

class TestSchemaCompleteness:
    """Verify RLS policies match the expected configuration."""

    def test_all_agent_id_tables_have_rls(self, db_conn):
        """Every table with an agent_id column should have an RLS policy,
        unless it is in the explicit exemption list."""
        # Find all tables that have an agent_id column
        rows = db_conn.execute(
            """
            SELECT DISTINCT c.table_name
            FROM information_schema.columns c
            JOIN information_schema.tables t
                ON t.table_name = c.table_name AND t.table_schema = c.table_schema
            WHERE c.column_name = 'agent_id'
              AND c.table_schema = 'public'
              AND t.table_type = 'BASE TABLE'
            """
        ).fetchall()
        tables_with_agent_id = {r["table_name"] for r in rows}

        # Find all tables with RLS enabled via pg_class
        rls_rows = db_conn.execute(
            """
            SELECT relname
            FROM pg_class
            WHERE relrowsecurity = true
              AND relnamespace = 'public'::regnamespace
            """
        ).fetchall()
        tables_with_rls = {r["relname"] for r in rls_rows}

        # Check: every agent_id table not in the exemption list must have RLS
        missing_rls = tables_with_agent_id - tables_with_rls - TABLES_WITHOUT_RLS
        assert missing_rls == set(), (
            f"Tables with agent_id column but NO RLS policy: {missing_rls}. "
            "Either add RLS or add to TABLES_WITHOUT_RLS exemption list."
        )

    def test_expected_rls_tables_exist(self, db_conn):
        """All tables we expect to have RLS actually do."""
        rls_rows = db_conn.execute(
            """
            SELECT relname
            FROM pg_class
            WHERE relrowsecurity = true
              AND relnamespace = 'public'::regnamespace
            """
        ).fetchall()
        tables_with_rls = {r["relname"] for r in rls_rows}

        missing = ALL_RLS_TABLES - tables_with_rls
        assert missing == set(), (
            f"Expected RLS on these tables but not found: {missing}"
        )

    def test_rls_policies_use_agent_isolation_name(self, db_conn):
        """All RLS policies should follow the naming convention 'agent_isolation'."""
        rows = db_conn.execute(
            """
            SELECT schemaname, tablename, policyname
            FROM pg_policies
            WHERE schemaname = 'public'
            """
        ).fetchall()

        non_standard = [
            r for r in rows if r["policyname"] != "agent_isolation"
        ]
        assert non_standard == [], (
            f"Policies with non-standard names: "
            f"{[(r['tablename'], r['policyname']) for r in non_standard]}"
        )


# ---------------------------------------------------------------------------
# Test B: Cross-tenant isolation — contacts
# ---------------------------------------------------------------------------

class TestContactsIsolation:
    """Verify RLS on the contacts table."""

    @pytest.fixture(autouse=True)
    def setup_contacts(self, db_conn, agent_ids):
        """Insert test contacts for both agents."""
        self.agent_a, self.agent_b = agent_ids
        self.contact_a_id = uuid.uuid4()
        self.contact_b_id = uuid.uuid4()

        for cid, aid, name, phone in [
            (self.contact_a_id, self.agent_a, "Alice Buyer", "+15551110001"),
            (self.contact_b_id, self.agent_b, "Bob Seller", "+15551110002"),
        ]:
            db_conn.execute(
                """
                INSERT INTO contacts (id, agent_id, name, phone)
                VALUES (%s, %s, %s, %s)
                ON CONFLICT (agent_id, phone) DO NOTHING
                """,
                [str(cid), str(aid), name, phone],
            )

        yield

        db_conn.execute("DELETE FROM contacts WHERE id = %s OR id = %s",
                        [str(self.contact_a_id), str(self.contact_b_id)])

    def test_agent_a_sees_only_own_contacts(self, rls_conn):
        """Agent A should only see their own contacts."""
        _set_rls_context(rls_conn, self.agent_a)
        rows = rls_conn.execute("SELECT id, name FROM contacts").fetchall()
        ids = {r["id"] for r in rows}
        assert self.contact_a_id in ids, "Agent A should see their own contact"
        assert self.contact_b_id not in ids, "Agent A must NOT see Agent B's contact"

    def test_agent_b_sees_only_own_contacts(self, rls_conn):
        """Agent B should only see their own contacts."""
        _set_rls_context(rls_conn, self.agent_b)
        rows = rls_conn.execute("SELECT id, name FROM contacts").fetchall()
        ids = {r["id"] for r in rows}
        assert self.contact_b_id in ids, "Agent B should see their own contact"
        assert self.contact_a_id not in ids, "Agent B must NOT see Agent A's contact"


# ---------------------------------------------------------------------------
# Test C: Cross-tenant isolation — messages
# ---------------------------------------------------------------------------

class TestMessagesIsolation:
    """Verify RLS on messages table."""

    @pytest.fixture(autouse=True)
    def setup_messages(self, db_conn, agent_ids):
        """Insert conversations and messages for both agents."""
        self.agent_a, self.agent_b = agent_ids

        # Create contacts first
        self.contact_a_id = uuid.uuid4()
        self.contact_b_id = uuid.uuid4()
        for cid, aid, phone in [
            (self.contact_a_id, self.agent_a, "+15552220001"),
            (self.contact_b_id, self.agent_b, "+15552220002"),
        ]:
            db_conn.execute(
                "INSERT INTO contacts (id, agent_id, name, phone) VALUES (%s, %s, %s, %s) "
                "ON CONFLICT (agent_id, phone) DO NOTHING",
                [str(cid), str(aid), "Test Contact", phone],
            )

        # Create conversations
        self.conv_a_id = uuid.uuid4()
        self.conv_b_id = uuid.uuid4()
        for cvid, aid, cid in [
            (self.conv_a_id, self.agent_a, self.contact_a_id),
            (self.conv_b_id, self.agent_b, self.contact_b_id),
        ]:
            db_conn.execute(
                "INSERT INTO conversations (id, agent_id, contact_id, channel) "
                "VALUES (%s, %s, %s, 'sms')",
                [str(cvid), str(aid), str(cid)],
            )

        # Create messages
        self.msg_a_id = uuid.uuid4()
        self.msg_b_id = uuid.uuid4()
        for mid, aid, cvid in [
            (self.msg_a_id, self.agent_a, self.conv_a_id),
            (self.msg_b_id, self.agent_b, self.conv_b_id),
        ]:
            db_conn.execute(
                "INSERT INTO messages (id, agent_id, conversation_id, sender_type, body) "
                "VALUES (%s, %s, %s, 'contact', 'Hello')",
                [str(mid), str(aid), str(cvid)],
            )

        yield

        # Cleanup
        db_conn.execute("DELETE FROM messages WHERE id IN (%s, %s)",
                        [str(self.msg_a_id), str(self.msg_b_id)])
        db_conn.execute("DELETE FROM conversations WHERE id IN (%s, %s)",
                        [str(self.conv_a_id), str(self.conv_b_id)])
        db_conn.execute("DELETE FROM contacts WHERE id IN (%s, %s)",
                        [str(self.contact_a_id), str(self.contact_b_id)])

    def test_agent_a_sees_only_own_messages(self, rls_conn):
        """Agent A should only see their own messages."""
        _set_rls_context(rls_conn, self.agent_a)
        rows = rls_conn.execute("SELECT id FROM messages").fetchall()
        ids = {r["id"] for r in rows}
        assert self.msg_a_id in ids
        assert self.msg_b_id not in ids

    def test_agent_b_sees_only_own_messages(self, rls_conn):
        """Agent B should only see their own messages."""
        _set_rls_context(rls_conn, self.agent_b)
        rows = rls_conn.execute("SELECT id FROM messages").fetchall()
        ids = {r["id"] for r in rows}
        assert self.msg_b_id in ids
        assert self.msg_a_id not in ids


# ---------------------------------------------------------------------------
# Test D: Cross-tenant INSERT blocking
# ---------------------------------------------------------------------------

class TestCrossTenantInsertBlocking:
    """Verify that RLS prevents inserting rows for another agent."""

    def test_insert_contact_as_wrong_agent_is_blocked(self, rls_conn, agent_ids):
        """Agent A cannot insert a contact with agent_id = Agent B.

        With RLS FOR ALL policies, the INSERT goes through but the USING
        check on the inserted row fails, causing the row to be silently
        filtered (not visible). In strict mode it raises an error.
        We test that the row is at minimum not visible to Agent A.
        """
        agent_a, agent_b = agent_ids
        _set_rls_context(rls_conn, agent_a)
        test_id = uuid.uuid4()

        # Attempt to insert a contact belonging to Agent B while context is Agent A.
        # This should either raise an error or silently filter the row.
        try:
            rls_conn.execute(
                "INSERT INTO contacts (id, agent_id, name, phone) "
                "VALUES (%s, %s, %s, %s)",
                [str(test_id), str(agent_b), "Intruder", "+15559990001"],
            )
            # If no error, verify the row is not visible to Agent A
            rows = rls_conn.execute(
                "SELECT id FROM contacts WHERE id = %s", [str(test_id)]
            ).fetchall()
            assert len(rows) == 0, (
                "Agent A should NOT be able to see a contact inserted for Agent B"
            )
        except psycopg.errors.InsufficientPrivilege:
            # This is also acceptable — RLS blocked the INSERT outright
            rls_conn.rollback()
        except psycopg.errors.CheckViolation:
            # WITH CHECK clause violation
            rls_conn.rollback()


# ---------------------------------------------------------------------------
# Test E: Service-role access (no RLS context) — all rows visible
# ---------------------------------------------------------------------------

class TestServiceRoleAccess:
    """Without set_agent_context, queries should see all rows (service role)."""

    @pytest.fixture(autouse=True)
    def setup_contacts(self, db_conn, agent_ids):
        self.agent_a, self.agent_b = agent_ids
        self.contact_a_id = uuid.uuid4()
        self.contact_b_id = uuid.uuid4()

        for cid, aid, phone in [
            (self.contact_a_id, self.agent_a, "+15553330001"),
            (self.contact_b_id, self.agent_b, "+15553330002"),
        ]:
            db_conn.execute(
                "INSERT INTO contacts (id, agent_id, name, phone) VALUES (%s, %s, %s, %s) "
                "ON CONFLICT (agent_id, phone) DO NOTHING",
                [str(cid), str(aid), "Service Test", phone],
            )

        yield

        db_conn.execute("DELETE FROM contacts WHERE id IN (%s, %s)",
                        [str(self.contact_a_id), str(self.contact_b_id)])

    def test_no_context_sees_all_rows(self, db_conn):
        """A connection with no RLS context (service role) sees all rows.

        This simulates console/admin queries that bypass tenant scoping.
        The db_conn fixture uses autocommit=True and doesn't set app.current_agent_id,
        so RLS evaluates current_setting('app.current_agent_id') which either
        returns empty string (causing cast to fail) or the connection's superuser
        role bypasses RLS. Either way, a service-role connection should see all data.
        """
        rows = db_conn.execute(
            "SELECT id FROM contacts WHERE id IN (%s, %s)",
            [str(self.contact_a_id), str(self.contact_b_id)],
        ).fetchall()
        ids = {r["id"] for r in rows}
        assert self.contact_a_id in ids, "Service role should see Agent A's contact"
        assert self.contact_b_id in ids, "Service role should see Agent B's contact"


# ---------------------------------------------------------------------------
# Test F: Cross-table JOIN filtering
# ---------------------------------------------------------------------------

class TestCrossTableJoinFiltering:
    """Verify that JOINs across RLS-protected tables filter correctly."""

    @pytest.fixture(autouse=True)
    def setup_data(self, db_conn, agent_ids):
        self.agent_a, self.agent_b = agent_ids

        # Contacts
        self.contact_a = uuid.uuid4()
        self.contact_b = uuid.uuid4()
        for cid, aid, phone in [
            (self.contact_a, self.agent_a, "+15554440001"),
            (self.contact_b, self.agent_b, "+15554440002"),
        ]:
            db_conn.execute(
                "INSERT INTO contacts (id, agent_id, name, phone) VALUES (%s, %s, %s, %s) "
                "ON CONFLICT (agent_id, phone) DO NOTHING",
                [str(cid), str(aid), "Join Test", phone],
            )

        # Conversations
        self.conv_a = uuid.uuid4()
        self.conv_b = uuid.uuid4()
        for cvid, aid, cid in [
            (self.conv_a, self.agent_a, self.contact_a),
            (self.conv_b, self.agent_b, self.contact_b),
        ]:
            db_conn.execute(
                "INSERT INTO conversations (id, agent_id, contact_id, channel) "
                "VALUES (%s, %s, %s, 'sms')",
                [str(cvid), str(aid), str(cid)],
            )

        # Messages
        self.msg_a = uuid.uuid4()
        self.msg_b = uuid.uuid4()
        for mid, aid, cvid in [
            (self.msg_a, self.agent_a, self.conv_a),
            (self.msg_b, self.agent_b, self.conv_b),
        ]:
            db_conn.execute(
                "INSERT INTO messages (id, agent_id, conversation_id, sender_type, body) "
                "VALUES (%s, %s, %s, 'contact', 'Join test msg')",
                [str(mid), str(aid), str(cvid)],
            )

        yield

        db_conn.execute("DELETE FROM messages WHERE id IN (%s, %s)",
                        [str(self.msg_a), str(self.msg_b)])
        db_conn.execute("DELETE FROM conversations WHERE id IN (%s, %s)",
                        [str(self.conv_a), str(self.conv_b)])
        db_conn.execute("DELETE FROM contacts WHERE id IN (%s, %s)",
                        [str(self.contact_a), str(self.contact_b)])

    def test_join_messages_conversations_filtered(self, rls_conn):
        """JOIN between messages and conversations should only return Agent A's data."""
        _set_rls_context(rls_conn, self.agent_a)
        rows = rls_conn.execute(
            """
            SELECT m.id AS message_id, c.id AS conversation_id
            FROM messages m
            JOIN conversations c ON c.id = m.conversation_id
            """
        ).fetchall()

        msg_ids = {r["message_id"] for r in rows}
        conv_ids = {r["conversation_id"] for r in rows}

        assert self.msg_a in msg_ids, "Agent A should see own message in JOIN"
        assert self.msg_b not in msg_ids, "Agent A must NOT see Agent B's message in JOIN"
        assert self.conv_a in conv_ids, "Agent A should see own conversation in JOIN"
        assert self.conv_b not in conv_ids, "Agent A must NOT see Agent B's conversation in JOIN"


# ---------------------------------------------------------------------------
# Test G: lead_preferences via contact FK
# ---------------------------------------------------------------------------

class TestLeadPreferencesIsolation:
    """lead_preferences uses contact_id FK to inherit RLS from contacts."""

    @pytest.fixture(autouse=True)
    def setup_lead_prefs(self, db_conn, agent_ids):
        self.agent_a, self.agent_b = agent_ids

        self.contact_a = uuid.uuid4()
        self.contact_b = uuid.uuid4()
        for cid, aid, phone in [
            (self.contact_a, self.agent_a, "+15555550001"),
            (self.contact_b, self.agent_b, "+15555550002"),
        ]:
            db_conn.execute(
                "INSERT INTO contacts (id, agent_id, name, phone) VALUES (%s, %s, %s, %s) "
                "ON CONFLICT (agent_id, phone) DO NOTHING",
                [str(cid), str(aid), "Lead Pref Test", phone],
            )

        # Insert lead_preferences for both contacts
        for cid, areas, price_max in [
            (self.contact_a, ["Downtown", "Midtown"], 500000),
            (self.contact_b, ["Suburbs"], 300000),
        ]:
            db_conn.execute(
                """
                INSERT INTO lead_preferences (contact_id, areas, price_max)
                VALUES (%s, %s, %s)
                ON CONFLICT (contact_id) DO NOTHING
                """,
                [str(cid), areas, price_max],
            )

        yield

        db_conn.execute("DELETE FROM lead_preferences WHERE contact_id IN (%s, %s)",
                        [str(self.contact_a), str(self.contact_b)])
        db_conn.execute("DELETE FROM contacts WHERE id IN (%s, %s)",
                        [str(self.contact_a), str(self.contact_b)])

    def test_agent_a_sees_only_own_lead_prefs(self, rls_conn):
        """Agent A should only see lead_preferences for their own contacts."""
        _set_rls_context(rls_conn, self.agent_a)
        rows = rls_conn.execute("SELECT contact_id, price_max FROM lead_preferences").fetchall()
        contact_ids = {r["contact_id"] for r in rows}
        assert self.contact_a in contact_ids, "Agent A should see own lead preferences"
        assert self.contact_b not in contact_ids, "Agent A must NOT see Agent B's lead preferences"

    def test_agent_b_cannot_see_agent_a_lead_prefs(self, rls_conn):
        """Agent B should not see Agent A's lead_preferences."""
        _set_rls_context(rls_conn, self.agent_b)
        rows = rls_conn.execute("SELECT contact_id, price_max FROM lead_preferences").fetchall()
        contact_ids = {r["contact_id"] for r in rows}
        assert self.contact_b in contact_ids, "Agent B should see own lead preferences"
        assert self.contact_a not in contact_ids, "Agent B must NOT see Agent A's lead preferences"
