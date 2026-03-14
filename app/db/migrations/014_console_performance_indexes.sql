-- Migration 014: Console Performance Indexes
-- Purpose: Add indexes to support cross-tenant console queries that bypass RLS.
-- These indexes target the most frequent console_queries.py access patterns:
--   - get_recent_conversations (ORDER BY last_message_at DESC)
--   - get_conversation_thread (tool_executions by conversation)
--   - cost/usage dashboards (usage_metrics by date)
--   - get_trigger_queue (triggers by status + agent)
--
-- All indexes use CONCURRENTLY to avoid locking tables in production.
-- Note: messages(conversation_id, created_at) is intentionally omitted —
-- PostgreSQL can reverse-scan the existing ASC index via backward index scan.

-- Conversations: ORDER BY last_message_at DESC (get_recent_conversations)
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_conversations_last_message_at
    ON conversations(last_message_at DESC NULLS LAST);

-- Conversations: filtered by agent + ordered by last_message_at
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_conversations_agent_last_message
    ON conversations(agent_id, last_message_at DESC NULLS LAST);

-- Tool executions: lookup by conversation (get_conversation_thread)
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_tool_executions_conversation_created
    ON tool_executions(conversation_id, created_at);

-- Usage metrics: cost queries filtered by date range without agent filter
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_usage_metrics_date
    ON usage_metrics(date);

-- Triggers: queue filtered by status + agent (get_trigger_queue)
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_triggers_status_agent_scheduled
    ON triggers(status, agent_id, scheduled_at);
