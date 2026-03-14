"""Transaction tools — create, update, query transactions."""
import logging
from datetime import datetime, timezone
from uuid import UUID

from app.db.connection import get_db_connection

import psycopg
from app.models.schemas import Transaction
from app.tools.sql_utils import build_safe_update_clause

logger = logging.getLogger(__name__)

VALID_STATUSES = {
    "pending_offer", "under_contract", "contingency",
    "clear_to_close", "closed", "fell_through",
}

VALID_TRANSACTION_TYPES = {"purchase", "sale", "lease"}


def create_transaction(
    agent_id: UUID,
    contact_id: UUID,
    listing_id: UUID | None = None,
    transaction_type: str = "purchase",
    offer_price: int | None = None,
    offer_date=None,
    closing_date=None,
    notes: str | None = None,
) -> Transaction:
    """Create a new transaction record."""
    with get_db_connection() as conn:
        row = conn.execute(
            """INSERT INTO transactions
               (agent_id, contact_id, listing_id, transaction_type, offer_price,
                offer_date, closing_date, notes)
               VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
               RETURNING *""",
            [str(agent_id), str(contact_id),
             str(listing_id) if listing_id else None,
             transaction_type, offer_price, offer_date, closing_date, notes],
        ).fetchone()

        # Auto-update contact lifecycle stage (same transaction)
        conn.execute(
            "UPDATE contacts SET lifecycle_stage = 'under_contract' WHERE id = %s",
            [str(contact_id)],
        )
        conn.commit()

    logger.info("Created transaction %s for contact %s", row["id"], contact_id)

    return Transaction(**row)


def update_transaction(
    transaction_id: UUID,
    agent_id: UUID,
    **fields,
) -> Transaction | None:
    """Update transaction fields."""
    valid_fields = {
        "status", "offer_price", "final_price", "offer_date", "contract_date",
        "closing_date", "inspection_date", "appraisal_date", "financing_deadline",
        "earnest_money", "commission_pct", "notes", "listing_id",
    }
    set_clause, values = build_safe_update_clause(fields, valid_fields)
    if not set_clause:
        return None

    values.extend([str(transaction_id), str(agent_id)])

    with get_db_connection() as conn:
        row = conn.execute(
            f"""UPDATE transactions SET {set_clause}, updated_at = now()
                WHERE id = %s AND agent_id = %s
                RETURNING *""",
            values,
        ).fetchone()
        conn.commit()

    if not row:
        return None

    # If status changed to closed, update contact lifecycle
    if "status" in updates:
        _sync_contact_lifecycle(row["contact_id"], updates["status"])

    return Transaction(**row)


def get_transactions(
    agent_id: UUID,
    status: str | None = None,
    contact_id: UUID | None = None,
) -> list[Transaction]:
    """Get transactions with optional filters."""
    conditions = ["agent_id = %s"]
    params = [str(agent_id)]

    if status:
        conditions.append("status = %s")
        params.append(status)
    if contact_id:
        conditions.append("contact_id = %s")
        params.append(str(contact_id))

    where = " AND ".join(conditions)

    with get_db_connection() as conn:
        rows = conn.execute(
            f"""SELECT * FROM transactions WHERE {where}
                ORDER BY closing_date ASC NULLS LAST, created_at DESC
                LIMIT 50""",
            params,
        ).fetchall()

    return [Transaction(**r) for r in rows]


def get_transaction(transaction_id: UUID, agent_id: UUID) -> Transaction | None:
    """Get a single transaction by ID."""
    with get_db_connection() as conn:
        row = conn.execute(
            "SELECT * FROM transactions WHERE id = %s AND agent_id = %s",
            [str(transaction_id), str(agent_id)],
        ).fetchone()

    return Transaction(**row) if row else None


def _sync_contact_lifecycle(contact_id, new_status: str) -> None:
    """Sync contact lifecycle_stage when transaction status changes."""
    stage_map = {
        "pending_offer": "active_buyer",
        "under_contract": "under_contract",
        "contingency": "under_contract",
        "clear_to_close": "under_contract",
        "closed": "past_client",
        "fell_through": "active_buyer",
    }
    stage = stage_map.get(new_status)
    if not stage:
        return
    try:
        with get_db_connection() as conn:
            conn.execute(
                "UPDATE contacts SET lifecycle_stage = %s WHERE id = %s",
                [stage, str(contact_id)],
            )
            conn.commit()
    except psycopg.Error as e:
        logger.error("Failed to sync contact lifecycle: %s", e)
