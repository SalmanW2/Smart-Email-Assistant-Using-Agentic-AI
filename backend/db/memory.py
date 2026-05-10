import asyncio
import json
from typing import List, Dict, Any, Optional
from cachetools import TTLCache
from config import settings
from db.models import db_manager

class MemoryManager:
    def __init__(self):
        self.db = db_manager
        # TTL Cache for 1 hour to reduce database calls
        self.cache = TTLCache(maxsize=1000, ttl=3600)

    def _safe_data(self, result):
        return getattr(result, 'data', None) if result else None

    async def get_recent_summaries(self, telegram_id: int, limit: int = settings.MAX_CONTEXT_MESSAGES) -> List[Dict[str, Any]]:
        """Fetch the most recent conversation summaries for LLM context."""
        cache_key = f"summaries_{telegram_id}_{limit}"
        if cache_key in self.cache:
            return self.cache[cache_key]

        try:
            result = await self.db.db.run(lambda: self.db.db.client.table("conversation_summaries")
                                         .select("*")
                                         .eq("telegram_id", telegram_id)
                                         .order("created_at", desc=True)
                                         .limit(limit)
                                         .execute())
            data = self._safe_data(result) or []
            summaries = data[::-1]  # Reverse to chronological order
            self.cache[cache_key] = summaries
            return summaries
        except Exception as e:
            print(f"DB Error in get_recent_summaries: {e}")
            return []

    async def save_conversation_summary(self, telegram_id: int, summary_text: str, key_facts: Dict[str, Any],
                                       email_addresses: List[str], current_topic: str, tokens_used: int, message_count: int) -> bool:
        """Save a new conversation summary to the database."""
        try:
            await self.db.db.run(lambda: self.db.db.client.table("conversation_summaries").insert({
                "telegram_id": telegram_id,
                "summary_text": summary_text,
                "key_facts": key_facts,
                "email_addresses_mentioned": email_addresses,
                "current_topic": current_topic,
                "tokens_used": tokens_used,
                "message_count": message_count
            }).execute())
            
            # Invalidate cache for this user
            for key in list(self.cache.keys()):
                if f"summaries_{telegram_id}" in key:
                    del self.cache[key]
            return True
        except Exception as e:
            print(f"DB Error in save_conversation_summary: {e}")
            return False

    async def get_current_topic(self, telegram_id: int) -> Optional[str]:
        """Get the most recent topic discussed by the user."""
        try:
            result = await self.db.db.run(lambda: self.db.db.client.table("conversation_summaries")
                                         .select("current_topic")
                                         .eq("telegram_id", telegram_id)
                                         .order("created_at", desc=True)
                                         .limit(1)
                                         .execute())
            data = self._safe_data(result)
            if data:
                return data[0].get("current_topic")
            return None
        except Exception as e:
            print(f"DB Error in get_current_topic: {e}")
            return None

    async def build_memory_prompt(self, telegram_id: int) -> str:
        """Build a memory prompt from recent summaries for the LLM."""
        summaries = await self.get_recent_summaries(telegram_id)
        if not summaries:
            return "No prior conversation memory available."

        prompt_lines = ["User memory context:"]
        for item in summaries:
            facts = item.get("key_facts") or []
            if isinstance(facts, str):
                try:
                    facts = json.loads(facts)
                except json.JSONDecodeError:
                    facts = [facts]

            prompt_lines.append(f"Summary: {item.get('summary_text', '')}")
            if facts:
                prompt_lines.append(f"Facts: {', '.join(facts[:5])}")
            if item.get("current_topic"):
                prompt_lines.append(f"Topic: {item.get('current_topic', '')}")

        return "\n".join(prompt_lines)

    async def log_conversation(self, telegram_id: int, user_message: str, bot_response: str,
                              interaction_type: str, related_email_id: Optional[str] = None,
                              related_contact_id: Optional[str] = None, current_topic: Optional[str] = None) -> bool:
        """Log a conversation interaction for analytics and memory."""
        try:
            await self.db.db.run(lambda: self.db.db.client.table("conversation_history").insert({
                "telegram_id": telegram_id,
                "user_message": user_message,
                "bot_response": bot_response,
                "interaction_type": interaction_type,
                "related_email_id": related_email_id,
                "related_contact_id": related_contact_id,
                "current_topic": current_topic
            }).execute())
            return True
        except Exception as e:
            print(f"DB Error in log_conversation: {e}")
            return False

    async def should_generate_summary(self, telegram_id: int) -> bool:
        """Check if we should generate a new summary based on message count."""
        try:
            result = await self.db.db.run(lambda: self.db.db.client.table("conversation_history")
                                         .select("id")
                                         .eq("telegram_id", telegram_id)
                                         .gte("created_at", f"{settings.get_utc_date()} 00:00:00")
                                         .execute())
            data = self._safe_data(result) or []
            return len(data) >= settings.SUMMARY_GENERATION_THRESHOLD
        except Exception as e:
            print(f"DB Error in should_generate_summary: {e}")
            return False

    async def cache_email(self, telegram_id: int, gmail_message_id: str, sender: str, sender_email: str,
                         subject: str, preview: str, received_at: str) -> bool:
        """Cache recent email for context."""
        try:
            await self.db.db.run(lambda: self.db.db.client.table("email_cache").upsert({
                "telegram_id": telegram_id,
                "gmail_message_id": gmail_message_id,
                "sender": sender,
                "sender_email": sender_email,
                "subject": subject,
                "preview": preview,
                "received_at": received_at
            }).execute())
            
            # Invalidate cache for this user
            for key in list(self.cache.keys()):
                if f"emails_{telegram_id}" in key:
                    del self.cache[key]
            return True
        except Exception as e:
            print(f"DB Error in cache_email: {e}")
            return False

    async def get_cached_emails(self, telegram_id: int, limit: int = 10) -> List[Dict[str, Any]]:
        """Get cached emails for context."""
        cache_key = f"emails_{telegram_id}_{limit}"
        if cache_key in self.cache:
            return self.cache[cache_key]

        try:
            result = await self.db.db.run(lambda: self.db.db.client.table("email_cache")
                                         .select("*")
                                         .eq("telegram_id", telegram_id)
                                         .order("received_at", desc=True)
                                         .limit(limit)
                                         .execute())
            emails = self._safe_data(result) or []
            self.cache[cache_key] = emails
            return emails
        except Exception as e:
            print(f"DB Error in get_cached_emails: {e}")
            return []

memory_manager = MemoryManager()