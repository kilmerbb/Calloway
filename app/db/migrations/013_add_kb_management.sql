-- Migration 013: Add knowledge base management columns
-- Supports: Customer Detail redesign — Knowledge Base tab, expiration policy
-- Reversible: All changes are additive (ADD COLUMN with defaults / NULLable)

-- ============================================================
-- 1. embeddings table: add title and expiration columns
-- ============================================================

ALTER TABLE embeddings ADD COLUMN IF NOT EXISTS title TEXT;
-- Human-readable label for UI display. Auto-generated during indexing.
-- NULL for legacy rows; UI falls back to source_type + source_id.

ALTER TABLE embeddings ADD COLUMN IF NOT EXISTS expires_at TIMESTAMPTZ;
-- When this embedding set should expire. NULL = no expiration.
-- Applies at the source_id level: all chunks for a source_id share the same expiration.

-- Index for the daily scanner expiration query
CREATE INDEX IF NOT EXISTS idx_embeddings_expires_at
    ON embeddings(expires_at)
    WHERE expires_at IS NOT NULL;

-- Index for knowledge base tab grouping query
CREATE INDEX IF NOT EXISTS idx_embeddings_agent_source_type_source_id
    ON embeddings(agent_id, source_type, source_id);

-- ============================================================
-- 2. agents table: add KB expiration policy columns
-- ============================================================

ALTER TABLE agents ADD COLUMN IF NOT EXISTS kb_expiration_policy TEXT DEFAULT 'remind_only';
-- Either 'auto_remove' or 'remind_only'. Controls what happens when embeddings expire.

ALTER TABLE agents ADD COLUMN IF NOT EXISTS kb_default_ttl_days INTEGER;
-- Default TTL in days for new knowledge base items. NULL = no default expiration.

-- ============================================================
-- Rollback (manual — run only if reverting):
-- ALTER TABLE embeddings DROP COLUMN IF EXISTS title;
-- ALTER TABLE embeddings DROP COLUMN IF EXISTS expires_at;
-- DROP INDEX IF EXISTS idx_embeddings_expires_at;
-- DROP INDEX IF EXISTS idx_embeddings_agent_source_type_source_id;
-- ALTER TABLE agents DROP COLUMN IF EXISTS kb_expiration_policy;
-- ALTER TABLE agents DROP COLUMN IF EXISTS kb_default_ttl_days;
-- ============================================================
