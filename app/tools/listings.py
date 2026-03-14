"""Listing tools — ingest, retrieve, and search listings."""
import json
import logging
from datetime import datetime, timezone, timedelta
from decimal import Decimal
from uuid import UUID

from app.db.connection import get_db_connection
from app.models.schemas import Listing
from app.services.anthropic_service import get_anthropic_client
from app.tools.sql_utils import build_safe_update_clause

logger = logging.getLogger(__name__)

LISTING_PARSE_PROMPT = """Extract listing details from this text. Return JSON with these fields:
{
  "address": string or null,
  "price": integer or null,
  "beds": integer or null,
  "baths": float or null,
  "sqft": integer or null,
  "hoa": integer or null,
  "features": [list of feature strings] or [],
  "lockbox": string or null,
  "showing_instructions": string or null
}

Be precise. Convert "3/2" to beds=3, baths=2. Convert "475K" to 475000.
Return ONLY valid JSON."""


def ingest_listing(agent_id: UUID, text: str) -> tuple[Listing, list[str]]:
    """
    Parse natural language listing description into a structured record.
    Returns (listing, missing_fields).
    """
    client = get_anthropic_client()
    result = client.classify(LISTING_PARSE_PROMPT, text, agent_id, max_tokens=300)

    # Remove internal tracking fields
    result.pop("_tokens", None)
    result.pop("_latency_ms", None)
    result.pop("raw_response", None)

    address = result.get("address")
    price = result.get("price")

    if not address or not price:
        raise ValueError(f"Could not extract address and price from: {text}")

    # Check if listing already exists (for updates like "Drop 123 Oak to 465K")
    existing = get_listing(agent_id, address=address)
    if existing:
        return update_listing(agent_id, existing.id, result)

    # Insert new listing
    features = json.dumps(result.get("features", []))
    access_rules = json.dumps({"type": "vacant", "approval_required": False})

    with get_db_connection() as conn:
        row = conn.execute(
            """INSERT INTO listings (agent_id, address, price, beds, baths, sqft, hoa,
                features, showing_instructions, lockbox, access_rules, list_date, status)
               VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, CURRENT_DATE, 'active')
               RETURNING *""",
            [
                str(agent_id), address, price,
                result.get("beds"), result.get("baths"), result.get("sqft"),
                result.get("hoa"), features,
                result.get("showing_instructions"), result.get("lockbox"),
                access_rules,
            ],
        ).fetchone()
        conn.commit()

    listing = Listing(**row)

    # Identify missing fields
    important_fields = ["beds", "baths", "sqft", "showing_instructions", "lockbox"]
    missing = [f for f in important_fields if not result.get(f)]

    logger.info(f"Created listing: {address} at ${price}")
    return listing, missing


def update_listing(
    agent_id: UUID, listing_id: UUID, updates: dict
) -> tuple[Listing, list[str]]:
    """Apply updates to an existing listing."""
    valid_fields = {
        "address", "price", "beds", "baths", "sqft", "hoa",
        "features", "showing_instructions", "lockbox", "status", "notes",
    }

    # Pre-process features before validation
    if "features" in updates and isinstance(updates.get("features"), list):
        updates["features"] = json.dumps(updates["features"])

    set_clauses, values = build_safe_update_clause(updates, valid_fields)

    if not set_clauses:
        existing = get_listing(agent_id, listing_id=listing_id)
        return existing, []

    values.extend([str(listing_id), str(agent_id)])

    with get_db_connection() as conn:
        row = conn.execute(
            f"""UPDATE listings SET {set_clauses}, last_updated_at = now()
                WHERE id = %s AND agent_id = %s
                RETURNING *""",
            values,
        ).fetchone()
        conn.commit()

    if row is None:
        raise ValueError(f"Listing {listing_id} not found")

    listing = Listing(**row)
    logger.info(f"Updated listing: {listing.address}")
    return listing, []


def get_listing(
    agent_id: UUID, address: str | None = None, listing_id: UUID | None = None
) -> Listing | None:
    """Get a listing by ID or address (fuzzy match). Includes freshness check."""
    with get_db_connection() as conn:
        if listing_id:
            row = conn.execute(
                "SELECT * FROM listings WHERE id = %s AND agent_id = %s",
                [str(listing_id), str(agent_id)],
            ).fetchone()
        elif address:
            # Fuzzy match on address (case-insensitive contains)
            row = conn.execute(
                "SELECT * FROM listings WHERE agent_id = %s AND LOWER(address) LIKE LOWER(%s) LIMIT 1",
                [str(agent_id), f"%{address}%"],
            ).fetchone()
        else:
            return None

    if row is None:
        return None

    listing = Listing(**row)

    # Freshness check
    if listing.last_updated_at:
        age = datetime.now(timezone.utc) - listing.last_updated_at.replace(tzinfo=timezone.utc)
        if age > timedelta(days=7):
            listing.freshness_warning = f"Last updated {age.days} days ago. Data may be stale."

    return listing


def search_listings(
    agent_id: UUID,
    query: str | None = None,
    filters: dict | None = None,
) -> list[Listing]:
    """
    Search listings by semantic query and/or structured filters.
    Returns up to 10 results.
    """
    conditions = ["agent_id = %s"]
    params: list = [str(agent_id)]

    if filters:
        if "status" in filters:
            conditions.append("status = %s")
            params.append(filters["status"])
        if "price_min" in filters:
            conditions.append("price >= %s")
            params.append(filters["price_min"])
        if "price_max" in filters:
            conditions.append("price <= %s")
            params.append(filters["price_max"])
        if "beds_min" in filters:
            conditions.append("beds >= %s")
            params.append(filters["beds_min"])
        if "baths_min" in filters:
            conditions.append("baths >= %s")
            params.append(filters["baths_min"])
        if "address" in filters:
            conditions.append("LOWER(address) LIKE LOWER(%s)")
            params.append(f"%{filters['address']}%")

    where = " AND ".join(conditions)

    with get_db_connection() as conn:
        rows = conn.execute(
            f"SELECT * FROM listings WHERE {where} ORDER BY created_at DESC LIMIT 10",
            params,
        ).fetchall()

    listings = [Listing(**row) for row in rows]

    # Add freshness warnings
    now = datetime.now(timezone.utc)
    for listing in listings:
        if listing.last_updated_at:
            age = now - listing.last_updated_at.replace(tzinfo=timezone.utc)
            if age > timedelta(days=7):
                listing.freshness_warning = f"Last updated {age.days} days ago."

    return listings
