-- Migration: Add pagination_limit to user_preferences for dynamic list views
ALTER TABLE user_preferences ADD COLUMN IF NOT EXISTS pagination_limit INT DEFAULT 2;
