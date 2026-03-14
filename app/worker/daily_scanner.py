"""Daily scanner — morning evaluation of recurring rules, gap analysis, DOM alerts."""
import logging
from datetime import datetime, timezone, timedelta, time
from uuid import UUID

import psycopg

from app.db.connection import get_db_connection
from app.models.schemas import AgentConfig, Trigger
from app.tools.contacts import analyze_contact_gaps

logger = logging.getLogger(__name__)


def run_daily_scan():
    """Run the daily scan for all agents. Called once per morning."""
    agents = _get_all_active_agents()
    logger.info(f"Daily scan: processing {len(agents)} agents")

    # Process knowledge base expirations across all agents
    try:
        process_kb_expirations()
    except Exception as e:  # Broad catch: worker loop must survive transient errors
        logger.error(f"KB expiration processing failed: {e}")

    for agent in agents:
        try:
            scan_agent(agent)
        except Exception as e:  # Broad catch: worker loop must survive transient errors
            logger.error(f"Daily scan failed for agent {agent.id}: {e}")


def scan_agent(agent: AgentConfig) -> dict:
    """Run all daily checks for a single agent."""
    results = {
        "agent_id": str(agent.id),
        "gaps_found": 0,
        "dom_alerts": 0,
        "proactive_followups": 0,
    }

    # 1. Contact gap analysis → create follow-up triggers
    gaps = analyze_contact_gaps(agent.id)
    results["gaps_found"] = len(gaps)
    for gap in gaps:
        _create_gap_trigger(agent, gap)

    # 2. DOM alerts for aging listings
    dom_alerts = _check_dom_alerts(agent)
    results["dom_alerts"] = len(dom_alerts)
    for alert in dom_alerts:
        _create_dom_alert_trigger(agent, alert)

    # 3. Proactive follow-ups for leads going cold
    followups = _find_proactive_followups(agent)
    results["proactive_followups"] = len(followups)
    for followup in followups:
        _create_followup_trigger(agent, followup)

    logger.info(
        f"Agent {agent.name}: {results['gaps_found']} gaps, "
        f"{results['dom_alerts']} DOM alerts, "
        f"{results['proactive_followups']} proactive followups"
    )
    return results


def compile_morning_briefing(agent: AgentConfig) -> dict:
    """Compile the morning briefing for an agent (Step 33)."""
    now = datetime.now(timezone.utc)
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    today_end = today_start + timedelta(days=1)

    briefing = {
        "agent_name": agent.name,
        "date": now.strftime("%A, %B %d"),
        "showings_today": [],
        "triggers_today": [],
        "gaps": [],
        "new_leads": [],
        "dom_alerts": [],
    }

    with get_db_connection() as conn:
        # Today's showings
        showings = conn.execute(
            """SELECT s.*, c.name as contact_name, l.address
               FROM showings s
               JOIN contacts c ON s.contact_id = c.id
               JOIN listings l ON s.listing_id = l.id
               WHERE s.agent_id = %s
               AND s.start_time BETWEEN %s AND %s
               AND s.status IN ('confirmed', 'hold')
               ORDER BY s.start_time""",
            [str(agent.id), today_start, today_end],
        ).fetchall()
        briefing["showings_today"] = [
            {
                "time": s["start_time"].strftime("%I:%M %p"),
                "client": s["contact_name"],
                "address": s["address"],
                "status": s["status"],
            }
            for s in showings
        ]

        # Today's triggers
        triggers = conn.execute(
            """SELECT * FROM triggers
               WHERE agent_id = %s
               AND scheduled_at BETWEEN %s AND %s
               AND status = 'pending'
               ORDER BY scheduled_at""",
            [str(agent.id), today_start, today_end],
        ).fetchall()
        briefing["triggers_today"] = [
            {
                "type": t["trigger_type"],
                "message": t["message_template"] or t["trigger_type"],
                "time": t["scheduled_at"].strftime("%I:%M %p"),
            }
            for t in triggers
        ]

        # New leads (last 24h)
        new_leads = conn.execute(
            """SELECT name, phone, lifecycle_stage FROM contacts
               WHERE agent_id = %s AND created_at > %s
               ORDER BY created_at DESC""",
            [str(agent.id), now - timedelta(days=1)],
        ).fetchall()
        briefing["new_leads"] = [
            {"name": l["name"], "phone": l["phone"]}
            for l in new_leads
        ]

    # Gap analysis
    gaps = analyze_contact_gaps(agent.id)
    briefing["gaps"] = [
        {
            "name": g["contact"].name,
            "days": g["days_since_contact"],
            "action": g["suggested_action"],
        }
        for g in gaps[:5]
    ]

    # DOM alerts
    dom_alerts = _check_dom_alerts(agent)
    briefing["dom_alerts"] = [
        {"address": a["address"], "dom": a["dom"], "price": a["price"]}
        for a in dom_alerts
    ]

    return briefing


def format_briefing_text(briefing: dict) -> str:
    """Format a briefing dict into a push notification body."""
    lines = [f"Good morning, {briefing['agent_name']}! {briefing['date']}"]

    showings = briefing["showings_today"]
    if showings:
        lines.append(f"\n{len(showings)} showing(s) today:")
        for s in showings:
            lines.append(f"  {s['time']}: {s['client']} at {s['address']}")
    else:
        lines.append("\nNo showings today.")

    triggers = briefing["triggers_today"]
    if triggers:
        lines.append(f"\n{len(triggers)} task(s) today:")
        for t in triggers[:3]:
            lines.append(f"  - {t['message']}")

    gaps = briefing["gaps"]
    if gaps:
        lines.append(f"\n{len(gaps)} client(s) need attention:")
        for g in gaps[:3]:
            lines.append(f"  - {g['name']} ({g['days']}d, {g['action'].lower()})")

    new_leads = briefing["new_leads"]
    if new_leads:
        lines.append(f"\n{len(new_leads)} new lead(s):")
        for l in new_leads:
            lines.append(f"  - {l['name']} ({l['phone']})")

    dom_alerts = briefing["dom_alerts"]
    if dom_alerts:
        lines.append(f"\nDOM alerts:")
        for a in dom_alerts:
            lines.append(f"  - {a['address']}: {a['dom']} days, ${a['price']:,}")

    return "\n".join(lines)


def send_morning_briefing(agent: AgentConfig) -> None:
    """Compile and send the morning briefing push notification."""
    briefing = compile_morning_briefing(agent)
    text = format_briefing_text(briefing)

    try:
        from app.services.firebase_service import send_push_notification
        send_push_notification(
            agent_id=agent.id,
            tier="briefing",
            title=f"Morning Briefing — {briefing['date']}",
            body=text,
        )
    except Exception as e:  # Broad catch: Firebase SDK errors
        logger.error(f"Failed to send morning briefing to {agent.name}: {e}")


def compile_seller_report(agent: AgentConfig, listing_id: UUID) -> dict:
    """Compile a weekly seller activity report (Step 34)."""
    now = datetime.now(timezone.utc)
    week_ago = now - timedelta(days=7)

    report = {
        "listing": None,
        "period": f"{week_ago.strftime('%b %d')} - {now.strftime('%b %d')}",
        "showings_count": 0,
        "inquiries_count": 0,
        "feedback_summary": [],
        "dom": 0,
        "market_context": "",
    }

    with get_db_connection() as conn:
        # Get listing info
        listing = conn.execute(
            "SELECT * FROM listings WHERE id = %s AND agent_id = %s",
            [str(listing_id), str(agent.id)],
        ).fetchone()

        if not listing:
            return report

        report["listing"] = {
            "address": listing["address"],
            "price": listing["price"],
            "status": listing["status"],
        }

        if listing["list_date"]:
            report["dom"] = (now.date() - listing["list_date"]).days

        # Count showings this week
        showings = conn.execute(
            """SELECT COUNT(*) as cnt FROM showings
               WHERE listing_id = %s AND created_at > %s""",
            [str(listing_id), week_ago],
        ).fetchone()
        report["showings_count"] = showings["cnt"] if showings else 0

        # Get showing feedback
        feedback = conn.execute(
            """SELECT s.feedback, c.name FROM showings s
               JOIN contacts c ON s.contact_id = c.id
               WHERE s.listing_id = %s AND s.feedback IS NOT NULL
               AND s.created_at > %s""",
            [str(listing_id), week_ago],
        ).fetchall()
        report["feedback_summary"] = [
            {"client": f["name"], "feedback": f["feedback"]}
            for f in feedback
        ]

        # Count inquiries (messages mentioning the listing)
        inquiries = conn.execute(
            """SELECT COUNT(*) as cnt FROM messages m
               JOIN conversations c ON m.conversation_id = c.id
               WHERE c.agent_id = %s AND m.created_at > %s
               AND LOWER(m.body) LIKE LOWER(%s)""",
            [str(agent.id), week_ago, f"%{listing['address'][:20]}%"],
        ).fetchone()
        report["inquiries_count"] = inquiries["cnt"] if inquiries else 0

    return report


def format_seller_report(report: dict) -> str:
    """Format a seller report into readable text."""
    if not report["listing"]:
        return "Listing not found."

    listing = report["listing"]
    lines = [
        f"Weekly Activity Report: {listing['address']}",
        f"Period: {report['period']}",
        f"Status: {listing['status']} | DOM: {report['dom']} | Price: ${listing['price']:,}",
        f"\nShowings: {report['showings_count']} | Inquiries: {report['inquiries_count']}",
    ]

    if report["feedback_summary"]:
        lines.append("\nFeedback:")
        for f in report["feedback_summary"]:
            lines.append(f"  - {f['client']}: {f['feedback'][:100]}")

    return "\n".join(lines)


# ============================================================
# Knowledge Base Expiration Processing
# ============================================================

def process_kb_expirations() -> dict:
    """Process expired knowledge base embeddings for all agents.

    For agents with kb_expiration_policy='auto_remove': delete expired chunks.
    For agents with kb_expiration_policy='remind_only': log a warning.

    Returns summary stats.
    """
    results = {"auto_removed": 0, "remind_only": 0, "agents_processed": 0}

    with get_db_connection() as conn:
        # Find all expired embeddings grouped by agent
        expired = conn.execute(
            """SELECT DISTINCT e.agent_id, e.source_id, e.source_type, e.title,
                      a.kb_expiration_policy
               FROM embeddings e
               JOIN agents a ON e.agent_id = a.id
               WHERE e.expires_at IS NOT NULL AND e.expires_at < now()"""
        ).fetchall()

    if not expired:
        logger.info("KB expiration scan: no expired items found")
        return results

    # Group by agent for processing
    by_agent: dict[str, list[dict]] = {}
    for row in expired:
        aid = str(row["agent_id"])
        if aid not in by_agent:
            by_agent[aid] = []
        by_agent[aid].append(row)

    results["agents_processed"] = len(by_agent)

    for agent_id, items in by_agent.items():
        policy = items[0]["kb_expiration_policy"] or "remind_only"

        if policy == "auto_remove":
            with get_db_connection() as conn:
                for item in items:
                    conn.execute(
                        "DELETE FROM embeddings WHERE agent_id = %s AND source_id = %s",
                        [str(item["agent_id"]), str(item["source_id"])],
                    )
                    title = item["title"] or f"{item['source_type']}/{item['source_id']}"
                    logger.info(
                        f"KB auto-remove: deleted expired embeddings for '{title}' "
                        f"(agent {agent_id}, source_type={item['source_type']})"
                    )
                    results["auto_removed"] += 1
                conn.commit()
        else:
            # remind_only: just log (UI shows expired badge)
            for item in items:
                title = item["title"] or f"{item['source_type']}/{item['source_id']}"
                logger.warning(
                    f"KB expired (remind_only): '{title}' has expired "
                    f"(agent {agent_id}, source_type={item['source_type']})"
                )
                results["remind_only"] += 1

    logger.info(
        f"KB expiration scan complete: {results['auto_removed']} auto-removed, "
        f"{results['remind_only']} remind-only, {results['agents_processed']} agents"
    )
    return results


# ============================================================
# Helper functions
# ============================================================

def _get_all_active_agents() -> list[AgentConfig]:
    """Get all active agents from the database.

    Selects only the columns used by downstream scan functions rather than
    SELECT * — this avoids loading large JSONB blobs that aren't needed:
      - google_oauth, style_profile, vapi_assistant are excluded.

    Columns used by:
      - scan_agent / run_daily_scan: id, name, listing_rules
      - _check_dom_alerts:           id, listing_rules
      - _create_*_trigger helpers:   id
      - _find_proactive_followups:   id
      - send_morning_briefing:       id, name
      - AgentConfig required fields: id, name, email, phone, twilio_number
    """
    with get_db_connection() as conn:
        rows = conn.execute(
            """SELECT id, name, email, phone, timezone, twilio_number,
                      autonomy_rules, listing_rules, scheduling_prefs,
                      market, brokerage, system_prompt, google_review_link,
                      briefing_time, current_status, status_until,
                      voice_daily_cap_minutes, created_at, updated_at
               FROM agents"""
        ).fetchall()
    return [AgentConfig(**r) for r in rows]


def _check_dom_alerts(agent: AgentConfig) -> list[dict]:
    """Check for listings approaching DOM thresholds."""
    dom_rules = agent.listing_rules.get("dom_alert_days", [30, 60, 90])
    alerts = []

    with get_db_connection() as conn:
        rows = conn.execute(
            """SELECT * FROM listings
               WHERE agent_id = %s AND status = 'active' AND list_date IS NOT NULL""",
            [str(agent.id)],
        ).fetchall()

    now = datetime.now(timezone.utc).date()
    for row in rows:
        dom = (now - row["list_date"]).days
        for threshold in dom_rules:
            if dom == threshold:
                alerts.append({
                    "listing_id": row["id"],
                    "address": row["address"],
                    "price": row["price"],
                    "dom": dom,
                    "threshold": threshold,
                })
                break

    return alerts


def _find_proactive_followups(agent: AgentConfig) -> list[dict]:
    """Find new leads that haven't been contacted in 2+ days."""
    with get_db_connection() as conn:
        rows = conn.execute(
            """SELECT * FROM contacts
               WHERE agent_id = %s
               AND lifecycle_stage = 'new_lead'
               AND silent_mode = false
               AND last_contact_at < now() - interval '2 days'
               AND last_contact_at > now() - interval '5 days'""",
            [str(agent.id)],
        ).fetchall()

    return [
        {
            "contact_id": row["id"],
            "name": row["name"],
            "phone": row["phone"],
            "days_since": (datetime.now(timezone.utc) - row["last_contact_at"].replace(tzinfo=timezone.utc)).days
            if row["last_contact_at"] else 999,
        }
        for row in rows
    ]


def _create_gap_trigger(agent: AgentConfig, gap: dict) -> None:
    """Create a follow-up trigger for a contact gap."""
    from app.tools.triggers import create_trigger
    contact = gap["contact"]

    try:
        create_trigger(
            agent_id=agent.id,
            entity_type="contact",
            entity_id=contact.id,
            trigger_type="gap_follow_up",
            scheduled_at=datetime.now(timezone.utc) + timedelta(hours=2),
            action_type="notify_agent",
            message_template=f"{contact.name}: {gap['suggested_action']} ({gap['days_since_contact']}d gap)",
            autonomy_level="ask_agent",
        )
    except psycopg.Error as e:
        logger.error(f"Failed to create gap trigger for {contact.name}: {e}")


def _create_dom_alert_trigger(agent: AgentConfig, alert: dict) -> None:
    """Create a DOM alert trigger."""
    from app.tools.triggers import create_trigger

    try:
        create_trigger(
            agent_id=agent.id,
            entity_type="listing",
            entity_id=alert["listing_id"],
            trigger_type="dom_alert",
            scheduled_at=datetime.now(timezone.utc) + timedelta(hours=1),
            action_type="notify_agent",
            message_template=f"{alert['address']}: {alert['dom']} days on market at ${alert['price']:,}",
            autonomy_level="ask_agent",
        )
    except psycopg.Error as e:
        logger.error(f"Failed to create DOM alert: {e}")


def _create_followup_trigger(agent: AgentConfig, followup: dict) -> None:
    """Create a proactive follow-up trigger for a cooling lead."""
    from app.tools.triggers import create_trigger

    try:
        create_trigger(
            agent_id=agent.id,
            entity_type="contact",
            entity_id=followup["contact_id"],
            trigger_type="proactive_follow_up",
            scheduled_at=datetime.now(timezone.utc) + timedelta(hours=3),
            action_type="send_message",
            message_template=f"Hi {followup['name']}! Just checking in — still interested in finding a place?",
            autonomy_level="auto",
        )
    except psycopg.Error as e:
        logger.error(f"Failed to create proactive followup: {e}")
