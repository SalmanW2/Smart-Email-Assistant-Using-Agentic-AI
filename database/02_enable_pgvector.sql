-- ============================================================================
-- MIGRATION: 02_enable_pgvector.sql
-- Description: Sets up pgvector extension, embedding column, and semantic 
--              search RPC for email caching.
-- ============================================================================

-- 1. Enable pgvector extension (must be superuser or have privileges)
CREATE EXTENSION IF NOT EXISTS vector;

-- 2. Add the embedding column to email_cache (Gemini 1.5 Flash / text-embedding-004 uses 768 dims)
ALTER TABLE email_cache
ADD COLUMN IF NOT EXISTS embedding vector(768);

-- 3. Create an IVFFlat or HNSW index for lightning fast cosine similarity search
-- We use HNSW here as it's highly efficient for Postgres >= 15 with pgvector >= 0.5.0
-- (If using older pgvector, you can fall back to IVFFlat)
CREATE INDEX IF NOT EXISTS idx_email_cache_embedding_hnsw 
ON email_cache 
USING hnsw (embedding vector_cosine_ops);

-- 4. Create an RPC function to perform Semantic Similarity Matching
-- This function will be called from the Python backend (Supabase client.rpc)
CREATE OR REPLACE FUNCTION match_emails (
  query_embedding vector(768),
  match_threshold float,
  match_count int,
  user_telegram_id bigint
)
RETURNS TABLE (
  id uuid,
  gmail_message_id varchar,
  sender varchar,
  sender_email varchar,
  subject varchar,
  preview text,
  received_at timestamp,
  similarity float
)
LANGUAGE plpgsql
AS $$
BEGIN
  RETURN QUERY
  SELECT
    e.id,
    e.gmail_message_id,
    e.sender,
    e.sender_email,
    e.subject,
    e.preview,
    e.received_at,
    1 - (e.embedding <=> query_embedding) AS similarity
  FROM email_cache e
  WHERE e.telegram_id = user_telegram_id
    AND e.embedding IS NOT NULL
    -- <=> is the vector cosine distance operator. 
    -- 1 - distance = cosine similarity
    AND 1 - (e.embedding <=> query_embedding) > match_threshold
  ORDER BY e.embedding <=> query_embedding ASC
  LIMIT match_count;
END;
$$;