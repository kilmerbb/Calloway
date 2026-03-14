"""
Calloway Load Test — Idempotent seed data script.

Creates a test agent and test contacts in the database so that the load
test payloads resolve correctly through the pipeline.

Usage:
    python -m tests.load.seed_data

Environment:
    DATABASE_URL must be set (or present in .env).
"""

import os
import sys
import uuid
import logging

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

# Fixed UUIDs for idempotency
TEST_AGENT_ID = uuid.UUID("00000000-0000-0000-0000-000000000001")
TEST_AGENT_TWILIO_NUMBER = "+15550000001"
TEST_AGENT_EMAIL = "loadtest@calloway.test"
TEST_AGENT_PHONE = "+15550000000"

NUM_CONTACTS = 100


def get_connection():
    """Get a database connection using the app's config or DATABASE_URL env."""
    try:
        from app.db.connection import get_db_connection
        return get_db_connection()
    except Exception:
        pass

    # Fallback: direct psycopg connection
    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        logger.error("DATABASE_URL not set. Cannot connect to database.")
        sys.exit(1)

    try:
        import psycopg
        return psycopg.connect(database_url, row_factory=psycopg.rows.dict_row)
    except ImportError:
        import psycopg2
        import psycopg2.extras
        conn = psycopg2.connect(database_url)
        conn.cursor_factory = psycopg2.extras.RealDictCursor
        return conn


def seed_agent(conn) -> None:
    """Create the test agent if it doesn't exist."""
    cur = conn.execute(
        "SELECT id FROM agents WHERE id = %s", [str(TEST_AGENT_ID)]
    )
    if cur.fetchone():
        logger.info("Test agent already exists: %s", TEST_AGENT_ID)
        return

    conn.execute(
        """INSERT INTO agents (id, name, email, phone, twilio_number, timezone, brokerage, market)
           VALUES (%s, %s, %s, %s, %s, %s, %s, %s)""",
        [
            str(TEST_AGENT_ID),
            "Load Test Agent",
            TEST_AGENT_EMAIL,
            TEST_AGENT_PHONE,
            TEST_AGENT_TWILIO_NUMBER,
            "America/New_York",
            "Test Brokerage",
            "Test Market",
        ],
    )
    conn.commit()
    logger.info("Created test agent: %s (%s)", TEST_AGENT_ID, TEST_AGENT_TWILIO_NUMBER)


def seed_contacts(conn) -> None:
    """Create test contacts for the test agent (idempotent)."""
    created = 0
    for i in range(NUM_CONTACTS):
        phone = f"+1555010{str(i).zfill(4)}"
        cur = conn.execute(
            "SELECT id FROM contacts WHERE agent_id = %s AND phone = %s",
            [str(TEST_AGENT_ID), phone],
        )
        if cur.fetchone():
            continue

        conn.execute(
            """INSERT INTO contacts (agent_id, name, phone, role, lifecycle_stage, consent_status)
               VALUES (%s, %s, %s, %s, %s, %s)""",
            [
                str(TEST_AGENT_ID),
                f"LoadTest Contact {i}",
                phone,
                "lead",
                "new_lead",
                "granted",
            ],
        )
        created += 1

    conn.commit()
    if created:
        logger.info("Created %d test contacts", created)
    else:
        logger.info("All %d test contacts already exist", NUM_CONTACTS)


def main() -> None:
    logger.info("Seeding load test data...")
    conn = get_connection()
    try:
        seed_agent(conn)
        seed_contacts(conn)
        logger.info("Seed complete.")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
