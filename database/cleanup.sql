-- 1. Drop the completely unused legacy attachments table
DROP TABLE IF EXISTS saved_attachments CASCADE;

-- 2. Drop legacy memory tables if you strictly prefer relying on the live RAM Context window + pgvector
-- WARNING: Only run this if you want to wipe old summarize history.
-- DROP TABLE IF EXISTS conversation_summaries CASCADE;
