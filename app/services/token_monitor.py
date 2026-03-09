"""Token monitor — tracks LLM usage and alerts on budget thresholds."""
import logging
from datetime import date
from uuid import UUID

from app.db.connection import get_db_connection

logger = logging.getLogger(__name__)

# Default daily budget in cents (can be overridden per agent)
DEFAULT_DAILY_BUDGET_CENTS = 500  # $5/day
DEFAULT_MONTHLY_BUDGET_CENTS = 10000  # $100/month

ALERT_THRESHOLDS = [0.75, 0.90, 1.0]  # 75%, 90%, 100%


def check_budget(agent_id: UUID) -> dict:
    """Check current usage against budget thresholds."""
    today = date.today()

    with get_db_connection() as conn:
        # Daily usage
        daily = conn.execute(
            """SELECT COALESCE(SUM(llm_cost_cents), 0) as cost,
                      COALESCE(SUM(llm_tokens_used), 0) as tokens,
                      COALESCE(SUM(llm_calls), 0) as calls
               FROM usage_metrics
               WHERE agent_id = %s AND date = %s""",
            [str(agent_id), today],
        ).fetchone()

        # Monthly usage
        monthly = conn.execute(
            """SELECT COALESCE(SUM(llm_cost_cents), 0) as cost,
                      COALESCE(SUM(llm_tokens_used), 0) as tokens,
                      COALESCE(SUM(llm_calls), 0) as calls
               FROM usage_metrics
               WHERE agent_id = %s AND date >= date_trunc('month', CURRENT_DATE)""",
            [str(agent_id)],
        ).fetchone()

    daily_cost = daily["cost"]
    monthly_cost = monthly["cost"]

    daily_pct = daily_cost / DEFAULT_DAILY_BUDGET_CENTS if DEFAULT_DAILY_BUDGET_CENTS else 0
    monthly_pct = monthly_cost / DEFAULT_MONTHLY_BUDGET_CENTS if DEFAULT_MONTHLY_BUDGET_CENTS else 0

    alerts = []
    for threshold in ALERT_THRESHOLDS:
        if daily_pct >= threshold:
            alerts.append({
                "type": "daily_budget",
                "threshold": threshold,
                "current": daily_cost,
                "budget": DEFAULT_DAILY_BUDGET_CENTS,
                "pct": round(daily_pct * 100, 1),
            })
            break  # Only the highest alert

    for threshold in ALERT_THRESHOLDS:
        if monthly_pct >= threshold:
            alerts.append({
                "type": "monthly_budget",
                "threshold": threshold,
                "current": monthly_cost,
                "budget": DEFAULT_MONTHLY_BUDGET_CENTS,
                "pct": round(monthly_pct * 100, 1),
            })
            break

    return {
        "agent_id": str(agent_id),
        "daily": {
            "cost_cents": daily_cost,
            "tokens": daily["tokens"],
            "calls": daily["calls"],
            "budget_cents": DEFAULT_DAILY_BUDGET_CENTS,
            "pct_used": round(daily_pct * 100, 1),
        },
        "monthly": {
            "cost_cents": monthly_cost,
            "tokens": monthly["tokens"],
            "calls": monthly["calls"],
            "budget_cents": DEFAULT_MONTHLY_BUDGET_CENTS,
            "pct_used": round(monthly_pct * 100, 1),
        },
        "alerts": alerts,
        "should_throttle": daily_pct >= 1.0,
    }


def get_usage_summary(agent_id: UUID, days: int = 30) -> dict:
    """Get usage summary for the last N days."""
    with get_db_connection() as conn:
        rows = conn.execute(
            """SELECT date, messages_sent, messages_received, llm_calls,
                      llm_tokens_used, llm_cost_cents, voice_minutes,
                      showings_booked, triggers_fired
               FROM usage_metrics
               WHERE agent_id = %s AND date >= CURRENT_DATE - %s
               ORDER BY date DESC""",
            [str(agent_id), days],
        ).fetchall()

    if not rows:
        return {
            "agent_id": str(agent_id),
            "period_days": days,
            "total_messages_sent": 0,
            "total_messages_received": 0,
            "total_llm_calls": 0,
            "total_tokens": 0,
            "total_cost_cents": 0,
            "avg_daily_cost_cents": 0,
            "daily_breakdown": [],
        }

    total_sent = sum(r["messages_sent"] for r in rows)
    total_received = sum(r["messages_received"] for r in rows)
    total_calls = sum(r["llm_calls"] for r in rows)
    total_tokens = sum(r["llm_tokens_used"] for r in rows)
    total_cost = sum(r["llm_cost_cents"] for r in rows)
    total_showings = sum(r["showings_booked"] for r in rows)

    return {
        "agent_id": str(agent_id),
        "period_days": days,
        "total_messages_sent": total_sent,
        "total_messages_received": total_received,
        "total_llm_calls": total_calls,
        "total_tokens": total_tokens,
        "total_cost_cents": total_cost,
        "total_cost_dollars": round(total_cost / 100, 2),
        "avg_daily_cost_cents": round(total_cost / max(len(rows), 1)),
        "total_showings_booked": total_showings,
        "daily_breakdown": [
            {
                "date": str(r["date"]),
                "messages": r["messages_sent"] + r["messages_received"],
                "llm_calls": r["llm_calls"],
                "cost_cents": r["llm_cost_cents"],
            }
            for r in rows[:7]  # Last 7 days detail
        ],
    }
