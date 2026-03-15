"""Drip campaign tools — create campaigns, enroll contacts, advance steps."""
import json
import logging
from datetime import datetime, timezone, timedelta
from uuid import UUID

from app.db.connection import get_db_connection
from app.models.schemas import DripCampaign, DripEnrollment

logger = logging.getLogger(__name__)

# Built-in campaign templates
DEFAULT_CAMPAIGNS = [
    {
        "name": "New Buyer Nurture",
        "description": "5-touch sequence for new buyer leads over 30 days",
        "trigger_type": "nurture",
        "steps": [
            {"day": 0, "message": "Thanks for reaching out! I'd love to help you find your perfect home. What areas are you most interested in?", "action_type": "send_message"},
            {"day": 3, "message": "Just checking in — have you had a chance to think about what you're looking for? I have some great listings I can share.", "action_type": "send_message"},
            {"day": 7, "message": None, "action_type": "notify_agent"},
            {"day": 14, "message": "Hi! The market is moving fast. Want me to set up some showings this week?", "action_type": "send_message"},
            {"day": 30, "message": "Still looking? I'm here whenever you're ready. Let me know if anything has changed!", "action_type": "send_message"},
        ],
    },
    {
        "name": "Past Client Check-in",
        "description": "Quarterly touchpoints for past clients",
        "trigger_type": "retention",
        "steps": [
            {"day": 0, "message": "Hi! Hope you're enjoying your home. If you ever need contractor recommendations, just ask!", "action_type": "send_message"},
            {"day": 90, "message": "Just checking in! How's everything going with the house?", "action_type": "send_message"},
            {"day": 180, "message": "Happy half-year in your home! Need anything?", "action_type": "send_message"},
            {"day": 270, "message": None, "action_type": "notify_agent"},
            {"day": 365, "message": "Happy homeversary! It's been a year already. Here's a market update for your neighborhood.", "action_type": "send_message"},
        ],
    },
    {
        "name": "Open House Follow-up",
        "description": "Post-open house engagement sequence",
        "trigger_type": "follow_up",
        "steps": [
            {"day": 1, "message": "Thanks for visiting the open house! What did you think of the property?", "action_type": "send_message"},
            {"day": 3, "message": "I have some similar listings you might like. Want me to send them over?", "action_type": "send_message"},
            {"day": 7, "message": None, "action_type": "notify_agent"},
            {"day": 14, "message": "Still interested in properties in that area? I'd love to set up a private showing.", "action_type": "send_message"},
        ],
    },
]


def create_campaign(
    agent_id: UUID,
    name: str,
    steps: list[dict],
    description: str | None = None,
    trigger_type: str = "nurture",
) -> DripCampaign:
    """Create a new drip campaign."""
    with get_db_connection() as conn:
        row = conn.execute(
            """INSERT INTO drip_campaigns (agent_id, name, description, trigger_type, steps)
               VALUES (%s, %s, %s, %s, %s)
               RETURNING *""",
            [str(agent_id), name, description, trigger_type, json.dumps(steps)],
        ).fetchone()
        conn.commit()

    if not row:
        raise RuntimeError(f"Failed to create drip campaign '{name}'")
    logger.info("Created drip campaign '%s' for agent %s", name, agent_id)
    return DripCampaign(**row)


def get_campaigns(agent_id: UUID, active_only: bool = True) -> list[DripCampaign]:
    """Get campaigns for an agent."""
    query = "SELECT * FROM drip_campaigns WHERE agent_id = %s"
    params = [str(agent_id)]
    if active_only:
        query += " AND is_active = true"
    query += " ORDER BY created_at DESC"

    with get_db_connection() as conn:
        rows = conn.execute(query, params).fetchall()
    return [DripCampaign(**r) for r in rows]


def enroll_contact(
    agent_id: UUID,
    campaign_id: UUID,
    contact_id: UUID,
) -> DripEnrollment | None:
    """Enroll a contact in a drip campaign. Creates triggers for all steps."""
    with get_db_connection() as conn:
        # Check for existing active enrollment
        existing = conn.execute(
            """SELECT id FROM drip_enrollments
               WHERE campaign_id = %s AND contact_id = %s AND status = 'active'""",
            [str(campaign_id), str(contact_id)],
        ).fetchone()
        if existing:
            logger.info("Contact %s already enrolled in campaign %s", contact_id, campaign_id)
            return None

        # Get campaign
        campaign = conn.execute(
            "SELECT * FROM drip_campaigns WHERE id = %s AND agent_id = %s",
            [str(campaign_id), str(agent_id)],
        ).fetchone()
        if not campaign:
            return None

        # Create enrollment
        enrollment = conn.execute(
            """INSERT INTO drip_enrollments (agent_id, campaign_id, contact_id)
               VALUES (%s, %s, %s) RETURNING *""",
            [str(agent_id), str(campaign_id), str(contact_id)],
        ).fetchone()
        conn.commit()

    # Schedule triggers for each step
    steps = campaign["steps"] if isinstance(campaign["steps"], list) else json.loads(campaign["steps"])
    now = datetime.now(timezone.utc)

    from app.tools.triggers import create_trigger
    for step in steps:
        day_offset = step.get("day", 0)
        scheduled = now + timedelta(days=day_offset)
        create_trigger(
            agent_id=agent_id,
            entity_type="contact",
            entity_id=contact_id,
            trigger_type=f"drip_{campaign['name'].lower().replace(' ', '_')}",
            scheduled_at=scheduled,
            action_type=step.get("action_type", "send_message"),
            message_template=step.get("message"),
            autonomy_level="auto" if step.get("action_type") == "send_message" else "ask_agent",
            notes=f"Drip: {campaign['name']} (step {steps.index(step) + 1}/{len(steps)})",
        )

    logger.info("Enrolled contact %s in campaign '%s' (%d steps)",
                contact_id, campaign["name"], len(steps))
    return DripEnrollment(**enrollment)


def get_enrollments(
    agent_id: UUID,
    campaign_id: UUID | None = None,
    contact_id: UUID | None = None,
    status: str = "active",
) -> list[dict]:
    """Get enrollments with contact and campaign details."""
    conditions = ["e.agent_id = %s", "e.status = %s"]
    params = [str(agent_id), status]

    if campaign_id:
        conditions.append("e.campaign_id = %s")
        params.append(str(campaign_id))
    if contact_id:
        conditions.append("e.contact_id = %s")
        params.append(str(contact_id))

    where = " AND ".join(conditions)

    with get_db_connection() as conn:
        rows = conn.execute(
            f"""SELECT e.*, c.name as contact_name, d.name as campaign_name
                FROM drip_enrollments e
                JOIN contacts c ON c.id = e.contact_id
                JOIN drip_campaigns d ON d.id = e.campaign_id
                WHERE {where}
                ORDER BY e.enrolled_at DESC""",
            params,
        ).fetchall()

    return [dict(r) for r in rows]


def unenroll_contact(enrollment_id: UUID, agent_id: UUID) -> bool:
    """Remove a contact from a drip campaign."""
    with get_db_connection() as conn:
        result = conn.execute(
            """UPDATE drip_enrollments SET status = 'cancelled', completed_at = now()
               WHERE id = %s AND agent_id = %s AND status = 'active'
               RETURNING id""",
            [str(enrollment_id), str(agent_id)],
        ).fetchone()
        conn.commit()
    return result is not None


def seed_default_campaigns(agent_id: UUID) -> list[DripCampaign]:
    """Seed default campaign templates for a new agent."""
    campaigns = []
    for template in DEFAULT_CAMPAIGNS:
        campaign = create_campaign(
            agent_id=agent_id,
            name=template["name"],
            steps=template["steps"],
            description=template["description"],
            trigger_type=template["trigger_type"],
        )
        campaigns.append(campaign)
    return campaigns
