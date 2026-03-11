-- Migration 005: Add lead_source tracking to contacts
-- Run this against your database to add the lead_source column.

ALTER TABLE contacts ADD COLUMN IF NOT EXISTS lead_source TEXT;

CREATE INDEX IF NOT EXISTS idx_contacts_agent_email
    ON contacts(agent_id, email) WHERE email IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_contacts_lead_source
    ON contacts(agent_id, lead_source) WHERE lead_source IS NOT NULL;

-- Backfill existing contacts based on conversation channel
UPDATE contacts c
SET lead_source = COALESCE(
    (SELECT DISTINCT cv.channel FROM conversations cv
     WHERE cv.contact_id = c.id
     ORDER BY cv.created_at LIMIT 1),
    'manual'
)
WHERE c.lead_source IS NULL;
