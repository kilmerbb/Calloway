-- Solo Realtor AI Database Schema
-- All 12 tables with indexes and RLS policies

-- Enable pgvector extension
CREATE EXTENSION IF NOT EXISTS vector;

-- ============================================================
-- 1. agents
-- ============================================================
CREATE TABLE agents (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name            TEXT NOT NULL,
    email           TEXT NOT NULL,
    phone           TEXT NOT NULL,
    brokerage       TEXT,
    market          TEXT,
    timezone        TEXT DEFAULT 'America/New_York',
    twilio_number   TEXT NOT NULL,
    google_oauth    JSONB,
    vapi_assistant  TEXT,
    scheduling_prefs JSONB NOT NULL DEFAULT '{}',
    style_profile   JSONB NOT NULL DEFAULT '{}',
    autonomy_rules  JSONB NOT NULL DEFAULT '{}',
    listing_rules   JSONB NOT NULL DEFAULT '{}',
    system_prompt   TEXT,
    google_review_link TEXT,
    briefing_time   TIME DEFAULT '07:30',
    current_status  TEXT DEFAULT 'available',
    status_until    TIMESTAMPTZ,
    voice_daily_cap_minutes INT DEFAULT 30,
    kb_expiration_policy TEXT DEFAULT 'remind_only',
    kb_default_ttl_days INTEGER,
    created_at      TIMESTAMPTZ DEFAULT now(),
    updated_at      TIMESTAMPTZ DEFAULT now()
);

-- ============================================================
-- 2. contacts
-- ============================================================
CREATE TABLE contacts (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    agent_id        UUID NOT NULL REFERENCES agents(id),
    name            TEXT NOT NULL,
    phone           TEXT NOT NULL,
    email           TEXT,
    role            TEXT NOT NULL DEFAULT 'lead',
    lifecycle_stage TEXT NOT NULL DEFAULT 'new_lead',
    linked_listing_id UUID,
    preferences     JSONB DEFAULT '{}',
    notes           TEXT,
    last_contact_at TIMESTAMPTZ,
    silent_mode     BOOLEAN DEFAULT false,
    consent_status  TEXT DEFAULT 'pending',
    consent_granted_at TIMESTAMPTZ,
    consent_revoked_at TIMESTAMPTZ,
    consent_method  TEXT,
    consent_message TEXT,
    consent_response TEXT,
    lead_source     TEXT,
    language_detected TEXT DEFAULT 'en',
    interaction_count INT DEFAULT 0,
    created_at      TIMESTAMPTZ DEFAULT now(),
    updated_at      TIMESTAMPTZ DEFAULT now()
);

CREATE UNIQUE INDEX idx_contacts_agent_phone ON contacts(agent_id, phone);
CREATE INDEX idx_contacts_agent_lifecycle ON contacts(agent_id, lifecycle_stage);
CREATE INDEX idx_contacts_agent_last_contact ON contacts(agent_id, last_contact_at);
CREATE INDEX idx_contacts_agent_email ON contacts(agent_id, email) WHERE email IS NOT NULL;
CREATE INDEX idx_contacts_lead_source ON contacts(agent_id, lead_source) WHERE lead_source IS NOT NULL;

-- ============================================================
-- 2A. consent_log
-- ============================================================
CREATE TABLE consent_log (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    agent_id        UUID NOT NULL REFERENCES agents(id),
    contact_id      UUID NOT NULL REFERENCES contacts(id),
    event_type      TEXT NOT NULL,
    message_text    TEXT,
    response_text   TEXT,
    created_at      TIMESTAMPTZ DEFAULT now()
);

ALTER TABLE consent_log ENABLE ROW LEVEL SECURITY;
CREATE POLICY agent_isolation ON consent_log
    FOR ALL USING (agent_id = current_setting('app.current_agent_id')::uuid);

-- ============================================================
-- 3. lead_preferences
-- ============================================================
CREATE TABLE lead_preferences (
    contact_id      UUID PRIMARY KEY REFERENCES contacts(id) ON DELETE CASCADE,
    areas           TEXT[],
    timeline        TEXT,
    preapproved     BOOLEAN,
    property_type   TEXT,
    bedrooms_min    INT,
    bathrooms_min   NUMERIC(3,1),
    price_min       INT,
    price_max       INT
);

-- ============================================================
-- 4. listings
-- ============================================================
CREATE TABLE listings (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    agent_id        UUID NOT NULL REFERENCES agents(id),
    address         TEXT NOT NULL,
    price           INT NOT NULL,
    beds            INT,
    baths           NUMERIC(3,1),
    sqft            INT,
    hoa             INT,
    features        JSONB DEFAULT '[]',
    showing_instructions TEXT,
    lockbox         TEXT,
    access_rules    JSONB DEFAULT '{}',
    open_house_dates JSONB DEFAULT '[]',
    list_date       DATE,
    status          TEXT DEFAULT 'active',
    notes           TEXT,
    last_updated_at TIMESTAMPTZ DEFAULT now(),
    created_at      TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX idx_listings_agent_status ON listings(agent_id, status);

-- ============================================================
-- 5. conversations
-- ============================================================
CREATE TABLE conversations (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    agent_id        UUID NOT NULL REFERENCES agents(id),
    contact_id      UUID REFERENCES contacts(id),
    channel         TEXT NOT NULL,
    stage           TEXT DEFAULT 'open',
    active_handler  TEXT,
    last_message_at TIMESTAMPTZ,
    created_at      TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX idx_conversations_agent_contact ON conversations(agent_id, contact_id);
CREATE INDEX idx_conversations_last_message_at ON conversations(last_message_at DESC NULLS LAST);
CREATE INDEX idx_conversations_agent_last_message ON conversations(agent_id, last_message_at DESC NULLS LAST);

-- ============================================================
-- 6. messages
-- ============================================================
CREATE TABLE messages (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    agent_id        UUID NOT NULL REFERENCES agents(id),
    conversation_id UUID NOT NULL REFERENCES conversations(id),
    sender_type     TEXT NOT NULL,
    body            TEXT NOT NULL,
    intent          TEXT,
    ai_generated    BOOLEAN DEFAULT false,
    model_used      TEXT,
    tokens_used     INT,
    provider_message_id TEXT,
    delivery_status TEXT DEFAULT 'pending',
    delivered_at    TIMESTAMPTZ,
    failure_reason  TEXT,
    feedback_score  INT,
    created_at      TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX idx_messages_conversation_created ON messages(conversation_id, created_at);
CREATE INDEX idx_messages_agent_created ON messages(agent_id, created_at);
CREATE INDEX idx_messages_provider_id ON messages(provider_message_id) WHERE provider_message_id IS NOT NULL;
CREATE INDEX idx_messages_delivery_status ON messages(agent_id, delivery_status) WHERE delivery_status IN ('failed', 'undelivered');

-- ============================================================
-- 7. showings
-- ============================================================
CREATE TABLE showings (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    agent_id        UUID NOT NULL REFERENCES agents(id),
    contact_id      UUID NOT NULL REFERENCES contacts(id),
    listing_id      UUID NOT NULL REFERENCES listings(id),
    start_time      TIMESTAMPTZ NOT NULL,
    end_time        TIMESTAMPTZ NOT NULL,
    status          TEXT DEFAULT 'hold',
    hold_expires_at TIMESTAMPTZ,
    calendar_event_id TEXT,
    requesting_agent_id UUID,
    feedback        TEXT,
    created_at      TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX idx_showings_agent_start ON showings(agent_id, start_time);
CREATE INDEX idx_showings_listing_status ON showings(listing_id, status);

-- ============================================================
-- 8. triggers
-- ============================================================
CREATE TABLE triggers (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    agent_id        UUID NOT NULL REFERENCES agents(id),
    entity_type     TEXT NOT NULL,
    entity_id       UUID NOT NULL,
    trigger_type    TEXT NOT NULL,
    scheduled_at    TIMESTAMPTZ NOT NULL,
    recurrence      TEXT,
    action_type     TEXT NOT NULL,
    message_template TEXT,
    autonomy_level  TEXT DEFAULT 'ask_agent',
    status          TEXT DEFAULT 'pending',
    notes           TEXT,
    created_at      TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX idx_triggers_status_scheduled ON triggers(status, scheduled_at);
CREATE INDEX idx_triggers_status_agent_scheduled ON triggers(status, agent_id, scheduled_at);
CREATE INDEX idx_triggers_agent_entity ON triggers(agent_id, entity_type, entity_id);

-- ============================================================
-- 8A. transactions
-- ============================================================
CREATE TABLE transactions (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    agent_id        UUID NOT NULL REFERENCES agents(id),
    contact_id      UUID NOT NULL REFERENCES contacts(id),
    listing_id      UUID REFERENCES listings(id),
    transaction_type TEXT NOT NULL DEFAULT 'purchase',
    status          TEXT NOT NULL DEFAULT 'pending_offer',
    offer_price     INT,
    final_price     INT,
    offer_date      DATE,
    contract_date   DATE,
    closing_date    DATE,
    inspection_date DATE,
    appraisal_date  DATE,
    financing_deadline DATE,
    earnest_money   INT,
    commission_pct  NUMERIC(4,2),
    notes           TEXT,
    created_at      TIMESTAMPTZ DEFAULT now(),
    updated_at      TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX idx_transactions_agent_status ON transactions(agent_id, status);
CREATE INDEX idx_transactions_contact ON transactions(contact_id);
CREATE INDEX idx_transactions_closing ON transactions(closing_date) WHERE status NOT IN ('closed', 'fell_through');

-- ============================================================
-- 8B. drip_campaigns
-- ============================================================
CREATE TABLE drip_campaigns (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    agent_id        UUID NOT NULL REFERENCES agents(id),
    name            TEXT NOT NULL,
    description     TEXT,
    trigger_type    TEXT NOT NULL DEFAULT 'nurture',
    steps           JSONB NOT NULL DEFAULT '[]',
    is_active       BOOLEAN DEFAULT true,
    created_at      TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX idx_drip_campaigns_agent ON drip_campaigns(agent_id, is_active);

-- ============================================================
-- 8C. drip_enrollments
-- ============================================================
CREATE TABLE drip_enrollments (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    agent_id        UUID NOT NULL REFERENCES agents(id),
    campaign_id     UUID NOT NULL REFERENCES drip_campaigns(id),
    contact_id      UUID NOT NULL REFERENCES contacts(id),
    current_step    INT DEFAULT 0,
    status          TEXT DEFAULT 'active',
    enrolled_at     TIMESTAMPTZ DEFAULT now(),
    completed_at    TIMESTAMPTZ,
    paused_at       TIMESTAMPTZ
);

CREATE INDEX idx_drip_enrollments_campaign ON drip_enrollments(campaign_id, status);
CREATE INDEX idx_drip_enrollments_contact ON drip_enrollments(contact_id, status);
CREATE UNIQUE INDEX idx_drip_enrollment_unique ON drip_enrollments(campaign_id, contact_id) WHERE status = 'active';

-- ============================================================
-- 9. emails
-- ============================================================
CREATE TABLE emails (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    agent_id        UUID NOT NULL REFERENCES agents(id),
    from_address    TEXT,
    to_address      TEXT,
    subject         TEXT,
    body            TEXT,
    received_at     TIMESTAMPTZ DEFAULT now(),
    classification  TEXT,
    linked_contact_id UUID REFERENCES contacts(id),
    linked_listing_id UUID REFERENCES listings(id),
    action_taken    TEXT,
    created_at      TIMESTAMPTZ DEFAULT now()
);

-- ============================================================
-- 10. tool_executions
-- ============================================================
CREATE TABLE tool_executions (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    agent_id        UUID NOT NULL REFERENCES agents(id),
    conversation_id UUID REFERENCES conversations(id),
    tool_name       TEXT NOT NULL,
    input_json      JSONB NOT NULL,
    output_json     JSONB,
    status          TEXT NOT NULL,
    error_message   TEXT,
    latency_ms      INT,
    created_at      TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX idx_tool_executions_agent_created ON tool_executions(agent_id, created_at);
CREATE INDEX idx_tool_executions_conversation_created ON tool_executions(conversation_id, created_at);
CREATE INDEX idx_tool_executions_errors ON tool_executions(status) WHERE status != 'success';

-- ============================================================
-- 11. embeddings (pgvector — RAG with voyage-3-lite, 512 dims)
-- ============================================================
CREATE TABLE embeddings (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    agent_id        UUID NOT NULL REFERENCES agents(id),
    source_type     TEXT NOT NULL,  -- 'conversation', 'contact', 'listing', 'note', 'document'
    source_id       UUID NOT NULL,
    chunk_index     INT NOT NULL DEFAULT 0,
    content         TEXT NOT NULL,
    embedding       vector(512),  -- voyage-3-lite outputs 512 dims
    title           TEXT,          -- human-readable label for UI display
    expires_at      TIMESTAMPTZ,   -- when this embedding set should expire (NULL = no expiration)
    metadata        JSONB DEFAULT '{}',
    created_at      TIMESTAMPTZ DEFAULT now(),
    updated_at      TIMESTAMPTZ DEFAULT now()
);

-- HNSW index for fast similarity search
CREATE INDEX idx_embeddings_vector ON embeddings USING hnsw (embedding vector_cosine_ops);
CREATE INDEX idx_embeddings_agent_source ON embeddings(agent_id, source_type);
CREATE UNIQUE INDEX idx_embeddings_source_chunk ON embeddings(source_id, chunk_index);
CREATE INDEX idx_embeddings_expires_at ON embeddings(expires_at) WHERE expires_at IS NOT NULL;
CREATE INDEX idx_embeddings_agent_source_type_source_id ON embeddings(agent_id, source_type, source_id);

-- ============================================================
-- 12. usage_metrics
-- ============================================================
CREATE TABLE usage_metrics (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    agent_id        UUID NOT NULL REFERENCES agents(id),
    date            DATE NOT NULL,
    messages_sent   INT DEFAULT 0,
    messages_received INT DEFAULT 0,
    llm_calls       INT DEFAULT 0,
    llm_tokens_used INT DEFAULT 0,
    llm_cost_cents  INT DEFAULT 0,
    voice_minutes   DECIMAL(8,2) DEFAULT 0,
    sms_segments_sent INT DEFAULT 0,
    sms_segments_received INT DEFAULT 0,
    sms_cost_cents  INT DEFAULT 0,
    voice_cost_cents INT DEFAULT 0,
    showings_booked INT DEFAULT 0,
    triggers_fired  INT DEFAULT 0
);

CREATE UNIQUE INDEX idx_usage_metrics_agent_date ON usage_metrics(agent_id, date);
CREATE INDEX idx_usage_metrics_date ON usage_metrics(date);

-- ============================================================
-- 12A. conversation_summaries
-- ============================================================
CREATE TABLE IF NOT EXISTS conversation_summaries (
    id                      UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id               UUID NOT NULL REFERENCES agents(id),
    contact_id              UUID NOT NULL REFERENCES contacts(id),
    conversation_id         UUID NOT NULL REFERENCES conversations(id),
    summary_text            TEXT NOT NULL,
    messages_summarized_count INT NOT NULL DEFAULT 0,
    last_message_id         UUID REFERENCES messages(id),
    token_estimate          INT NOT NULL DEFAULT 0,
    incremental_count       INTEGER DEFAULT 0,
    created_at              TIMESTAMPTZ DEFAULT now(),
    updated_at              TIMESTAMPTZ DEFAULT now()
);

CREATE UNIQUE INDEX idx_convsummary_conversation
    ON conversation_summaries(conversation_id);
CREATE INDEX idx_convsummary_tenant_contact
    ON conversation_summaries(tenant_id, contact_id);

ALTER TABLE conversation_summaries ENABLE ROW LEVEL SECURITY;
CREATE POLICY agent_isolation ON conversation_summaries
    FOR ALL USING (tenant_id = current_setting('app.current_agent_id')::uuid);

-- ============================================================
-- Row Level Security Policies
-- ============================================================

-- contacts
ALTER TABLE contacts ENABLE ROW LEVEL SECURITY;
CREATE POLICY agent_isolation ON contacts
    FOR ALL USING (agent_id = current_setting('app.current_agent_id')::uuid);

-- lead_preferences (via contacts join)
ALTER TABLE lead_preferences ENABLE ROW LEVEL SECURITY;
CREATE POLICY agent_isolation ON lead_preferences
    FOR ALL USING (
        contact_id IN (
            SELECT id FROM contacts
            WHERE agent_id = current_setting('app.current_agent_id')::uuid
        )
    );

-- listings
ALTER TABLE listings ENABLE ROW LEVEL SECURITY;
CREATE POLICY agent_isolation ON listings
    FOR ALL USING (agent_id = current_setting('app.current_agent_id')::uuid);

-- conversations
ALTER TABLE conversations ENABLE ROW LEVEL SECURITY;
CREATE POLICY agent_isolation ON conversations
    FOR ALL USING (agent_id = current_setting('app.current_agent_id')::uuid);

-- messages
ALTER TABLE messages ENABLE ROW LEVEL SECURITY;
CREATE POLICY agent_isolation ON messages
    FOR ALL USING (agent_id = current_setting('app.current_agent_id')::uuid);

-- showings
ALTER TABLE showings ENABLE ROW LEVEL SECURITY;
CREATE POLICY agent_isolation ON showings
    FOR ALL USING (agent_id = current_setting('app.current_agent_id')::uuid);

-- triggers
ALTER TABLE triggers ENABLE ROW LEVEL SECURITY;
CREATE POLICY agent_isolation ON triggers
    FOR ALL USING (agent_id = current_setting('app.current_agent_id')::uuid);

-- transactions
ALTER TABLE transactions ENABLE ROW LEVEL SECURITY;
CREATE POLICY agent_isolation ON transactions
    FOR ALL USING (agent_id = current_setting('app.current_agent_id')::uuid);

-- drip_campaigns
ALTER TABLE drip_campaigns ENABLE ROW LEVEL SECURITY;
CREATE POLICY agent_isolation ON drip_campaigns
    FOR ALL USING (agent_id = current_setting('app.current_agent_id')::uuid);

-- drip_enrollments
ALTER TABLE drip_enrollments ENABLE ROW LEVEL SECURITY;
CREATE POLICY agent_isolation ON drip_enrollments
    FOR ALL USING (agent_id = current_setting('app.current_agent_id')::uuid);

-- emails
ALTER TABLE emails ENABLE ROW LEVEL SECURITY;
CREATE POLICY agent_isolation ON emails
    FOR ALL USING (agent_id = current_setting('app.current_agent_id')::uuid);

-- tool_executions
ALTER TABLE tool_executions ENABLE ROW LEVEL SECURITY;
CREATE POLICY agent_isolation ON tool_executions
    FOR ALL USING (agent_id = current_setting('app.current_agent_id')::uuid);

-- embeddings
ALTER TABLE embeddings ENABLE ROW LEVEL SECURITY;
CREATE POLICY agent_isolation ON embeddings
    FOR ALL USING (agent_id = current_setting('app.current_agent_id')::uuid);

-- usage_metrics
ALTER TABLE usage_metrics ENABLE ROW LEVEL SECURITY;
CREATE POLICY agent_isolation ON usage_metrics
    FOR ALL USING (agent_id = current_setting('app.current_agent_id')::uuid);

-- ============================================================
-- 13. device_tokens (FCM push notifications)
-- ============================================================
CREATE TABLE IF NOT EXISTS device_tokens (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    agent_id        UUID NOT NULL REFERENCES agents(id) ON DELETE CASCADE,
    fcm_token       TEXT NOT NULL,
    device_name     TEXT,
    platform        TEXT,
    is_active       BOOLEAN DEFAULT true,
    created_at      TIMESTAMPTZ DEFAULT now(),
    updated_at      TIMESTAMPTZ DEFAULT now()
);

CREATE UNIQUE INDEX idx_device_tokens_fcm ON device_tokens(fcm_token);
CREATE INDEX idx_device_tokens_agent_active ON device_tokens(agent_id) WHERE is_active = true;

ALTER TABLE device_tokens ENABLE ROW LEVEL SECURITY;
CREATE POLICY agent_isolation ON device_tokens
    FOR ALL USING (agent_id = current_setting('app.current_agent_id')::uuid);

-- ============================================================
-- 14. error_log (Operator Console)
-- ============================================================
CREATE TABLE IF NOT EXISTS error_log (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    agent_id        UUID REFERENCES agents(id),
    module          TEXT NOT NULL,
    severity        TEXT NOT NULL DEFAULT 'error',
    message         TEXT NOT NULL,
    stack_trace     TEXT,
    context_json    JSONB,
    created_at      TIMESTAMPTZ DEFAULT now()
);
CREATE INDEX idx_error_log_created ON error_log(created_at DESC);
CREATE INDEX idx_error_log_agent ON error_log(agent_id);

-- ============================================================
-- 15. harness_traces (Testing Harness)
-- ============================================================
CREATE TABLE IF NOT EXISTS harness_traces (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    trace_json      JSONB NOT NULL,
    agent_id        UUID REFERENCES agents(id),
    sender_phone    TEXT,
    message_body    TEXT,
    intent_detected TEXT,
    model_used      TEXT,
    total_duration_ms INT,
    created_at      TIMESTAMPTZ DEFAULT now()
);
CREATE INDEX idx_harness_traces_created ON harness_traces(created_at DESC);
CREATE INDEX idx_harness_traces_agent ON harness_traces(agent_id);

-- ============================================================
-- 16. console_users (Operator Console per-user auth)
-- ============================================================
CREATE TABLE IF NOT EXISTS console_users (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    email           TEXT NOT NULL,
    password_hash   TEXT NOT NULL,
    display_name    TEXT NOT NULL,
    role            TEXT NOT NULL DEFAULT 'viewer',
    active          BOOLEAN NOT NULL DEFAULT true,
    created_at      TIMESTAMPTZ DEFAULT now(),
    updated_at      TIMESTAMPTZ DEFAULT now()
);

CREATE UNIQUE INDEX idx_console_users_email ON console_users(email);

-- ============================================================
-- 17. audit_log (Operator Console audit trail)
-- ============================================================
CREATE TABLE IF NOT EXISTS audit_log (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id         UUID REFERENCES console_users(id),
    action          TEXT NOT NULL,
    target_entity   TEXT,
    target_id       TEXT,
    ip_address      TEXT,
    metadata        JSONB,
    created_at      TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX idx_audit_log_created ON audit_log(created_at);
CREATE INDEX idx_audit_log_user ON audit_log(user_id);
CREATE INDEX idx_audit_log_action ON audit_log(action);

-- ── Subscriptions (Stripe billing) ──────────────────────────

CREATE TABLE IF NOT EXISTS subscriptions (
    agent_id                UUID PRIMARY KEY REFERENCES agents(id),
    stripe_customer_id      TEXT NOT NULL,
    stripe_subscription_id  TEXT NOT NULL,
    plan_tier               TEXT NOT NULL DEFAULT 'starter',
    status                  TEXT NOT NULL DEFAULT 'trialing',
    trial_ends_at           TIMESTAMPTZ,
    current_period_start    TIMESTAMPTZ,
    current_period_end      TIMESTAMPTZ,
    monthly_price_cents     INTEGER NOT NULL DEFAULT 0,
    message_limit           INTEGER NOT NULL DEFAULT 200,
    contact_limit           INTEGER NOT NULL DEFAULT 50,
    cancel_at_period_end    BOOLEAN NOT NULL DEFAULT false,
    created_at              TIMESTAMPTZ DEFAULT now(),
    updated_at              TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX idx_subscriptions_status ON subscriptions(status);

-- ── Invoices (Stripe billing) ───────────────────────────────

CREATE TABLE IF NOT EXISTS invoices (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    agent_id            UUID NOT NULL REFERENCES agents(id),
    stripe_invoice_id   TEXT NOT NULL UNIQUE,
    amount_cents        INTEGER NOT NULL DEFAULT 0,
    status              TEXT NOT NULL DEFAULT 'pending',
    period_start        TIMESTAMPTZ,
    period_end          TIMESTAMPTZ,
    paid_at             TIMESTAMPTZ,
    invoice_url         TEXT,
    created_at          TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX idx_invoices_agent ON invoices(agent_id);
CREATE INDEX idx_invoices_stripe_id ON invoices(stripe_invoice_id);
