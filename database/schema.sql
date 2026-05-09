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

-- Contacts Table (NEW - Advanced Relationship Mapping)
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

-- Conversation Summaries Table (NEW - Memory Management)
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

-- Email Cache Table (NEW - Recent Emails for Context)
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

-- Conversation History Table (NEW - Track User Interactions)
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

-- User Preferences Table (NEW - Settings & Toggles)
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

-- TTS Usage Tracking Table (NEW - for fallback logic)
CREATE TABLE IF NOT EXISTS tts_usage (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    telegram_id BIGINT NOT NULL,
    method VARCHAR(50), -- 'google', 'local'
    characters_generated INT DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (telegram_id) REFERENCES users(telegram_id) ON DELETE CASCADE
);

-- Indexes for Performance
CREATE INDEX IF NOT EXISTS idx_users_telegram_id ON users(telegram_id);
CREATE INDEX IF NOT EXISTS idx_users_email ON users(email);
CREATE INDEX IF NOT EXISTS idx_contacts_telegram_id ON contacts(telegram_id);
CREATE INDEX IF NOT EXISTS idx_contacts_email ON contacts(email_address);
CREATE INDEX IF NOT EXISTS idx_conversation_summaries_telegram_id ON conversation_summaries(telegram_id);
CREATE INDEX IF NOT EXISTS idx_conversation_summaries_date ON conversation_summaries(conversation_date);
CREATE INDEX IF NOT EXISTS idx_email_cache_telegram_id ON email_cache(telegram_id);
CREATE INDEX IF NOT EXISTS idx_conversation_history_telegram_id ON conversation_history(telegram_id);
CREATE INDEX IF NOT EXISTS idx_blocked_users_value ON blocked_users(block_value);