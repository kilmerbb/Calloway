"""Contact tools — lookup, create, update, search, gap analysis."""
import logging
from datetime import datetime, timezone, timedelta
from uuid import UUID

from app.db.connection import get_db_connection
from app.models.schemas import Contact, LeadPreferences

logger = logging.getLogger(__name__)

# Gap thresholds by lifecycle stage (in days)
GAP_THRESHOLDS = {
    "active_buyer": 7,
    "active_seller": 14,
    "under_contract": 5,
    "new_lead": 3,
    "past_client": 90,
    "vendor": 30,
    "other_agent": 14,
}


def lookup_contact(
    agent_id: UUID, phone: str | None = None, name: str | None = None
) -> Contact | list[Contact] | None:
    """
    Look up a contact by phone (exact) or name (fuzzy).
    If name matches multiple, returns a list for disambiguation.
    """
    with get_db_connection() as conn:
        if phone:
            row = conn.execute(
                "SELECT * FROM contacts WHERE agent_id = %s AND phone = %s",
                [str(agent_id), phone],
            ).fetchone()
            return Contact(**row) if row else None

        if name:
            rows = conn.execute(
                "SELECT * FROM contacts WHERE agent_id = %s AND LOWER(name) LIKE LOWER(%s)",
                [str(agent_id), f"%{name}%"],
            ).fetchall()
            if not rows:
                return None
            if len(rows) == 1:
                return Contact(**rows[0])
            return [Contact(**r) for r in rows]

    return None


def create_contact(
    agent_id: UUID,
    name: str,
    phone: str,
    role: str = "lead",
    lifecycle_stage: str = "new_lead",
    email: str | None = None,
    preferences: dict | None = None,
    linked_listing_id: UUID | None = None,
) -> Contact:
    """Create a new contact and optionally a lead_preferences row."""
    with get_db_connection() as conn:
        row = conn.execute(
            """INSERT INTO contacts (agent_id, name, phone, email, role, lifecycle_stage,
                linked_listing_id, preferences, last_contact_at)
               VALUES (%s, %s, %s, %s, %s, %s, %s, %s, now())
               RETURNING *""",
            [
                str(agent_id), name, phone, email, role, lifecycle_stage,
                str(linked_listing_id) if linked_listing_id else None,
                "{}" if not preferences else str(preferences).replace("'", '"'),
            ],
        ).fetchone()
        conn.commit()

        contact = Contact(**row)

        # Create lead preferences if buyer data provided
        if preferences and role in ("buyer", "lead"):
            buyer_prefs = {}
            if "areas" in preferences:
                buyer_prefs["areas"] = preferences["areas"]
            if "price_max" in preferences:
                buyer_prefs["price_max"] = preferences["price_max"]
            if "price_min" in preferences:
                buyer_prefs["price_min"] = preferences["price_min"]
            if "preapproved" in preferences:
                buyer_prefs["preapproved"] = preferences["preapproved"]
            if "timeline" in preferences:
                buyer_prefs["timeline"] = preferences["timeline"]
            if "bedrooms_min" in preferences:
                buyer_prefs["bedrooms_min"] = preferences["bedrooms_min"]
            if "bathrooms_min" in preferences:
                buyer_prefs["bathrooms_min"] = preferences["bathrooms_min"]
            if "property_type" in preferences:
                buyer_prefs["property_type"] = preferences["property_type"]

            if buyer_prefs:
                areas_val = (
                    "{" + ",".join(f'"{a}"' for a in buyer_prefs.get("areas", [])) + "}"
                    if buyer_prefs.get("areas") else None
                )
                conn.execute(
                    """INSERT INTO lead_preferences (contact_id, areas, timeline, preapproved,
                        property_type, bedrooms_min, bathrooms_min, price_min, price_max)
                       VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                       ON CONFLICT (contact_id) DO NOTHING""",
                    [
                        str(contact.id), areas_val,
                        buyer_prefs.get("timeline"), buyer_prefs.get("preapproved"),
                        buyer_prefs.get("property_type"), buyer_prefs.get("bedrooms_min"),
                        buyer_prefs.get("bathrooms_min"),
                        buyer_prefs.get("price_min"), buyer_prefs.get("price_max"),
                    ],
                )
                conn.commit()

    logger.info(f"Created contact: {name} ({role})")
    return contact


def update_contact(contact_id: UUID, **updates) -> Contact:
    """Update a contact record. Always updates last_contact_at."""
    valid_fields = {
        "name", "phone", "email", "role", "lifecycle_stage",
        "linked_listing_id", "preferences", "notes", "silent_mode",
        "consent_status", "consent_granted_at", "consent_revoked_at",
        "consent_method", "consent_message", "consent_response",
        "language_detected", "interaction_count",
    }
    filtered = {k: v for k, v in updates.items() if k in valid_fields and v is not None}

    if not filtered:
        # Just update last_contact_at
        with get_db_connection() as conn:
            row = conn.execute(
                "UPDATE contacts SET last_contact_at = now(), updated_at = now() WHERE id = %s RETURNING *",
                [str(contact_id)],
            ).fetchone()
            conn.commit()
            return Contact(**row)

    set_clauses = ", ".join(f"{k} = %s" for k in filtered)
    values = list(filtered.values())
    values.append(str(contact_id))

    with get_db_connection() as conn:
        row = conn.execute(
            f"""UPDATE contacts SET {set_clauses}, last_contact_at = now(), updated_at = now()
                WHERE id = %s RETURNING *""",
            values,
        ).fetchone()
        conn.commit()

    return Contact(**row)


def search_contacts(agent_id: UUID, **filters) -> list[Contact]:
    """Search contacts with filters."""
    conditions = ["c.agent_id = %s"]
    params: list = [str(agent_id)]
    join_prefs = False

    if "lifecycle_stage" in filters:
        conditions.append("c.lifecycle_stage = %s")
        params.append(filters["lifecycle_stage"])

    if "role" in filters:
        conditions.append("c.role = %s")
        params.append(filters["role"])

    if "areas" in filters:
        # ANY match on lead_preferences.areas
        join_prefs = True
        conditions.append("lp.areas && %s")
        areas_val = "{" + ",".join(f'"{a}"' for a in filters["areas"]) + "}"
        params.append(areas_val)

    if "price_min" in filters and "price_max" in filters:
        join_prefs = True
        conditions.append("(lp.price_max >= %s OR lp.price_max IS NULL)")
        conditions.append("(lp.price_min <= %s OR lp.price_min IS NULL)")
        params.append(filters["price_min"])
        params.append(filters["price_max"])

    if "last_contact_before" in filters:
        conditions.append("c.last_contact_at < %s")
        params.append(filters["last_contact_before"])

    if "last_contact_after" in filters:
        conditions.append("c.last_contact_at > %s")
        params.append(filters["last_contact_after"])

    where = " AND ".join(conditions)

    join_clause = ""
    if join_prefs:
        join_clause = "LEFT JOIN lead_preferences lp ON lp.contact_id = c.id"

    with get_db_connection() as conn:
        rows = conn.execute(
            f"SELECT c.* FROM contacts c {join_clause} WHERE {where} ORDER BY c.name LIMIT 50",
            params,
        ).fetchall()

    return [Contact(**r) for r in rows]


def analyze_contact_gaps(agent_id: UUID) -> list[dict]:
    """
    Find contacts exceeding their lifecycle-appropriate contact gap thresholds.
    Shared between agent command "Who needs follow-up?" and daily scanner.
    """
    now = datetime.now(timezone.utc)
    results = []

    with get_db_connection() as conn:
        rows = conn.execute(
            """SELECT * FROM contacts
               WHERE agent_id = %s
               AND lifecycle_stage IN ('active_buyer', 'active_seller', 'under_contract', 'new_lead', 'past_client')
               AND silent_mode = false
               ORDER BY last_contact_at ASC NULLS FIRST""",
            [str(agent_id)],
        ).fetchall()

    for row in rows:
        contact = Contact(**row)
        threshold = GAP_THRESHOLDS.get(contact.lifecycle_stage, 14)

        if contact.last_contact_at is None:
            days_since = 999
        else:
            last = contact.last_contact_at.replace(tzinfo=timezone.utc) if contact.last_contact_at.tzinfo is None else contact.last_contact_at
            days_since = (now - last).days

        if days_since >= threshold:
            # Suggest an action based on lifecycle stage
            if contact.lifecycle_stage == "active_buyer":
                suggested = "Send listing alert or check-in"
            elif contact.lifecycle_stage == "active_seller":
                suggested = "Send activity update"
            elif contact.lifecycle_stage == "under_contract":
                suggested = "Check on milestone progress"
            elif contact.lifecycle_stage == "new_lead":
                suggested = "Follow up on initial inquiry"
            elif contact.lifecycle_stage == "past_client":
                suggested = "Send check-in or market update"
            else:
                suggested = "General follow-up"

            results.append({
                "contact": contact,
                "days_since_contact": days_since,
                "lifecycle_stage": contact.lifecycle_stage,
                "suggested_action": suggested,
            })

    # Sort by urgency (days over threshold)
    results.sort(
        key=lambda x: x["days_since_contact"] - GAP_THRESHOLDS.get(x["lifecycle_stage"], 14),
        reverse=True,
    )

    return results
