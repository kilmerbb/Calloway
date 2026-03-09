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
    language_detected TEXT DEFAULT 'en',
    interaction_count INT DEFAULT 0,
    created_at      TIMESTAMPTZ DEFAULT now(),
    updated_at      TIMESTAMPTZ DEFAULT now()
);

CREATE UNIQUE INDEX idx_contacts_agent_phone ON contacts(agent_id, phone);
CREATE INDEX idx_contacts_agent_lifecycle ON contacts(agent_id, lifecycle_stage);
CREATE INDEX idx_contacts_agent_last_contact ON contacts(agent_id, last_contact_at);

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
    created_at      TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX idx_messages_conversation_created ON messages(conversation_id, created_at);
CREATE INDEX idx_messages_agent_created ON messages(agent_id, created_at);

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
CREATE INDEX idx_triggers_agent_entity ON triggers(agent_id, entity_type, entity_id);

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
CREATE INDEX idx_tool_executions_errors ON tool_executions(status) WHERE status != 'success';

-- ============================================================
-- 11. embeddings (pgvector)
-- ============================================================
CREATE TABLE embeddings (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    agent_id        UUID NOT NULL REFERENCES agents(id),
    source_type     TEXT NOT NULL,
    source_id       UUID NOT NULL,
    content_chunk   TEXT NOT NULL,
    embedding       vector(1536),
    metadata        JSONB DEFAULT '{}',
    created_at      TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX idx_embeddings_vector ON embeddings
    USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100);

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
    showings_booked INT DEFAULT 0,
    triggers_fired  INT DEFAULT 0
);

CREATE UNIQUE INDEX idx_usage_metrics_agent_date ON usage_metrics(agent_id, date);

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
