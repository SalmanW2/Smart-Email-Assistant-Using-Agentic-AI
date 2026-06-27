-- Users Table (Enhanced)
CREATE TABLE IF NOT EXISTS users (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    telegram_id BIGINT UNIQUE NOT NULL,
    username VARCHAR(255),
    first_name VARCHAR(255),
    email VARCHAR(255),
    auth_token JSONB,
    ai_mode_enabled BOOLEAN DEFAULT TRUE,
    voice_preference VARCHAR(50) DEFAULT 'text', -- 'text', 'voice', 'both'
    preferred_tts_method VARCHAR(50) DEFAULT 'google', -- 'google' or 'local'
    is_verified BOOLEAN DEFAULT FALSE,
    approved_at TIMESTAMP,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    last_activity_at TIMESTAMP
);

-- Admin Users Table
CREATE TABLE IF NOT EXISTS admin_users (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    email VARCHAR(255) UNIQUE NOT NULL,
    password_hash VARCHAR(255),
    role VARCHAR(50) DEFAULT 'admin', -- 'admin', 'super_admin'
    added_by VARCHAR(255),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    last_login_at TIMESTAMP
);

-- Blocked Users Table
CREATE TABLE IF NOT EXISTS blocked_users (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    block_type VARCHAR(50), -- 'telegram', 'email'
    block_value VARCHAR(255),
    reason TEXT,
    blocked_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    blocked_by VARCHAR(255),
    UNIQUE(block_type, block_value)
);

-- Contacts Table (Advanced Relationship Mapping)
CREATE TABLE IF NOT EXISTS contacts (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    telegram_id BIGINT NOT NULL,
    email_address VARCHAR(255) NOT NULL,
    contact_name VARCHAR(255),
    contact_alias VARCHAR(255), -- "Boss", "John", "HR Team"
    relationship_type VARCHAR(100), -- "manager", "colleague", "client", "friend", etc.
    last_email_date TIMESTAMP,
    frequency_of_contact INT DEFAULT 0, -- Number of emails exchanged
    tags JSONB DEFAULT '[]'::jsonb, -- ["project_alpha", "important"]
    context_topics JSONB DEFAULT '[]'::jsonb, -- Topics discussed with this contact
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (telegram_id) REFERENCES users(telegram_id) ON DELETE CASCADE,
    UNIQUE(telegram_id, email_address)
);

-- Conversation Summaries Table (Memory Management)
CREATE TABLE IF NOT EXISTS conversation_summaries (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    telegram_id BIGINT NOT NULL,
    conversation_date DATE DEFAULT CURRENT_DATE,
    summary_text TEXT, -- 50-100 word AI-generated recap
    key_facts JSONB DEFAULT '{}'::jsonb, -- {"topic": "...", "action_items": [...]}
    email_addresses_mentioned JSONB DEFAULT '[]'::jsonb, -- ["john@example.com", "sarah@example.com"]
    current_topic VARCHAR(255), -- Currently discussed topic (for context)
    tokens_used INT DEFAULT 0,
    message_count INT DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (telegram_id) REFERENCES users(telegram_id) ON DELETE CASCADE
);

-- Email Cache Table (Recent Emails for Context)
CREATE TABLE IF NOT EXISTS email_cache (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    telegram_id BIGINT NOT NULL,
    gmail_message_id VARCHAR(255),
    sender VARCHAR(255),
    sender_email VARCHAR(255),
    subject VARCHAR(500),
    preview TEXT, -- First 200 chars
    received_at TIMESTAMP,
    cached_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    full_body_cached BOOLEAN DEFAULT FALSE,
    FOREIGN KEY (telegram_id) REFERENCES users(telegram_id) ON DELETE CASCADE,
    UNIQUE(telegram_id, gmail_message_id)
);

-- Conversation History Table (Track User Interactions)
CREATE TABLE IF NOT EXISTS conversation_history (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    telegram_id BIGINT NOT NULL,
    user_message TEXT,
    bot_response TEXT,
    interaction_type VARCHAR(50), -- 'compose', 'search', 'read', 'voice', 'attachment_qa'
    related_email_id VARCHAR(255),
    related_contact_id UUID,
    current_topic VARCHAR(255),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (telegram_id) REFERENCES users(telegram_id) ON DELETE CASCADE,
    FOREIGN KEY (related_contact_id) REFERENCES contacts(id) ON DELETE SET NULL
);

-- User Preferences Table (Settings & Toggles)
CREATE TABLE IF NOT EXISTS user_preferences (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    telegram_id BIGINT UNIQUE NOT NULL,
    ai_mode_enabled BOOLEAN DEFAULT TRUE,
    auto_suggest_contacts BOOLEAN DEFAULT TRUE,
    undo_window_seconds INT DEFAULT 4,
    max_attachment_size_mb INT DEFAULT 20,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (telegram_id) REFERENCES users(telegram_id) ON DELETE CASCADE
);

-- Auth Sessions Table
CREATE TABLE IF NOT EXISTS auth_sessions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    state_uuid VARCHAR(255) UNIQUE NOT NULL,
    telegram_id BIGINT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    expires_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP + INTERVAL '10 minutes'
);

-- TTS Usage Tracking Table (for fallback logic)
CREATE TABLE IF NOT EXISTS tts_usage (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    telegram_id BIGINT NOT NULL,
    method VARCHAR(50), -- 'google', 'local'
    characters_generated INT DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (telegram_id) REFERENCES users(telegram_id) ON DELETE CASCADE
);

-- Scheduled Emails Table
CREATE TABLE IF NOT EXISTS scheduled_emails (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    telegram_id BIGINT NOT NULL,
    to_email VARCHAR(255) NOT NULL,
    subject VARCHAR(500),
    body TEXT,
    attachments JSONB DEFAULT '[]'::jsonb,
    scheduled_time TIMESTAMP NOT NULL, -- The exact UTC time to send
    status VARCHAR(50) DEFAULT 'pending', -- 'pending', 'sent', 'failed'
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (telegram_id) REFERENCES users(telegram_id) ON DELETE CASCADE
);

-- STT Usage Tracking
CREATE TABLE IF NOT EXISTS stt_usage (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    telegram_id BIGINT NOT NULL,
    method VARCHAR(50), -- 'groq_whisper', 'gemini_fallback'
    duration_seconds INT DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (telegram_id) REFERENCES users(telegram_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS saved_attachments (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    telegram_id BIGINT NOT NULL,
    file_id VARCHAR(255) NOT NULL,
    file_name VARCHAR(500),
    context_topic VARCHAR(255), -- (e.g., "Ghous Invoice")
    sent_to_emails JSONB DEFAULT '[]'::jsonb,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (telegram_id) REFERENCES users(telegram_id) ON DELETE CASCADE
);

-- Contact Messages Table (Public Contact Form)
CREATE TABLE IF NOT EXISTS contact_messages (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    sender_email VARCHAR(255) NOT NULL,
    message_text TEXT NOT NULL,
    status VARCHAR(50) DEFAULT 'pending', -- 'pending', 'reviewed', 'resolved'
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    reviewed_at TIMESTAMP,
    reviewed_by VARCHAR(255)
);

-- Indexes for Performance
CREATE INDEX idx_users_telegram_id ON users(telegram_id);
CREATE INDEX idx_users_email ON users(email);
CREATE INDEX idx_contacts_telegram_id ON contacts(telegram_id);
CREATE INDEX idx_contacts_email ON contacts(email_address);
CREATE INDEX idx_conversation_summaries_telegram_id ON conversation_summaries(telegram_id);
CREATE INDEX idx_conversation_summaries_date ON conversation_summaries(conversation_date);
CREATE INDEX idx_email_cache_telegram_id ON email_cache(telegram_id);
CREATE INDEX idx_conversation_history_telegram_id ON conversation_history(telegram_id);
CREATE INDEX idx_blocked_users_value ON blocked_users(block_value);
CREATE INDEX idx_saved_attachments_telegram_id ON saved_attachments(telegram_id);
CREATE INDEX idx_contact_messages_status ON contact_messages(status);
CREATE INDEX idx_contact_messages_created_at ON contact_messages(created_at);

-- Admin restrictions columns
ALTER TABLE users 
ADD COLUMN IF NOT EXISTS ai_allowed BOOLEAN DEFAULT TRUE,
ADD COLUMN IF NOT EXISTS voice_allowed BOOLEAN DEFAULT TRUE;

-- Temporary suspension for blocked users
ALTER TABLE blocked_users
ADD COLUMN IF NOT EXISTS expires_at TIMESTAMP NULL;

-- Auto-check preference
ALTER TABLE user_preferences 
ADD COLUMN IF NOT EXISTS auto_check_enabled BOOLEAN DEFAULT TRUE;

-- Unique constraint enforcement
ALTER TABLE contacts DROP CONSTRAINT IF EXISTS contacts_telegram_id_email_address_key;
ALTER TABLE contacts ADD CONSTRAINT contacts_telegram_id_email_address_key UNIQUE (telegram_id, email_address);

-- ============================================================================
-- ROW-LEVEL SECURITY (RLS) & TENANT ISOLATION POLICIES
-- ============================================================================
-- Enable RLS on all 14 tables to prevent unauthorized direct REST access
ALTER TABLE users ENABLE ROW LEVEL SECURITY;
ALTER TABLE admin_users ENABLE ROW LEVEL SECURITY;
ALTER TABLE blocked_users ENABLE ROW LEVEL SECURITY;
ALTER TABLE contacts ENABLE ROW LEVEL SECURITY;
ALTER TABLE conversation_summaries ENABLE ROW LEVEL SECURITY;
ALTER TABLE email_cache ENABLE ROW LEVEL SECURITY;
ALTER TABLE conversation_history ENABLE ROW LEVEL SECURITY;
ALTER TABLE user_preferences ENABLE ROW LEVEL SECURITY;
ALTER TABLE auth_sessions ENABLE ROW LEVEL SECURITY;
ALTER TABLE tts_usage ENABLE ROW LEVEL SECURITY;
ALTER TABLE scheduled_emails ENABLE ROW LEVEL SECURITY;
ALTER TABLE stt_usage ENABLE ROW LEVEL SECURITY;
ALTER TABLE saved_attachments ENABLE ROW LEVEL SECURITY;
ALTER TABLE contact_messages ENABLE ROW LEVEL SECURITY;

-- Tenant Isolation Policy on users (evaluates to FALSE for public/anon/authenticated roles)
-- This shuts off direct REST queries, ensuring all access goes through FastAPI with service_role bypass.
CREATE POLICY "Tenant-Isolation-Policy" ON users
    FOR ALL TO public USING (false);

-- Tenant Isolation Policies for other tables (anon/public block)
CREATE POLICY "Tenant-Isolation-Policy-Contacts" ON contacts FOR ALL TO public USING (false);
CREATE POLICY "Tenant-Isolation-Policy-Summaries" ON conversation_summaries FOR ALL TO public USING (false);
CREATE POLICY "Tenant-Isolation-Policy-History" ON conversation_history FOR ALL TO public USING (false);
CREATE POLICY "Tenant-Isolation-Policy-Preferences" ON user_preferences FOR ALL TO public USING (false);
CREATE POLICY "Tenant-Isolation-Policy-Cache" ON email_cache FOR ALL TO public USING (false);
CREATE POLICY "Tenant-Isolation-Policy-Scheduled" ON scheduled_emails FOR ALL TO public USING (false);
CREATE POLICY "Tenant-Isolation-Policy-SavedAttachments" ON saved_attachments FOR ALL TO public USING (false);
CREATE POLICY "Tenant-Isolation-Policy-STT" ON stt_usage FOR ALL TO public USING (false);
CREATE POLICY "Tenant-Isolation-Policy-TTS" ON tts_usage FOR ALL TO public USING (false);

-- Public Contact Form Policy: Allow anonymous users to insert contact messages, but block select/update
CREATE POLICY "Allow anonymous message submissions" ON contact_messages
    FOR INSERT TO anon WITH CHECK (status = 'pending');