-- Migration: Add missing settings columns to user_preferences
-- voice_preference and auto_check_enabled were missing from user_preferences
-- (they only existed in the users table) causing DB update errors.
ALTER TABLE user_preferences 
    ADD COLUMN IF NOT EXISTS voice_preference VARCHAR(50) DEFAULT 'text',
    ADD COLUMN IF NOT EXISTS auto_check_enabled BOOLEAN DEFAULT TRUE;
