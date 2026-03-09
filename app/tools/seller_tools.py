"""Seller tools — listing inquiry routing, occupied showing, activity tracking, DOM alerts."""
import logging
from datetime import datetime, timezone, timedelta
from uuid import UUID

from app.db.connection import get_db_connection
from app.models.schemas import Listing, Contact, AgentConfig

logger = logging.getLogger(__name__)


# ============================================================
# Step 37: Listing Inquiry Handler for Sellers
# ============================================================

def route_listing_inquiry(
    agent: AgentConfig,
    listing: Listing,
    contact: Contact | None,
    inquiry_body: str,
) -> dict:
    """
    Route a listing inquiry based on whether the listing is occupied/vacant
    and buyer vs. agent inquiry.
    Returns routing decision dict.
    """
    is_occupied = listing.access_rules.get("type") == "occupied"
    is_agent_inquiry = contact and contact.role == "other_agent" if contact else False

    decision = {
        "listing_id": str(listing.id),
        "address": listing.address,
        "is_occupied": is_occupied,
        "needs_seller_approval": False,
        "can_auto_respond": True,
        "showing_instructions": listing.showing_instructions,
        "lockbox_code": None,
        "seller_contact": None,
    }

    # Occupied homes need seller approval for showings
    if is_occupied:
        decision["needs_seller_approval"] = True
        decision["can_auto_respond"] = False
        seller_id = listing.access_rules.get("seller_contact_id")
        if seller_id:
            decision["seller_contact"] = seller_id

    # Agent inquiries get lockbox info after confirmation
    if is_agent_inquiry and not is_occupied:
        decision["lockbox_code"] = listing.lockbox

    return decision


def get_seller_for_listing(agent_id: UUID, listing_id: UUID) -> Contact | None:
    """Get the seller contact linked to a listing."""
    with get_db_connection() as conn:
        row = conn.execute(
            """SELECT c.* FROM contacts c
               WHERE c.agent_id = %s AND c.linked_listing_id = %s
               AND c.role = 'seller'
               LIMIT 1""",
            [str(agent_id), str(listing_id)],
        ).fetchone()

    return Contact(**row) if row else None


# ============================================================
# Step 38: Occupied Home Showing Coordination
# ============================================================

def request_occupied_showing(
    agent: AgentConfig,
    listing: Listing,
    contact: Contact,
    desired_time: datetime,
) -> dict:
    """
    Request a showing for an occupied property.
    Creates a hold and notifies the agent (who must get seller approval).
    """
    from app.tools.showings import create_showing_hold

    hold = create_showing_hold(
        agent_id=agent.id,
        contact_id=contact.id,
        listing_id=listing.id,
        desired_time=desired_time,
    )

    # Get seller contact
    seller = get_seller_for_listing(agent.id, listing.id)

    return {
        "hold": hold,
        "needs_seller_approval": True,
        "seller_name": seller.name if seller else None,
        "notification": {
            "tier": "action_needed",
            "title": f"Showing request: {listing.address}",
            "body": (
                f"{contact.name} wants to see {listing.address} at "
                f"{desired_time.strftime('%A %I:%M %p')}. "
                f"{'Contact ' + seller.name + ' for approval.' if seller else 'Confirm with seller.'}"
            ),
        },
    }


# ============================================================
# Step 39: Listing Activity Tracker
# ============================================================

def get_listing_activity(agent_id: UUID, listing_id: UUID, days: int = 7) -> dict:
    """Get activity summary for a listing over the last N days."""
    since = datetime.now(timezone.utc) - timedelta(days=days)

    with get_db_connection() as conn:
        # Showing count and details
        showings = conn.execute(
            """SELECT s.*, c.name as contact_name FROM showings s
               JOIN contacts c ON s.contact_id = c.id
               WHERE s.listing_id = %s AND s.agent_id = %s
               AND s.created_at > %s
               ORDER BY s.start_time DESC""",
            [str(listing_id), str(agent_id), since],
        ).fetchall()

        # Inquiry count from messages
        listing_row = conn.execute(
            "SELECT address FROM listings WHERE id = %s",
            [str(listing_id)],
        ).fetchone()

        inquiry_count = 0
        if listing_row:
            result = conn.execute(
                """SELECT COUNT(*) as cnt FROM messages m
                   JOIN conversations c ON m.conversation_id = c.id
                   WHERE c.agent_id = %s AND m.created_at > %s
                   AND m.sender_type = 'client'
                   AND LOWER(m.body) LIKE LOWER(%s)""",
                [str(agent_id), since, f"%{listing_row['address'][:20]}%"],
            ).fetchone()
            inquiry_count = result["cnt"] if result else 0

        # Feedback
        feedback = [
            {"client": s["contact_name"], "feedback": s["feedback"]}
            for s in showings if s.get("feedback")
        ]

    return {
        "listing_id": str(listing_id),
        "period_days": days,
        "showings_total": len(showings),
        "showings_confirmed": sum(1 for s in showings if s["status"] == "confirmed"),
        "showings_cancelled": sum(1 for s in showings if s["status"] == "cancelled"),
        "inquiries": inquiry_count,
        "feedback": feedback,
        "showings_detail": [
            {
                "client": s["contact_name"],
                "time": s["start_time"].isoformat() if s["start_time"] else None,
                "status": s["status"],
            }
            for s in showings
        ],
    }


# ============================================================
# Step 40: DOM Alerter
# ============================================================

DOM_THRESHOLDS = [14, 30, 45, 60, 90]

DOM_RECOMMENDATIONS = {
    14: "Consider social media boost or open house.",
    30: "Review pricing strategy. Market data suggests a price adjustment may increase showing activity.",
    45: "Strong recommendation for price adjustment. Showing-to-day ratio is below market average.",
    60: "Critical: 60+ DOM signals pricing or presentation issues. Consider fresh photos, staging updates.",
    90: "90+ DOM: Recommend temporary withdrawal and relist, or significant price reduction.",
}


def check_dom_status(listing: Listing) -> dict | None:
    """Check if a listing has hit a DOM threshold and return alert info."""
    if not listing.list_date:
        return None

    dom = (datetime.now(timezone.utc).date() - listing.list_date).days

    for threshold in reversed(DOM_THRESHOLDS):
        if dom >= threshold:
            recommendation = DOM_RECOMMENDATIONS.get(threshold, "Review listing strategy.")
            return {
                "listing_id": str(listing.id),
                "address": listing.address,
                "dom": dom,
                "threshold_hit": threshold,
                "price": listing.price,
                "recommendation": recommendation,
            }

    return None


def format_dom_alert(alert: dict) -> str:
    """Format a DOM alert for agent notification."""
    return (
        f"DOM Alert: {alert['address']}\n"
        f"{alert['dom']} days on market at ${alert['price']:,}\n"
        f"Recommendation: {alert['recommendation']}"
    )


# ============================================================
# Step 41: Open House Integration
# ============================================================

def schedule_open_house(
    agent: AgentConfig,
    listing: Listing,
    open_house_date: datetime,
    duration_hours: int = 2,
) -> dict:
    """
    Schedule an open house and create the trigger cascade.
    Updates listing.open_house_dates and creates cascade triggers.
    """
    from app.tools.triggers import create_trigger_cascade

    end_time = open_house_date + timedelta(hours=duration_hours)

    # Update listing with open house date
    with get_db_connection() as conn:
        # Get current open house dates
        row = conn.execute(
            "SELECT open_house_dates FROM listings WHERE id = %s",
            [str(listing.id)],
        ).fetchone()

        current_dates = row["open_house_dates"] if row and row["open_house_dates"] else []
        if isinstance(current_dates, str):
            import json
            current_dates = json.loads(current_dates)

        current_dates.append({
            "date": open_house_date.isoformat(),
            "end": end_time.isoformat(),
            "status": "scheduled",
        })

        import json
        conn.execute(
            "UPDATE listings SET open_house_dates = %s WHERE id = %s",
            [json.dumps(current_dates), str(listing.id)],
        )
        conn.commit()

    # Create the trigger cascade
    triggers = create_trigger_cascade(
        agent_id=agent.id,
        cascade_type="open_house",
        entity_id=listing.id,
        base_date=open_house_date,
    )

    # Find matching buyers to notify
    from app.tools.contacts import search_contacts
    matching_buyers = search_contacts(agent.id, lifecycle_stage="active_buyer")

    return {
        "open_house_date": open_house_date.isoformat(),
        "end_time": end_time.isoformat(),
        "triggers_created": len(triggers),
        "matching_buyers": len(matching_buyers),
        "address": listing.address,
    }


def get_open_house_attendees(agent_id: UUID, listing_id: UUID) -> list[dict]:
    """Get showing records around open house dates as attendee proxy."""
    with get_db_connection() as conn:
        rows = conn.execute(
            """SELECT s.*, c.name, c.phone, c.email FROM showings s
               JOIN contacts c ON s.contact_id = c.id
               WHERE s.listing_id = %s AND s.agent_id = %s
               AND s.status = 'confirmed'
               ORDER BY s.start_time DESC LIMIT 20""",
            [str(listing_id), str(agent_id)],
        ).fetchall()

    return [
        {
            "name": r["name"],
            "phone": r["phone"],
            "email": r.get("email"),
            "time": r["start_time"].isoformat() if r["start_time"] else None,
        }
        for r in rows
    ]
