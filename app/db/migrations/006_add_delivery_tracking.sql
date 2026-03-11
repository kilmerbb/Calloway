-- Migration 006: Add message delivery status tracking
-- Enables tracking of SMS/RCS delivery through Twilio status callbacks.

ALTER TABLE messages ADD COLUMN IF NOT EXISTS provider_message_id TEXT;
ALTER TABLE messages ADD COLUMN IF NOT EXISTS delivery_status TEXT DEFAULT 'pending';
ALTER TABLE messages ADD COLUMN IF NOT EXISTS delivered_at TIMESTAMPTZ;
ALTER TABLE messages ADD COLUMN IF NOT EXISTS failure_reason TEXT;
ALTER TABLE messages ADD COLUMN IF NOT EXISTS feedback_score INT;

CREATE INDEX IF NOT EXISTS idx_messages_provider_id
    ON messages(provider_message_id) WHERE provider_message_id IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_messages_delivery_status
    ON messages(agent_id, delivery_status) WHERE delivery_status IN ('failed', 'undelivered');
