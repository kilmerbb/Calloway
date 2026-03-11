-- Migration 010: Replace embeddings table with RAG-optimized schema
-- Uses voyage-3-lite (512 dimensions) with HNSW index for fast similarity search

-- Drop the old embeddings table and recreate with RAG-optimized schema
DROP TABLE IF EXISTS embeddings CASCADE;

CREATE TABLE embeddings (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    agent_id UUID NOT NULL REFERENCES agents(id),
    source_type TEXT NOT NULL,  -- 'conversation', 'contact', 'listing', 'note'
    source_id UUID NOT NULL,
    chunk_index INT NOT NULL DEFAULT 0,
    content TEXT NOT NULL,
    embedding vector(512),  -- voyage-3-lite outputs 512 dims
    metadata JSONB DEFAULT '{}',
    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now()
);

-- HNSW index for fast similarity search
CREATE INDEX idx_embeddings_vector ON embeddings USING hnsw (embedding vector_cosine_ops);
CREATE INDEX idx_embeddings_agent_source ON embeddings(agent_id, source_type);
CREATE UNIQUE INDEX idx_embeddings_source_chunk ON embeddings(source_id, chunk_index);

ALTER TABLE embeddings ENABLE ROW LEVEL SECURITY;
CREATE POLICY agent_isolation ON embeddings
    FOR ALL USING (agent_id = current_setting('app.current_agent_id')::uuid);
