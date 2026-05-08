"""
Memory Management System
Handles conversation context, summaries, and LLM memory optimization
"""

import logging
from typing import Optional, List, Dict, Any
from datetime import datetime, timedelta
from config import (
    SUPABASE_URL, SUPABASE_KEY, MAX_CONTEXT_MESSAGES, 
    SUMMARY_GENERATION_THRESHOLD, get_utc_now, get_utc_date
)
from supabase import create_client

supabase = create_client(SUPABASE_URL, SUPABASE_KEY)
logger = logging.getLogger(__name__)

class ConversationMemory:
    """Manages long-term conversation context and memory."""
    
    @staticmethod
    def log_conversation(
        telegram_id: int,
        user_message: str,
        bot_response: str,
        interaction_type: str = "text",
        related_email_id: Optional[str] = None,
        related_contact_id: Optional[str] = None,
        current_topic: Optional[str] = None
    ) -> bool:
        """Logs user interaction to database."""
        try:
            supabase.table("conversation_history").insert({
                "telegram_id": telegram_id,
                "user_message": user_message,
                "bot_response": bot_response,
                "interaction_type": interaction_type,
                "related_email_id": related_email_id,
                "related_contact_id": related_contact_id,
                "current_topic": current_topic,
                "created_at": get_utc_now()
            }).execute()
            return True
        except Exception as e:
            logger.error(f"Conversation log error: {e}")
            return False

    @staticmethod
    def get_recent_context(telegram_id: int, days: int = 1) -> str:
        """Fetches recent conversation summaries for context."""
        try:
            target_date = (datetime.utcnow() - timedelta(days=days)).date()
            res = supabase.table("conversation_summaries").select(
                "summary_text,current_topic,key_facts"
            ).eq("telegram_id", telegram_id).gte(
                "conversation_date", target_date
            ).order("conversation_date", desc=True).limit(MAX_CONTEXT_MESSAGES).execute()
            
            if not res.data:
                return ""
            
            context = "Recent Conversation Context:\n"
            for summary in res.data:
                topic = summary.get("current_topic", "General")
                text = summary.get("summary_text", "")
                context += f"\n[{topic}]: {text}"
            
            return context
        except Exception as e:
            logger.error(f"Context fetch error: {e}")
            return ""

    @staticmethod
    def get_conversation_history(telegram_id: int, limit: int = 10) -> List[Dict]:
        """Fetches raw conversation history."""
        try:
            res = supabase.table("conversation_history").select(
                "*"
            ).eq("telegram_id", telegram_id).order(
                "created_at", desc=True
            ).limit(limit).execute()
            return res.data[::-1]  # Reverse to get chronological order
        except Exception as e:
            logger.error(f"History fetch error: {e}")
            return []

    @staticmethod
    def generate_summary(
        telegram_id: int,
        conversation_date: str,
        summary_text: str,
        key_facts: Dict[str, Any],
        email_addresses: List[str],
        current_topic: Optional[str] = None,
        tokens_used: int = 0,
        message_count: int = 0
    ) -> bool:
        """Generates and saves conversation summary."""
        try:
            # Check if summary for today already exists
            existing = supabase.table("conversation_summaries").select(
                "id"
            ).eq("telegram_id", telegram_id).eq(
                "conversation_date", conversation_date
            ).execute()
            
            data = {
                "telegram_id": telegram_id,
                "conversation_date": conversation_date,
                "summary_text": summary_text,
                "key_facts": key_facts,
                "email_addresses_mentioned": email_addresses,
                "current_topic": current_topic,
                "tokens_used": tokens_used,
                "message_count": message_count,
                "created_at": get_utc_now()
            }
            
            if existing.data:
                # Update existing summary
                supabase.table("conversation_summaries").update(data).eq(
                    "id", existing.data[0]["id"]
                ).execute()
            else:
                # Create new summary
                supabase.table("conversation_summaries").insert(data).execute()
            
            return True
        except Exception as e:
            logger.error(f"Summary generation error: {e}")
            return False

    @staticmethod
    def get_today_message_count(telegram_id: int) -> int:
        """Gets today's message count for summary generation threshold."""
        try:
            res = supabase.table("conversation_history").select(
                "id", count="exact"
            ).eq("telegram_id", telegram_id).gte(
                "created_at", f"{get_utc_date()}T00:00:00"
            ).execute()
            return res.count or 0
        except Exception as e:
            logger.error(f"Message count error: {e}")
            return 0

    @staticmethod
    def should_generate_summary(telegram_id: int) -> bool:
        """Checks if summary should be generated based on message threshold."""
        count = ConversationMemory.get_today_message_count(telegram_id)
        return count >= SUMMARY_GENERATION_THRESHOLD

    @staticmethod
    def get_current_topic(telegram_id: int) -> Optional[str]:
        """Gets the current topic of conversation."""
        try:
            res = supabase.table("conversation_summaries").select(
                "current_topic"
            ).eq("telegram_id", telegram_id).eq(
                "conversation_date", str(get_utc_date())
            ).order("created_at", desc=True).limit(1).execute()
            
            if res.data:
                return res.data[0].get("current_topic")
            return None
        except Exception as e:
            logger.error(f"Topic fetch error: {e}")
            return None

    @staticmethod
    def update_current_topic(telegram_id: int, topic: str) -> bool:
        """Updates the current topic for today's conversation."""
        try:
            today = str(get_utc_date())
            res = supabase.table("conversation_summaries").select(
                "id"
            ).eq("telegram_id", telegram_id).eq(
                "conversation_date", today
            ).execute()
            
            if res.data:
                supabase.table("conversation_summaries").update({
                    "current_topic": topic
                }).eq("id", res.data[0]["id"]).execute()
            else:
                supabase.table("conversation_summaries").insert({
                    "telegram_id": telegram_id,
                    "conversation_date": today,
                    "current_topic": topic,
                    "created_at": get_utc_now()
                }).execute()
            
            return True
        except Exception as e:
            logger.error(f"Topic update error: {e}")
            return False

class EmailCache:
    """Manages email caching for context and quick access."""
    
    @staticmethod
    def cache_email(
        telegram_id: int,
        gmail_message_id: str,
        sender: str,
        sender_email: str,
        subject: str,
        preview: str
    ) -> bool:
        """Caches an email for quick reference."""
        try:
            supabase.table("email_cache").insert({
                "telegram_id": telegram_id,
                "gmail_message_id": gmail_message_id,
                "sender": sender,
                "sender_email": sender_email,
                "subject": subject,
                "preview": preview[:200],  # Limit preview
                "received_at": get_utc_now(),
                "cached_at": get_utc_now(),
                "full_body_cached": False
            }).execute()
            return True
        except Exception as e:
            logger.error(f"Email cache error: {e}")
            return False

    @staticmethod
    def get_cached_emails(telegram_id: int, limit: int = 10) -> List[Dict]:
        """Gets cached emails."""
        try:
            res = supabase.table("email_cache").select(
                "*"
            ).eq("telegram_id", telegram_id).order(
                "received_at", desc=True
            ).limit(limit).execute()
            return res.data
        except Exception as e:
            logger.error(f"Cache fetch error: {e}")
            return []

    @staticmethod
    def clear_old_cache(telegram_id: int, days: int = 7) -> bool:
        """Deletes old cached emails."""
        try:
            old_date = (datetime.utcnow() - timedelta(days=days)).isoformat()
            supabase.table("email_cache").delete().eq(
                "telegram_id", telegram_id
            ).lt("cached_at", old_date).execute()
            return True
        except Exception as e:
            logger.error(f"Cache clear error: {e}")
            return False