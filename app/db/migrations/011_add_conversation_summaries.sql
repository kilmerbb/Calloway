-- Migration 011: Add conversation_summaries table for context window optimization
-- Stores running summaries of long conversations so the assembler can load
-- summary + recent messages instead of trying to fit all history in the token budget.

CREATE TABLE IF NOT EXISTS conversation_summaries (
    id                      UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id               UUID NOT NULL REFERENCES agents(id),
    contact_id              UUID NOT NULL REFERENCES contacts(id),
    conversation_id         UUID NOT NULL REFERENCES conversations(id),
    summary_text            TEXT NOT NULL,
    messages_summarized_count INT NOT NULL DEFAULT 0,
    last_message_id         UUID REFERENCES messages(id),
    token_estimate          INT NOT NULL DEFAULT 0,
    created_at              TIMESTAMPTZ DEFAULT now(),
    updated_at              TIMESTAMPTZ DEFAULT now()
);

-- Each conversation gets at most one active summary (latest wins)
CREATE UNIQUE INDEX idx_convsummary_conversation
    ON conversation_summaries(conversation_id);

-- Fast lookup by tenant + contact (the assembler's access pattern)
CREATE INDEX idx_convsummary_tenant_contact
    ON conversation_summaries(tenant_id, contact_id);

-- RLS: tenant isolation
ALTER TABLE conversation_summaries ENABLE ROW LEVEL SECURITY;
CREATE POLICY agent_isolation ON conversation_summaries
    FOR ALL USING (tenant_id = current_setting('app.current_agent_id')::uuid);
