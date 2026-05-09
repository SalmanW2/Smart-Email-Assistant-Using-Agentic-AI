from db.models import db_manager
from typing import List, Dict, Any, Optional
import json

class MemoryManager:
    def __init__(self):
        self.db = db_manager

    async def save_conversation_summary(self, user_id: str, summary: str, facts: List[str]) -> bool:
        data = {
            "user_id": user_id,
            "summary": summary,
            "extracted_facts": json.dumps(facts)
        }
        response = self.db.client.table("conversation_summaries").insert(data).execute()
        return len(response.data) > 0

    async def get_recent_summaries(self, user_id: str, limit: int = 5) -> List[Dict[str, Any]]:
        response = self.db.client.table("conversation_summaries").select("*").eq("user_id", user_id).order("created_at", desc=True).limit(limit).execute()
        return response.data

    async def save_conversation_history(self, user_id: str, message: str, response: str, action: str = None) -> bool:
        data = {
            "user_id": user_id,
            "user_message": message,
            "bot_response": response,
            "action_taken": action
        }
        response = self.db.client.table("conversation_history").insert(data).execute()
        return len(response.data) > 0

    async def get_conversation_context(self, user_id: str) -> str:
        summaries = await self.get_recent_summaries(user_id)
        facts = []
        for summary in summaries:
            facts.extend(json.loads(summary.get("extracted_facts", "[]")))
        
        context = "Recent conversation summaries:\n"
        for summary in summaries:
            context += f"- {summary['summary']}\n"
        
        if facts:
            context += "\nExtracted facts:\n" + "\n".join(f"- {fact}" for fact in facts[:10])  # Limit to 10 facts
        
        return context

    async def save_email_cache(self, user_id: str, email_id: str, subject: str, sender: str, snippet: str) -> bool:
        data = {
            "user_id": user_id,
            "email_id": email_id,
            "subject": subject,
            "sender": sender,
            "snippet": snippet
        }
        response = self.db.client.table("email_cache").insert(data).execute()
        return len(response.data) > 0

    async def get_email_cache(self, user_id: str, email_id: str) -> Optional[Dict[str, Any]]:
        response = self.db.client.table("email_cache").select("*").eq("user_id", user_id).eq("email_id", email_id).execute()
        return response.data[0] if response.data else None

memory_manager = MemoryManager()