"""Step 49: Agent onboarding flow — create agent, validate config, seed data."""
import logging
from uuid import UUID
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.db.connection import get_db_connection

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/onboarding", tags=["onboarding"])


class OnboardingRequest(BaseModel):
    name: str
    email: str
    phone: str
    twilio_number: str
    brokerage: str | None = None
    market: str | None = None
    timezone: str = "America/New_York"
    style_tone: str = "professional"
    autonomy_level: str = "moderate"


class OnboardingResponse(BaseModel):
    agent_id: str
    status: str
    checklist: list[dict]


@router.post("/agent", response_model=OnboardingResponse)
async def onboard_agent(req: OnboardingRequest):
    """Create a new agent and return onboarding checklist."""
    try:
        with get_db_connection() as conn:
            # Check for duplicate
            existing = conn.execute(
                "SELECT id FROM agents WHERE phone = %s OR twilio_number = %s",
                [req.phone, req.twilio_number],
            ).fetchone()

            if existing:
                raise HTTPException(
                    status_code=409,
                    detail="Agent with this phone or Twilio number already exists",
                )

            import json
            row = conn.execute(
                """INSERT INTO agents (name, email, phone, twilio_number, brokerage, market,
                    timezone, style_profile, autonomy_rules, scheduling_prefs, listing_rules)
                   VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                   RETURNING id""",
                [
                    req.name, req.email, req.phone, req.twilio_number,
                    req.brokerage, req.market, req.timezone,
                    json.dumps({"tone": req.style_tone}),
                    json.dumps({"level": req.autonomy_level}),
                    json.dumps({"default_duration": 60, "buffer_minutes": 15}),
                    json.dumps({"dom_alert_days": [30, 60, 90]}),
                ],
            ).fetchone()
            conn.commit()

        agent_id = str(row["id"])

        # Build checklist
        checklist = _build_checklist(req)

        logger.info(f"Onboarded agent: {req.name} ({agent_id})")
        return OnboardingResponse(
            agent_id=agent_id,
            status="created",
            checklist=checklist,
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Onboarding failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/checklist/{agent_id}")
async def get_checklist(agent_id: str):
    """Get onboarding progress for an agent."""
    try:
        with get_db_connection() as conn:
            agent = conn.execute(
                "SELECT * FROM agents WHERE id = %s", [agent_id]
            ).fetchone()

            if not agent:
                raise HTTPException(status_code=404, detail="Agent not found")

            contacts = conn.execute(
                "SELECT COUNT(*) as cnt FROM contacts WHERE agent_id = %s",
                [agent_id],
            ).fetchone()

            listings = conn.execute(
                "SELECT COUNT(*) as cnt FROM listings WHERE agent_id = %s",
                [agent_id],
            ).fetchone()

        items = [
            {"step": "account_created", "label": "Account created", "done": True},
            {"step": "twilio_configured", "label": "Twilio number linked",
             "done": bool(agent["twilio_number"])},
            {"step": "contacts_imported", "label": "Import contacts (min 1)",
             "done": contacts["cnt"] > 0},
            {"step": "listing_added", "label": "Add first listing",
             "done": listings["cnt"] > 0},
            {"step": "google_connected", "label": "Connect Google Calendar",
             "done": bool(agent.get("google_oauth"))},
            {"step": "style_configured", "label": "Set communication style",
             "done": bool(agent.get("style_profile"))},
            {"step": "test_message", "label": "Send test message",
             "done": False},  # Can't auto-check
        ]

        completed = sum(1 for i in items if i["done"])
        return {
            "agent_id": agent_id,
            "progress": f"{completed}/{len(items)}",
            "pct": round(completed / len(items) * 100),
            "items": items,
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


def _build_checklist(req: OnboardingRequest) -> list[dict]:
    """Build initial onboarding checklist."""
    return [
        {"step": "account_created", "label": "Account created", "done": True},
        {"step": "twilio_configured", "label": "Twilio number linked",
         "done": bool(req.twilio_number)},
        {"step": "contacts_imported", "label": "Import your contacts",
         "done": False},
        {"step": "listing_added", "label": "Add your first listing",
         "done": False},
        {"step": "google_connected", "label": "Connect Google Calendar",
         "done": False},
        {"step": "style_configured", "label": "Set communication style",
         "done": bool(req.style_tone)},
        {"step": "test_message", "label": "Send a test message",
         "done": False},
    ]
