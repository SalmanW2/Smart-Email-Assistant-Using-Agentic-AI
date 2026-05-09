import json
from typing import Any, Dict, List, Optional
from db.models import db_manager

class MemoryManager:
    def __init__(self) -> None:
        self.db = db_manager

    async def save_conversation_summary(self, telegram_id: int, summary_text: str, key_facts: List[str], current_topic: str | None = None) -> bool:
        payload = {
            "telegram_id": telegram_id,
            "summary_text": summary_text,
            "key_facts": key_facts,
            "current_topic": current_topic,
        }

        def action():
            return self.db.db.client.table("conversation_summaries").insert(payload).execute()

        response = await self.db.db.run(action)
        return bool(response.data)

    async def get_recent_summaries(self, telegram_id: int, limit: int = 5) -> List[Dict[str, Any]]:
        def action():
            return (
                self.db.db.client.table("conversation_summaries")
                .select("*")
                .eq("telegram_id", telegram_id)
                .order("created_at", desc=True)
                .limit(limit)
                .execute()
            )

        response = await self.db.db.run(action)
        return response.data or []

    async def save_conversation_history(self, telegram_id: int, user_message: str, bot_response: str, interaction_type: str = "chat") -> bool:
        payload = {
            "telegram_id": telegram_id,
            "user_message": user_message,
            "bot_response": bot_response,
            "interaction_type": interaction_type,
        }

        def action():
            return self.db.db.client.table("conversation_history").insert(payload).execute()

        response = await self.db.db.run(action)
        return bool(response.data)

    async def build_memory_prompt(self, telegram_id: int) -> str:
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

            prompt_lines.append(f"Summary: {item['summary_text']}")
            if facts:
                prompt_lines.append(f"Facts: {', '.join(facts[:5])}")
            if item.get("current_topic"):
                prompt_lines.append(f"Topic: {item['current_topic']}")

        return "\n".join(prompt_lines)

memory_manager = MemoryManager()