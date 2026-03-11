-- Migration 008: Add transactions table
CREATE TABLE IF NOT EXISTS transactions (
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

CREATE INDEX IF NOT EXISTS idx_transactions_agent_status ON transactions(agent_id, status);
CREATE INDEX IF NOT EXISTS idx_transactions_contact ON transactions(contact_id);
CREATE INDEX IF NOT EXISTS idx_transactions_closing ON transactions(closing_date) WHERE status NOT IN ('closed', 'fell_through');

ALTER TABLE transactions ENABLE ROW LEVEL SECURITY;
CREATE POLICY agent_isolation ON transactions
    FOR ALL USING (agent_id = current_setting('app.current_agent_id')::uuid);
