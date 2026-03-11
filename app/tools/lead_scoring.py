"""Lead scoring — rule-based scoring from existing contact signals."""
import logging
from datetime import datetime, timezone, timedelta
from uuid import UUID

from app.db.connection import get_db_connection

logger = logging.getLogger(__name__)

# Score weights — each signal contributes points
SCORING_RULES = {
    # Recency of contact (higher = more recent = hotter)
    "contacted_today": 20,
    "contacted_3d": 15,
    "contacted_7d": 10,
    "contacted_14d": 5,
    "contacted_30d": 0,
    "no_contact_30d": -10,
    # Engagement
    "high_interaction": 15,       # 10+ interactions
    "medium_interaction": 10,     # 5-9 interactions
    "low_interaction": 5,         # 1-4 interactions
    # Lifecycle stage
    "under_contract": 25,
    "active_buyer": 20,
    "qualified_lead": 15,
    "new_lead": 10,
    "past_client": 5,
    # Showings
    "has_showing_scheduled": 15,
    "had_showing_week": 10,
    # Consent
    "consent_granted": 5,
    "consent_pending": 0,
    "consent_revoked": -50,       # effectively dead lead
    # Preferences
    "has_preferences": 5,
    "preapproved": 10,
}


def score_contact(agent_id: UUID, contact_id: UUID) -> dict:
    """Score a single contact. Returns {score, breakdown, tier}."""
    now = datetime.now(timezone.utc)

    with get_db_connection() as conn:
        contact = conn.execute(
            "SELECT * FROM contacts WHERE id = %s AND agent_id = %s",
            [str(contact_id), str(agent_id)],
        ).fetchone()

        if not contact:
            return {"score": 0, "breakdown": {}, "tier": "unknown"}

        # Check for scheduled showings
        upcoming_showing = conn.execute(
            """SELECT COUNT(*) as cnt FROM showings
               WHERE contact_id = %s AND agent_id = %s
               AND start_time > %s AND status IN ('confirmed', 'hold')""",
            [str(contact_id), str(agent_id), now],
        ).fetchone()

        recent_showing = conn.execute(
            """SELECT COUNT(*) as cnt FROM showings
               WHERE contact_id = %s AND agent_id = %s
               AND start_time > %s""",
            [str(contact_id), str(agent_id), now - timedelta(days=7)],
        ).fetchone()

        # Check preferences
        prefs = conn.execute(
            "SELECT * FROM lead_preferences WHERE contact_id = %s",
            [str(contact_id)],
        ).fetchone()

    breakdown = {}
    score = 0

    # Recency scoring
    if contact["last_contact_at"]:
        lc = contact["last_contact_at"]
        if not lc.tzinfo:
            lc = lc.replace(tzinfo=timezone.utc)
        days_since = (now - lc).days
        if days_since == 0:
            breakdown["contacted_today"] = SCORING_RULES["contacted_today"]
        elif days_since <= 3:
            breakdown["contacted_3d"] = SCORING_RULES["contacted_3d"]
        elif days_since <= 7:
            breakdown["contacted_7d"] = SCORING_RULES["contacted_7d"]
        elif days_since <= 14:
            breakdown["contacted_14d"] = SCORING_RULES["contacted_14d"]
        elif days_since <= 30:
            breakdown["contacted_30d"] = SCORING_RULES["contacted_30d"]
        else:
            breakdown["no_contact_30d"] = SCORING_RULES["no_contact_30d"]

    # Interaction count
    ic = contact["interaction_count"] or 0
    if ic >= 10:
        breakdown["high_interaction"] = SCORING_RULES["high_interaction"]
    elif ic >= 5:
        breakdown["medium_interaction"] = SCORING_RULES["medium_interaction"]
    elif ic >= 1:
        breakdown["low_interaction"] = SCORING_RULES["low_interaction"]

    # Lifecycle stage
    stage = contact["lifecycle_stage"]
    if stage in SCORING_RULES:
        breakdown[stage] = SCORING_RULES[stage]

    # Showings
    if upcoming_showing and upcoming_showing["cnt"] > 0:
        breakdown["has_showing_scheduled"] = SCORING_RULES["has_showing_scheduled"]
    if recent_showing and recent_showing["cnt"] > 0:
        breakdown["had_showing_week"] = SCORING_RULES["had_showing_week"]

    # Consent
    cs = contact["consent_status"]
    key = f"consent_{cs}" if f"consent_{cs}" in SCORING_RULES else "consent_pending"
    breakdown[key] = SCORING_RULES[key]

    # Preferences
    if prefs:
        breakdown["has_preferences"] = SCORING_RULES["has_preferences"]
        if prefs.get("preapproved"):
            breakdown["preapproved"] = SCORING_RULES["preapproved"]

    score = sum(breakdown.values())
    score = max(0, min(100, score))  # Clamp 0-100

    tier = _score_to_tier(score)

    return {"score": score, "breakdown": breakdown, "tier": tier}


def score_all_contacts(agent_id: UUID) -> list[dict]:
    """Score all contacts for an agent. Returns sorted list.

    Uses batch queries to avoid N+1 DB round trips.
    """
    now = datetime.now(timezone.utc)

    with get_db_connection() as conn:
        contacts = conn.execute(
            """SELECT id, name, phone, lifecycle_stage, last_contact_at,
                      interaction_count, consent_status
               FROM contacts WHERE agent_id = %s
               AND lifecycle_stage NOT IN ('inactive')
               ORDER BY last_contact_at DESC NULLS LAST""",
            [str(agent_id)],
        ).fetchall()

        # Batch fetch: upcoming showings per contact
        upcoming_rows = conn.execute(
            """SELECT contact_id, COUNT(*) as cnt FROM showings
               WHERE agent_id = %s AND start_time > %s
               AND status IN ('confirmed', 'hold')
               GROUP BY contact_id""",
            [str(agent_id), now],
        ).fetchall()
        upcoming_showings = {r["contact_id"]: r["cnt"] for r in upcoming_rows}

        # Batch fetch: recent showings (last 7 days) per contact
        recent_rows = conn.execute(
            """SELECT contact_id, COUNT(*) as cnt FROM showings
               WHERE agent_id = %s AND start_time > %s
               GROUP BY contact_id""",
            [str(agent_id), now - timedelta(days=7)],
        ).fetchall()
        recent_showings = {r["contact_id"]: r["cnt"] for r in recent_rows}

        # Batch fetch: all lead preferences for this agent's contacts
        pref_rows = conn.execute(
            """SELECT lp.* FROM lead_preferences lp
               JOIN contacts c ON c.id = lp.contact_id
               WHERE c.agent_id = %s""",
            [str(agent_id)],
        ).fetchall()
        prefs_by_contact = {r["contact_id"]: r for r in pref_rows}

    results = []
    for c in contacts:
        breakdown = {}

        # Recency scoring
        if c["last_contact_at"]:
            lc = c["last_contact_at"]
            if not lc.tzinfo:
                lc = lc.replace(tzinfo=timezone.utc)
            days_since = (now - lc).days
            if days_since == 0:
                breakdown["contacted_today"] = SCORING_RULES["contacted_today"]
            elif days_since <= 3:
                breakdown["contacted_3d"] = SCORING_RULES["contacted_3d"]
            elif days_since <= 7:
                breakdown["contacted_7d"] = SCORING_RULES["contacted_7d"]
            elif days_since <= 14:
                breakdown["contacted_14d"] = SCORING_RULES["contacted_14d"]
            elif days_since <= 30:
                breakdown["contacted_30d"] = SCORING_RULES["contacted_30d"]
            else:
                breakdown["no_contact_30d"] = SCORING_RULES["no_contact_30d"]

        # Interaction count
        ic = c["interaction_count"] or 0
        if ic >= 10:
            breakdown["high_interaction"] = SCORING_RULES["high_interaction"]
        elif ic >= 5:
            breakdown["medium_interaction"] = SCORING_RULES["medium_interaction"]
        elif ic >= 1:
            breakdown["low_interaction"] = SCORING_RULES["low_interaction"]

        # Lifecycle stage
        stage = c["lifecycle_stage"]
        if stage in SCORING_RULES:
            breakdown[stage] = SCORING_RULES[stage]

        # Showings (from pre-fetched data)
        contact_id = c["id"]
        if upcoming_showings.get(contact_id, 0) > 0:
            breakdown["has_showing_scheduled"] = SCORING_RULES["has_showing_scheduled"]
        if recent_showings.get(contact_id, 0) > 0:
            breakdown["had_showing_week"] = SCORING_RULES["had_showing_week"]

        # Consent
        cs = c["consent_status"]
        key = f"consent_{cs}" if f"consent_{cs}" in SCORING_RULES else "consent_pending"
        breakdown[key] = SCORING_RULES[key]

        # Preferences (from pre-fetched data)
        prefs = prefs_by_contact.get(contact_id)
        if prefs:
            breakdown["has_preferences"] = SCORING_RULES["has_preferences"]
            if prefs.get("preapproved"):
                breakdown["preapproved"] = SCORING_RULES["preapproved"]

        score = sum(breakdown.values())
        score = max(0, min(100, score))
        tier = _score_to_tier(score)

        results.append({
            "contact_id": contact_id,
            "name": c["name"],
            "phone": c["phone"],
            "lifecycle_stage": c["lifecycle_stage"],
            "score": score,
            "tier": tier,
        })

    results.sort(key=lambda x: x["score"], reverse=True)
    return results


def _score_to_tier(score: int) -> str:
    """Convert numeric score to tier label."""
    if score >= 70:
        return "hot"
    elif score >= 40:
        return "warm"
    elif score >= 20:
        return "cool"
    else:
        return "cold"
