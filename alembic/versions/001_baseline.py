"""001 baseline schema

Revision ID: 001_baseline
Revises:
Create Date: 2026-03-11

Baseline migration representing the full schema from app/db/schema.sql.
On existing databases this was stamped as head (no-op).
On fresh databases the upgrade() creates all tables, indexes, and RLS policies.
"""
from alembic import op

revision = "001_baseline"
down_revision = None
branch_labels = None
depends_on = None

# Tables that use standard agent_id-based RLS isolation
_RLS_TABLES_AGENT_ID = [
    "contacts",
    "listings",
    "conversations",
    "messages",
    "showings",
    "triggers",
    "emails",
    "tool_executions",
    "embeddings",
    "usage_metrics",
    "consent_log",
    "drip_campaigns",
    "drip_enrollments",
]


def _create_rls_policy_idempotent(table, column="agent_id"):
    """Enable RLS and create agent_isolation policy if it doesn't exist."""
    op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
    using_clause = f"{column} = current_setting('app.current_agent_id')::uuid"
    op.execute(
        f"DO $$ BEGIN "
        f"IF NOT EXISTS ("
        f"SELECT 1 FROM pg_policies "
        f"WHERE tablename = '{table}' AND policyname = 'agent_isolation'"
        f") THEN "
        f"CREATE POLICY agent_isolation ON {table} "
        f"FOR ALL USING ({using_clause}); "
        f"END IF; "
        f"END $$"
    )


def upgrade() -> None:
    """Create the full baseline schema.

    For existing databases that were bootstrapped from schema.sql, this
    migration was applied via ``alembic stamp 001_baseline`` (no DDL ran).
    For new databases, this creates everything from scratch.
    """

    # ==================================================================
    # Extension
    # ==================================================================
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    # ==================================================================
    # 1. agents
    # ==================================================================
    op.execute(
        "CREATE TABLE IF NOT EXISTS agents ("
        "id UUID PRIMARY KEY DEFAULT gen_random_uuid(), "
        "name TEXT NOT NULL, "
        "email TEXT NOT NULL, "
        "phone TEXT NOT NULL, "
        "brokerage TEXT, "
        "market TEXT, "
        "timezone TEXT DEFAULT 'America/New_York', "
        "twilio_number TEXT NOT NULL, "
        "google_oauth JSONB, "
        "vapi_assistant TEXT, "
        "scheduling_prefs JSONB NOT NULL DEFAULT '{}', "
        "style_profile JSONB NOT NULL DEFAULT '{}', "
        "autonomy_rules JSONB NOT NULL DEFAULT '{}', "
        "listing_rules JSONB NOT NULL DEFAULT '{}', "
        "system_prompt TEXT, "
        "google_review_link TEXT, "
        "briefing_time TIME DEFAULT '07:30', "
        "current_status TEXT DEFAULT 'available', "
        "status_until TIMESTAMPTZ, "
        "kb_expiration_policy TEXT DEFAULT 'remind_only', "
        "kb_default_ttl_days INTEGER, "
        "created_at TIMESTAMPTZ DEFAULT now(), "
        "updated_at TIMESTAMPTZ DEFAULT now()"
        ")"
    )

    # ==================================================================
    # 2. contacts
    # ==================================================================
    op.execute(
        "CREATE TABLE IF NOT EXISTS contacts ("
        "id UUID PRIMARY KEY DEFAULT gen_random_uuid(), "
        "agent_id UUID NOT NULL REFERENCES agents(id), "
        "name TEXT NOT NULL, "
        "phone TEXT NOT NULL, "
        "email TEXT, "
        "role TEXT NOT NULL DEFAULT 'lead', "
        "lifecycle_stage TEXT NOT NULL DEFAULT 'new_lead', "
        "linked_listing_id UUID, "
        "preferences JSONB DEFAULT '{}', "
        "notes TEXT, "
        "last_contact_at TIMESTAMPTZ, "
        "silent_mode BOOLEAN DEFAULT false, "
        "consent_status TEXT DEFAULT 'pending', "
        "consent_granted_at TIMESTAMPTZ, "
        "consent_revoked_at TIMESTAMPTZ, "
        "consent_method TEXT, "
        "consent_message TEXT, "
        "consent_response TEXT, "
        "language_detected TEXT DEFAULT 'en', "
        "interaction_count INT DEFAULT 0, "
        "created_at TIMESTAMPTZ DEFAULT now(), "
        "updated_at TIMESTAMPTZ DEFAULT now()"
        ")"
    )
    op.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS idx_contacts_agent_phone "
        "ON contacts(agent_id, phone)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_contacts_agent_lifecycle "
        "ON contacts(agent_id, lifecycle_stage)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_contacts_agent_last_contact "
        "ON contacts(agent_id, last_contact_at)"
    )

    # ==================================================================
    # 2A. consent_log
    # ==================================================================
    op.execute(
        "CREATE TABLE IF NOT EXISTS consent_log ("
        "id UUID PRIMARY KEY DEFAULT gen_random_uuid(), "
        "agent_id UUID NOT NULL REFERENCES agents(id), "
        "contact_id UUID NOT NULL REFERENCES contacts(id), "
        "event_type TEXT NOT NULL, "
        "message_text TEXT, "
        "response_text TEXT, "
        "created_at TIMESTAMPTZ DEFAULT now()"
        ")"
    )

    # ==================================================================
    # 3. lead_preferences
    # ==================================================================
    op.execute(
        "CREATE TABLE IF NOT EXISTS lead_preferences ("
        "contact_id UUID PRIMARY KEY REFERENCES contacts(id) ON DELETE CASCADE, "
        "areas TEXT[], "
        "timeline TEXT, "
        "preapproved BOOLEAN, "
        "property_type TEXT, "
        "bedrooms_min INT, "
        "bathrooms_min NUMERIC(3,1), "
        "price_min INT, "
        "price_max INT"
        ")"
    )

    # ==================================================================
    # 4. listings
    # ==================================================================
    op.execute(
        "CREATE TABLE IF NOT EXISTS listings ("
        "id UUID PRIMARY KEY DEFAULT gen_random_uuid(), "
        "agent_id UUID NOT NULL REFERENCES agents(id), "
        "address TEXT NOT NULL, "
        "price INT NOT NULL, "
        "beds INT, "
        "baths NUMERIC(3,1), "
        "sqft INT, "
        "hoa INT, "
        "features JSONB DEFAULT '[]', "
        "showing_instructions TEXT, "
        "lockbox TEXT, "
        "access_rules JSONB DEFAULT '{}', "
        "open_house_dates JSONB DEFAULT '[]', "
        "list_date DATE, "
        "status TEXT DEFAULT 'active', "
        "notes TEXT, "
        "last_updated_at TIMESTAMPTZ DEFAULT now(), "
        "created_at TIMESTAMPTZ DEFAULT now()"
        ")"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_listings_agent_status "
        "ON listings(agent_id, status)"
    )

    # ==================================================================
    # 5. conversations
    # ==================================================================
    op.execute(
        "CREATE TABLE IF NOT EXISTS conversations ("
        "id UUID PRIMARY KEY DEFAULT gen_random_uuid(), "
        "agent_id UUID NOT NULL REFERENCES agents(id), "
        "contact_id UUID REFERENCES contacts(id), "
        "channel TEXT NOT NULL, "
        "stage TEXT DEFAULT 'open', "
        "active_handler TEXT, "
        "last_message_at TIMESTAMPTZ, "
        "created_at TIMESTAMPTZ DEFAULT now()"
        ")"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_conversations_agent_contact "
        "ON conversations(agent_id, contact_id)"
    )

    # ==================================================================
    # 6. messages
    # ==================================================================
    op.execute(
        "CREATE TABLE IF NOT EXISTS messages ("
        "id UUID PRIMARY KEY DEFAULT gen_random_uuid(), "
        "agent_id UUID NOT NULL REFERENCES agents(id), "
        "conversation_id UUID NOT NULL REFERENCES conversations(id), "
        "sender_type TEXT NOT NULL, "
        "body TEXT NOT NULL, "
        "intent TEXT, "
        "ai_generated BOOLEAN DEFAULT false, "
        "model_used TEXT, "
        "tokens_used INT, "
        "created_at TIMESTAMPTZ DEFAULT now()"
        ")"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_messages_conversation_created "
        "ON messages(conversation_id, created_at)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_messages_agent_created "
        "ON messages(agent_id, created_at)"
    )

    # ==================================================================
    # 7. showings
    # ==================================================================
    op.execute(
        "CREATE TABLE IF NOT EXISTS showings ("
        "id UUID PRIMARY KEY DEFAULT gen_random_uuid(), "
        "agent_id UUID NOT NULL REFERENCES agents(id), "
        "contact_id UUID NOT NULL REFERENCES contacts(id), "
        "listing_id UUID NOT NULL REFERENCES listings(id), "
        "start_time TIMESTAMPTZ NOT NULL, "
        "end_time TIMESTAMPTZ NOT NULL, "
        "status TEXT DEFAULT 'hold', "
        "hold_expires_at TIMESTAMPTZ, "
        "calendar_event_id TEXT, "
        "requesting_agent_id UUID, "
        "feedback TEXT, "
        "created_at TIMESTAMPTZ DEFAULT now()"
        ")"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_showings_agent_start "
        "ON showings(agent_id, start_time)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_showings_listing_status "
        "ON showings(listing_id, status)"
    )

    # ==================================================================
    # 8. triggers
    # ==================================================================
    op.execute(
        "CREATE TABLE IF NOT EXISTS triggers ("
        "id UUID PRIMARY KEY DEFAULT gen_random_uuid(), "
        "agent_id UUID NOT NULL REFERENCES agents(id), "
        "entity_type TEXT NOT NULL, "
        "entity_id UUID NOT NULL, "
        "trigger_type TEXT NOT NULL, "
        "scheduled_at TIMESTAMPTZ NOT NULL, "
        "recurrence TEXT, "
        "action_type TEXT NOT NULL, "
        "message_template TEXT, "
        "autonomy_level TEXT DEFAULT 'ask_agent', "
        "status TEXT DEFAULT 'pending', "
        "notes TEXT, "
        "created_at TIMESTAMPTZ DEFAULT now()"
        ")"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_triggers_status_scheduled "
        "ON triggers(status, scheduled_at)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_triggers_agent_entity "
        "ON triggers(agent_id, entity_type, entity_id)"
    )

    # ==================================================================
    # 8A. drip_campaigns
    # ==================================================================
    op.execute(
        "CREATE TABLE IF NOT EXISTS drip_campaigns ("
        "id UUID PRIMARY KEY DEFAULT gen_random_uuid(), "
        "agent_id UUID NOT NULL REFERENCES agents(id), "
        "name TEXT NOT NULL, "
        "description TEXT, "
        "trigger_type TEXT NOT NULL DEFAULT 'nurture', "
        "steps JSONB NOT NULL DEFAULT '[]', "
        "is_active BOOLEAN DEFAULT true, "
        "created_at TIMESTAMPTZ DEFAULT now()"
        ")"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_drip_campaigns_agent "
        "ON drip_campaigns(agent_id, is_active)"
    )

    # ==================================================================
    # 8B. drip_enrollments
    # ==================================================================
    op.execute(
        "CREATE TABLE IF NOT EXISTS drip_enrollments ("
        "id UUID PRIMARY KEY DEFAULT gen_random_uuid(), "
        "agent_id UUID NOT NULL REFERENCES agents(id), "
        "campaign_id UUID NOT NULL REFERENCES drip_campaigns(id), "
        "contact_id UUID NOT NULL REFERENCES contacts(id), "
        "current_step INT DEFAULT 0, "
        "status TEXT DEFAULT 'active', "
        "enrolled_at TIMESTAMPTZ DEFAULT now(), "
        "completed_at TIMESTAMPTZ, "
        "paused_at TIMESTAMPTZ"
        ")"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_drip_enrollments_campaign "
        "ON drip_enrollments(campaign_id, status)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_drip_enrollments_contact "
        "ON drip_enrollments(contact_id, status)"
    )
    op.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS idx_drip_enrollment_unique "
        "ON drip_enrollments(campaign_id, contact_id) WHERE status = 'active'"
    )

    # ==================================================================
    # 9. emails
    # ==================================================================
    op.execute(
        "CREATE TABLE IF NOT EXISTS emails ("
        "id UUID PRIMARY KEY DEFAULT gen_random_uuid(), "
        "agent_id UUID NOT NULL REFERENCES agents(id), "
        "from_address TEXT, "
        "to_address TEXT, "
        "subject TEXT, "
        "body TEXT, "
        "received_at TIMESTAMPTZ DEFAULT now(), "
        "classification TEXT, "
        "linked_contact_id UUID REFERENCES contacts(id), "
        "linked_listing_id UUID REFERENCES listings(id), "
        "action_taken TEXT, "
        "created_at TIMESTAMPTZ DEFAULT now()"
        ")"
    )

    # ==================================================================
    # 10. tool_executions
    # ==================================================================
    op.execute(
        "CREATE TABLE IF NOT EXISTS tool_executions ("
        "id UUID PRIMARY KEY DEFAULT gen_random_uuid(), "
        "agent_id UUID NOT NULL REFERENCES agents(id), "
        "conversation_id UUID REFERENCES conversations(id), "
        "tool_name TEXT NOT NULL, "
        "input_json JSONB NOT NULL, "
        "output_json JSONB, "
        "status TEXT NOT NULL, "
        "error_message TEXT, "
        "latency_ms INT, "
        "created_at TIMESTAMPTZ DEFAULT now()"
        ")"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_tool_executions_agent_created "
        "ON tool_executions(agent_id, created_at)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_tool_executions_errors "
        "ON tool_executions(status) WHERE status != 'success'"
    )

    # ==================================================================
    # 11. embeddings (pgvector -- voyage-3-lite, 512 dims)
    # ==================================================================
    op.execute(
        "CREATE TABLE IF NOT EXISTS embeddings ("
        "id UUID PRIMARY KEY DEFAULT gen_random_uuid(), "
        "agent_id UUID NOT NULL REFERENCES agents(id), "
        "source_type TEXT NOT NULL, "
        "source_id UUID NOT NULL, "
        "chunk_index INT NOT NULL DEFAULT 0, "
        "content TEXT NOT NULL, "
        "embedding vector(512), "
        "title TEXT, "
        "expires_at TIMESTAMPTZ, "
        "metadata JSONB DEFAULT '{}', "
        "created_at TIMESTAMPTZ DEFAULT now(), "
        "updated_at TIMESTAMPTZ DEFAULT now()"
        ")"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_embeddings_vector "
        "ON embeddings USING hnsw (embedding vector_cosine_ops)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_embeddings_agent_source "
        "ON embeddings(agent_id, source_type)"
    )
    op.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS idx_embeddings_source_chunk "
        "ON embeddings(source_id, chunk_index)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_embeddings_expires_at "
        "ON embeddings(expires_at) WHERE expires_at IS NOT NULL"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_embeddings_agent_source_type_source_id "
        "ON embeddings(agent_id, source_type, source_id)"
    )

    # ==================================================================
    # 12. usage_metrics
    # ==================================================================
    op.execute(
        "CREATE TABLE IF NOT EXISTS usage_metrics ("
        "id UUID PRIMARY KEY DEFAULT gen_random_uuid(), "
        "agent_id UUID NOT NULL REFERENCES agents(id), "
        "date DATE NOT NULL, "
        "messages_sent INT DEFAULT 0, "
        "messages_received INT DEFAULT 0, "
        "llm_calls INT DEFAULT 0, "
        "llm_tokens_used INT DEFAULT 0, "
        "llm_cost_cents INT DEFAULT 0, "
        "voice_minutes DECIMAL(8,2) DEFAULT 0, "
        "showings_booked INT DEFAULT 0, "
        "triggers_fired INT DEFAULT 0"
        ")"
    )
    op.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS idx_usage_metrics_agent_date "
        "ON usage_metrics(agent_id, date)"
    )

    # ==================================================================
    # 12A. conversation_summaries
    # ==================================================================
    op.execute(
        "CREATE TABLE IF NOT EXISTS conversation_summaries ("
        "id UUID PRIMARY KEY DEFAULT gen_random_uuid(), "
        "tenant_id UUID NOT NULL REFERENCES agents(id), "
        "contact_id UUID NOT NULL REFERENCES contacts(id), "
        "conversation_id UUID NOT NULL REFERENCES conversations(id), "
        "summary_text TEXT NOT NULL, "
        "messages_summarized_count INT NOT NULL DEFAULT 0, "
        "last_message_id UUID REFERENCES messages(id), "
        "token_estimate INT NOT NULL DEFAULT 0, "
        "incremental_count INTEGER DEFAULT 0, "
        "created_at TIMESTAMPTZ DEFAULT now(), "
        "updated_at TIMESTAMPTZ DEFAULT now()"
        ")"
    )
    op.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS idx_convsummary_conversation "
        "ON conversation_summaries(conversation_id)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_convsummary_tenant_contact "
        "ON conversation_summaries(tenant_id, contact_id)"
    )

    # ==================================================================
    # 13. error_log
    # ==================================================================
    op.execute(
        "CREATE TABLE IF NOT EXISTS error_log ("
        "id UUID PRIMARY KEY DEFAULT gen_random_uuid(), "
        "agent_id UUID REFERENCES agents(id), "
        "module TEXT NOT NULL, "
        "severity TEXT NOT NULL DEFAULT 'error', "
        "message TEXT NOT NULL, "
        "stack_trace TEXT, "
        "context_json JSONB, "
        "created_at TIMESTAMPTZ DEFAULT now()"
        ")"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_error_log_created "
        "ON error_log(created_at DESC)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_error_log_agent "
        "ON error_log(agent_id)"
    )

    # ==================================================================
    # 14. harness_traces
    # ==================================================================
    op.execute(
        "CREATE TABLE IF NOT EXISTS harness_traces ("
        "id UUID PRIMARY KEY DEFAULT gen_random_uuid(), "
        "trace_json JSONB NOT NULL, "
        "agent_id UUID REFERENCES agents(id), "
        "sender_phone TEXT, "
        "message_body TEXT, "
        "intent_detected TEXT, "
        "model_used TEXT, "
        "total_duration_ms INT, "
        "created_at TIMESTAMPTZ DEFAULT now()"
        ")"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_harness_traces_created "
        "ON harness_traces(created_at DESC)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_harness_traces_agent "
        "ON harness_traces(agent_id)"
    )

    # ==================================================================
    # Row Level Security Policies
    # ==================================================================
    # Alembic does not natively track RLS.  Policies are managed as raw
    # SQL with idempotent DO-blocks so this migration is safe to run on
    # both fresh and pre-existing databases.
    #
    # Pattern: every tenant-scoped table gets an ``agent_isolation``
    # policy that restricts rows to the agent whose UUID matches the
    # session variable ``app.current_agent_id``, set via set_config()
    # at connection time (see app/db/connection.py).
    # ==================================================================

    for table in _RLS_TABLES_AGENT_ID:
        _create_rls_policy_idempotent(table, column="agent_id")

    # lead_preferences -- joined through contacts
    op.execute("ALTER TABLE lead_preferences ENABLE ROW LEVEL SECURITY")
    op.execute(
        "DO $$ BEGIN "
        "IF NOT EXISTS ("
        "SELECT 1 FROM pg_policies "
        "WHERE tablename = 'lead_preferences' AND policyname = 'agent_isolation'"
        ") THEN "
        "CREATE POLICY agent_isolation ON lead_preferences "
        "FOR ALL USING ("
        "contact_id IN ("
        "SELECT id FROM contacts "
        "WHERE agent_id = current_setting('app.current_agent_id')::uuid"
        ")"
        "); "
        "END IF; "
        "END $$"
    )

    # conversation_summaries -- uses tenant_id instead of agent_id
    _create_rls_policy_idempotent("conversation_summaries", column="tenant_id")


def downgrade() -> None:
    """Cannot downgrade past baseline."""
    raise RuntimeError("Cannot downgrade past baseline migration")
