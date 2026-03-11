"""Billing webhooks and API — Stripe integration."""
import logging

from fastapi import APIRouter, HTTPException, Request, Response

from app.config import get_settings

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/billing", tags=["billing"])


@router.post("/webhooks/stripe")
async def stripe_webhook(request: Request):
    """Handle Stripe webhook events."""
    import stripe
    settings = get_settings()

    payload = await request.body()
    sig_header = request.headers.get("stripe-signature", "")

    if not settings.STRIPE_WEBHOOK_SECRET:
        logger.error("STRIPE_WEBHOOK_SECRET not configured — rejecting webhook")
        raise HTTPException(status_code=500, detail="Stripe webhook secret not configured")
    else:
        try:
            event = stripe.Webhook.construct_event(
                payload, sig_header, settings.STRIPE_WEBHOOK_SECRET,
            )
        except (ValueError, stripe.error.SignatureVerificationError) as e:
            logger.warning(f"Stripe webhook signature validation failed: {e}")
            return Response(status_code=400)

    event_type = event.get("type", "")
    event_data = event.get("data", {})

    from app.services.billing_service import (
        handle_subscription_updated,
        handle_invoice_paid,
        handle_invoice_payment_failed,
    )

    handlers = {
        "customer.subscription.updated": handle_subscription_updated,
        "customer.subscription.deleted": handle_subscription_updated,
        "invoice.paid": handle_invoice_paid,
        "invoice.payment_failed": handle_invoice_payment_failed,
    }

    handler = handlers.get(event_type)
    if handler:
        try:
            handler(event_data)
            logger.info(f"Handled Stripe event: {event_type}")
        except Exception as e:
            logger.error(f"Error handling Stripe event {event_type}: {e}", exc_info=True)
    else:
        logger.debug(f"Unhandled Stripe event type: {event_type}")

    return {"status": "ok"}
