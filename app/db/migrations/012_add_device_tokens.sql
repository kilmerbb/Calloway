-- Migration 012: Add device_tokens table for FCM push notification delivery
-- Stores FCM registration tokens per agent, supporting multiple devices.

CREATE TABLE IF NOT EXISTS device_tokens (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    agent_id        UUID NOT NULL REFERENCES agents(id) ON DELETE CASCADE,
    fcm_token       TEXT NOT NULL,
    device_name     TEXT,          -- e.g. "iPhone 15", "Chrome on Mac"
    platform        TEXT,          -- 'ios', 'android', 'web'
    is_active       BOOLEAN DEFAULT true,
    created_at      TIMESTAMPTZ DEFAULT now(),
    updated_at      TIMESTAMPTZ DEFAULT now()
);

-- An FCM token is globally unique, so we can use it as a natural key
CREATE UNIQUE INDEX idx_device_tokens_fcm ON device_tokens(fcm_token);
-- Fast lookup by agent
CREATE INDEX idx_device_tokens_agent_active ON device_tokens(agent_id) WHERE is_active = true;

-- RLS: tenant isolation
ALTER TABLE device_tokens ENABLE ROW LEVEL SECURITY;
CREATE POLICY agent_isolation ON device_tokens
    FOR ALL USING (agent_id = current_setting('app.current_agent_id')::uuid);
