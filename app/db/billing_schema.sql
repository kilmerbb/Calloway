-- Billing Schema — Stripe-backed subscription management
-- Run AFTER schema.sql. These tables extend the agents table.

-- ============================================================
-- subscriptions — one active subscription per agent
-- ============================================================
CREATE TABLE subscriptions (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    agent_id        UUID NOT NULL REFERENCES agents(id) UNIQUE,
    stripe_customer_id   TEXT NOT NULL,
    stripe_subscription_id TEXT,
    plan_tier       TEXT NOT NULL DEFAULT 'starter',   -- starter, professional, enterprise
    status          TEXT NOT NULL DEFAULT 'trialing',  -- trialing, active, past_due, canceled, paused
    trial_ends_at   TIMESTAMPTZ,
    current_period_start TIMESTAMPTZ,
    current_period_end   TIMESTAMPTZ,
    cancel_at_period_end BOOLEAN DEFAULT false,
    monthly_price_cents  INT NOT NULL DEFAULT 4900,    -- $49.00
    message_limit   INT NOT NULL DEFAULT 200,
    contact_limit   INT NOT NULL DEFAULT 50,
    created_at      TIMESTAMPTZ DEFAULT now(),
    updated_at      TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX idx_subscriptions_stripe_customer ON subscriptions(stripe_customer_id);
CREATE INDEX idx_subscriptions_status ON subscriptions(status);

-- ============================================================
-- invoices — synced from Stripe webhooks
-- ============================================================
CREATE TABLE invoices (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    agent_id        UUID NOT NULL REFERENCES agents(id),
    stripe_invoice_id TEXT NOT NULL UNIQUE,
    amount_cents    INT NOT NULL,
    status          TEXT NOT NULL DEFAULT 'draft',  -- draft, open, paid, void, uncollectible
    period_start    TIMESTAMPTZ,
    period_end      TIMESTAMPTZ,
    paid_at         TIMESTAMPTZ,
    invoice_url     TEXT,
    created_at      TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX idx_invoices_agent ON invoices(agent_id);

-- ============================================================
-- usage_overages — tracked when agent exceeds plan limits
-- ============================================================
CREATE TABLE usage_overages (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    agent_id        UUID NOT NULL REFERENCES agents(id),
    period_start    DATE NOT NULL,
    period_end      DATE NOT NULL,
    messages_used   INT NOT NULL DEFAULT 0,
    messages_limit  INT NOT NULL DEFAULT 200,
    overage_messages INT NOT NULL DEFAULT 0,
    overage_charge_cents INT NOT NULL DEFAULT 0,
    billed          BOOLEAN DEFAULT false,
    created_at      TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX idx_usage_overages_agent_period ON usage_overages(agent_id, period_start);

-- RLS policies for billing tables
ALTER TABLE subscriptions ENABLE ROW LEVEL SECURITY;
CREATE POLICY agent_isolation ON subscriptions
    FOR ALL USING (agent_id = current_setting('app.current_agent_id')::uuid);

ALTER TABLE invoices ENABLE ROW LEVEL SECURITY;
CREATE POLICY agent_isolation ON invoices
    FOR ALL USING (agent_id = current_setting('app.current_agent_id')::uuid);

ALTER TABLE usage_overages ENABLE ROW LEVEL SECURITY;
CREATE POLICY agent_isolation ON usage_overages
    FOR ALL USING (agent_id = current_setting('app.current_agent_id')::uuid);
