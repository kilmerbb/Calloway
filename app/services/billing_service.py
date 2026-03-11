"""Stripe billing service — subscription lifecycle management."""
import logging
from datetime import datetime, timezone
from uuid import UUID

from app.config import get_settings
from app.db.connection import get_db_connection

logger = logging.getLogger(__name__)

# Plan tier definitions
PLAN_TIERS = {
    "starter": {
        "name": "Starter",
        "price_cents": 4900,
        "message_limit": 200,
        "contact_limit": 50,
        "features": ["SMS channel", "50 contacts", "200 messages/month", "Template responses"],
    },
    "professional": {
        "name": "Professional",
        "price_cents": 9900,
        "message_limit": 600,
        "contact_limit": 200,
        "features": ["SMS + Voice", "200 contacts", "600 messages/month", "AI reasoning", "Daily briefings"],
    },
    "enterprise": {
        "name": "Enterprise",
        "price_cents": 19900,
        "message_limit": 1500,
        "contact_limit": 999999,
        "features": ["All channels", "Unlimited contacts", "1,500 messages/month", "Full autonomy", "Seller ops", "Priority support"],
    },
}

TRIAL_DAYS = 14


def _get_stripe():
    """Lazy-import stripe to avoid import errors when not installed."""
    import stripe
    settings = get_settings()
    stripe.api_key = settings.STRIPE_SECRET_KEY
    return stripe


# ── Customer & subscription creation ─────────────────────────

def create_customer_and_subscription(
    agent_id: UUID, agent_name: str, agent_email: str, plan_tier: str = "starter"
) -> dict:
    """Create a Stripe customer with a trial subscription."""
    stripe = _get_stripe()
    tier = PLAN_TIERS[plan_tier]

    # Create Stripe customer
    customer = stripe.Customer.create(
        name=agent_name,
        email=agent_email,
        metadata={"agent_id": str(agent_id), "plan_tier": plan_tier},
    )

    # Create subscription with trial
    subscription = stripe.Subscription.create(
        customer=customer.id,
        items=[{"price_data": {
            "unit_amount": tier["price_cents"],
            "currency": "usd",
            "recurring": {"interval": "month"},
            "product_data": {"name": f"Calloway {tier['name']}"},
        }}],
        trial_period_days=TRIAL_DAYS,
        metadata={"agent_id": str(agent_id)},
    )

    # Store in database
    with get_db_connection() as conn:
        conn.execute(
            """INSERT INTO subscriptions
               (agent_id, stripe_customer_id, stripe_subscription_id,
                plan_tier, status, trial_ends_at,
                current_period_start, current_period_end,
                monthly_price_cents, message_limit, contact_limit)
               VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
               ON CONFLICT (agent_id) DO UPDATE SET
                stripe_customer_id = EXCLUDED.stripe_customer_id,
                stripe_subscription_id = EXCLUDED.stripe_subscription_id,
                plan_tier = EXCLUDED.plan_tier,
                status = EXCLUDED.status,
                trial_ends_at = EXCLUDED.trial_ends_at,
                current_period_start = EXCLUDED.current_period_start,
                current_period_end = EXCLUDED.current_period_end,
                monthly_price_cents = EXCLUDED.monthly_price_cents,
                message_limit = EXCLUDED.message_limit,
                contact_limit = EXCLUDED.contact_limit,
                updated_at = now()""",
            [
                str(agent_id), customer.id, subscription.id,
                plan_tier, "trialing",
                datetime.fromtimestamp(subscription.trial_end, tz=timezone.utc) if subscription.trial_end else None,
                datetime.fromtimestamp(subscription.current_period_start, tz=timezone.utc),
                datetime.fromtimestamp(subscription.current_period_end, tz=timezone.utc),
                tier["price_cents"], tier["message_limit"], tier["contact_limit"],
            ],
        )
        conn.commit()

    logger.info(f"Created subscription for agent {agent_id}: {plan_tier} (trial)")
    return {
        "customer_id": customer.id,
        "subscription_id": subscription.id,
        "plan_tier": plan_tier,
        "status": "trialing",
    }


# ── Subscription management ──────────────────────────────────

def change_plan(agent_id: UUID, new_tier: str) -> dict:
    """Change an agent's subscription plan tier."""
    stripe = _get_stripe()
    tier = PLAN_TIERS[new_tier]

    with get_db_connection() as conn:
        sub = conn.execute(
            "SELECT stripe_subscription_id FROM subscriptions WHERE agent_id = %s",
            [str(agent_id)],
        ).fetchone()

    if not sub or not sub["stripe_subscription_id"]:
        raise ValueError("No active subscription found")

    # Update Stripe subscription
    subscription = stripe.Subscription.retrieve(sub["stripe_subscription_id"])
    stripe.Subscription.modify(
        sub["stripe_subscription_id"],
        items=[{
            "id": subscription["items"]["data"][0]["id"],
            "price_data": {
                "unit_amount": tier["price_cents"],
                "currency": "usd",
                "recurring": {"interval": "month"},
                "product_data": {"name": f"Calloway {tier['name']}"},
            },
        }],
        proration_behavior="create_prorations",
        metadata={"plan_tier": new_tier},
    )

    # Update database
    with get_db_connection() as conn:
        conn.execute(
            """UPDATE subscriptions
               SET plan_tier = %s, monthly_price_cents = %s,
                   message_limit = %s, contact_limit = %s, updated_at = now()
               WHERE agent_id = %s""",
            [new_tier, tier["price_cents"], tier["message_limit"], tier["contact_limit"], str(agent_id)],
        )
        conn.commit()

    logger.info(f"Changed plan for agent {agent_id} to {new_tier}")
    return {"plan_tier": new_tier, "price_cents": tier["price_cents"]}


def cancel_subscription(agent_id: UUID, at_period_end: bool = True) -> dict:
    """Cancel an agent's subscription."""
    stripe = _get_stripe()

    with get_db_connection() as conn:
        sub = conn.execute(
            "SELECT stripe_subscription_id FROM subscriptions WHERE agent_id = %s",
            [str(agent_id)],
        ).fetchone()

    if not sub or not sub["stripe_subscription_id"]:
        raise ValueError("No active subscription found")

    if at_period_end:
        stripe.Subscription.modify(
            sub["stripe_subscription_id"],
            cancel_at_period_end=True,
        )
        new_status = "active"  # Still active until period end
    else:
        stripe.Subscription.cancel(sub["stripe_subscription_id"])
        new_status = "canceled"

    with get_db_connection() as conn:
        conn.execute(
            """UPDATE subscriptions
               SET status = %s, cancel_at_period_end = %s, updated_at = now()
               WHERE agent_id = %s""",
            [new_status, at_period_end, str(agent_id)],
        )
        conn.commit()

    logger.info(f"Cancelled subscription for agent {agent_id} (at_period_end={at_period_end})")
    return {"status": new_status, "cancel_at_period_end": at_period_end}


# ── Webhook handlers ─────────────────────────────────────────

def handle_subscription_updated(event_data: dict) -> None:
    """Handle Stripe subscription.updated webhook."""
    sub = event_data["object"]
    agent_id = sub.get("metadata", {}).get("agent_id")
    if not agent_id:
        logger.warning(f"Subscription updated without agent_id metadata: {sub['id']}")
        return

    status = sub["status"]
    with get_db_connection() as conn:
        conn.execute(
            """UPDATE subscriptions
               SET status = %s,
                   current_period_start = %s,
                   current_period_end = %s,
                   cancel_at_period_end = %s,
                   updated_at = now()
               WHERE agent_id = %s""",
            [
                status,
                datetime.fromtimestamp(sub["current_period_start"], tz=timezone.utc),
                datetime.fromtimestamp(sub["current_period_end"], tz=timezone.utc),
                sub.get("cancel_at_period_end", False),
                agent_id,
            ],
        )
        conn.commit()

    logger.info(f"Subscription updated for agent {agent_id}: status={status}")


def handle_invoice_paid(event_data: dict) -> None:
    """Handle Stripe invoice.paid webhook."""
    invoice = event_data["object"]
    customer_id = invoice["customer"]

    with get_db_connection() as conn:
        sub = conn.execute(
            "SELECT agent_id FROM subscriptions WHERE stripe_customer_id = %s",
            [customer_id],
        ).fetchone()

    if not sub:
        logger.warning(f"Invoice paid for unknown customer: {customer_id}")
        return

    agent_id = sub["agent_id"]
    with get_db_connection() as conn:
        conn.execute(
            """INSERT INTO invoices
               (agent_id, stripe_invoice_id, amount_cents, status,
                period_start, period_end, paid_at, invoice_url)
               VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
               ON CONFLICT (stripe_invoice_id) DO UPDATE SET
                status = EXCLUDED.status, paid_at = EXCLUDED.paid_at""",
            [
                str(agent_id), invoice["id"], invoice["amount_paid"], "paid",
                datetime.fromtimestamp(invoice["period_start"], tz=timezone.utc) if invoice.get("period_start") else None,
                datetime.fromtimestamp(invoice["period_end"], tz=timezone.utc) if invoice.get("period_end") else None,
                datetime.now(timezone.utc),
                invoice.get("hosted_invoice_url"),
            ],
        )
        conn.commit()

    logger.info(f"Invoice paid for agent {agent_id}: ${invoice['amount_paid'] / 100:.2f}")


def handle_invoice_payment_failed(event_data: dict) -> None:
    """Handle Stripe invoice.payment_failed webhook."""
    invoice = event_data["object"]
    customer_id = invoice["customer"]

    with get_db_connection() as conn:
        sub = conn.execute(
            "SELECT agent_id FROM subscriptions WHERE stripe_customer_id = %s",
            [customer_id],
        ).fetchone()

    if not sub:
        return

    agent_id = sub["agent_id"]
    with get_db_connection() as conn:
        conn.execute(
            "UPDATE subscriptions SET status = 'past_due', updated_at = now() WHERE agent_id = %s",
            [str(agent_id)],
        )
        conn.commit()

    logger.warning(f"Payment failed for agent {agent_id}")


# ── Usage tracking ────────────────────────────────────────────

def get_subscription(agent_id: UUID) -> dict | None:
    """Get the subscription record for an agent."""
    with get_db_connection() as conn:
        return conn.execute(
            "SELECT * FROM subscriptions WHERE agent_id = %s",
            [str(agent_id)],
        ).fetchone()


def check_message_quota(agent_id: UUID) -> dict:
    """Check if an agent is within their message quota for the current period."""
    with get_db_connection() as conn:
        sub = conn.execute(
            "SELECT message_limit, current_period_start, current_period_end, status FROM subscriptions WHERE agent_id = %s",
            [str(agent_id)],
        ).fetchone()

    if not sub:
        # No subscription — allow unlimited (pre-billing, or operator override)
        return {"allowed": True, "used": 0, "limit": 999999, "remaining": 999999}

    if sub["status"] in ("canceled", "paused"):
        return {"allowed": False, "used": 0, "limit": 0, "remaining": 0, "reason": "subscription_inactive"}

    # Count messages in current billing period
    with get_db_connection() as conn:
        row = conn.execute(
            """SELECT COALESCE(SUM(messages_sent), 0) as total
               FROM usage_metrics
               WHERE agent_id = %s AND date >= %s AND date <= %s""",
            [str(agent_id), sub["current_period_start"], sub["current_period_end"]],
        ).fetchone()

    used = row["total"] if row else 0
    limit = sub["message_limit"]
    remaining = max(0, limit - used)

    return {
        "allowed": remaining > 0 or sub["status"] == "trialing",
        "used": used,
        "limit": limit,
        "remaining": remaining,
        "status": sub["status"],
    }


def get_billing_summary() -> list[dict]:
    """Get billing summary for all agents (operator console)."""
    with get_db_connection() as conn:
        return conn.execute(
            """SELECT s.*, a.name as agent_name, a.email as agent_email,
                      (SELECT COALESCE(SUM(messages_sent), 0) FROM usage_metrics
                       WHERE agent_id = s.agent_id
                       AND date >= s.current_period_start
                       AND date <= COALESCE(s.current_period_end, CURRENT_DATE)) as messages_used
               FROM subscriptions s
               JOIN agents a ON a.id = s.agent_id
               ORDER BY s.created_at DESC""",
        ).fetchall()


def get_agent_invoices(agent_id: UUID, limit: int = 12) -> list[dict]:
    """Get recent invoices for an agent."""
    with get_db_connection() as conn:
        return conn.execute(
            """SELECT * FROM invoices
               WHERE agent_id = %s
               ORDER BY created_at DESC
               LIMIT %s""",
            [str(agent_id), limit],
        ).fetchall()
