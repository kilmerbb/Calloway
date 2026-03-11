-- Migration 009: Add drip campaigns and enrollments tables

CREATE TABLE IF NOT EXISTS drip_campaigns (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    agent_id        UUID NOT NULL REFERENCES agents(id),
    name            TEXT NOT NULL,
    description     TEXT,
    trigger_type    TEXT NOT NULL DEFAULT 'nurture',
    steps           JSONB NOT NULL DEFAULT '[]',
    is_active       BOOLEAN DEFAULT true,
    created_at      TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_drip_campaigns_agent ON drip_campaigns(agent_id, is_active);

ALTER TABLE drip_campaigns ENABLE ROW LEVEL SECURITY;
CREATE POLICY agent_isolation ON drip_campaigns
    FOR ALL USING (agent_id = current_setting('app.current_agent_id')::uuid);

CREATE TABLE IF NOT EXISTS drip_enrollments (
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

CREATE INDEX IF NOT EXISTS idx_drip_enrollments_campaign ON drip_enrollments(campaign_id, status);
CREATE INDEX IF NOT EXISTS idx_drip_enrollments_contact ON drip_enrollments(contact_id, status);
CREATE UNIQUE INDEX IF NOT EXISTS idx_drip_enrollment_unique ON drip_enrollments(campaign_id, contact_id) WHERE status = 'active';

ALTER TABLE drip_enrollments ENABLE ROW LEVEL SECURITY;
CREATE POLICY agent_isolation ON drip_enrollments
    FOR ALL USING (agent_id = current_setting('app.current_agent_id')::uuid);
