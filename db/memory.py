from db.models import supabase
from config import MAX_CONTEXT_MESSAGES, get_utc_now

class MemoryManager:
    @staticmethod
    def get_active_context(telegram_id: int):
        response = (
            supabase.table("conversation_summaries")
            .select("summary_text, key_facts, current_topic")
            .eq("telegram_id", telegram_id)
            .order("created_at", desc=True)
            .limit(MAX_CONTEXT_MESSAGES)
            .execute()
        )
        return response.data if response.data else []

    @staticmethod
    def add_interaction(telegram_id: int, user_msg: str, bot_resp: str, msg_type: str, topic: str = None):
        interaction = {
            "telegram_id": telegram_id,
            "user_message": user_msg,
            "bot_response": bot_resp,
            "interaction_type": msg_type,
            "current_topic": topic,
            "created_at": get_utc_now()
        }
        return supabase.table("conversation_history").insert(interaction).execute()

    @staticmethod
    def get_recent_history(telegram_id: int, limit: int = 10):
        response = (
            supabase.table("conversation_history")
            .select("user_message, bot_response")
            .eq("telegram_id", telegram_id)
            .order("created_at", desc=True)
            .limit(limit)
            .execute()
        )
        return response.data

    @staticmethod
    def save_summary(telegram_id: int, summary_text: str, key_facts: dict, mentioned_emails: list, topic: str):
        summary_data = {
            "telegram_id": telegram_id,
            "summary_text": summary_text,
            "key_facts": key_facts,
            "email_addresses_mentioned": mentioned_emails,
            "current_topic": topic,
            "created_at": get_utc_now()
        }
        return supabase.table("conversation_summaries").insert(summary_data).execute()