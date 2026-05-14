import asyncio
import json
import logging
from typing import Any, Dict, Optional
from google import genai
from google.genai import types
from config import settings
from db.memory import memory_manager
from bot.contact_manager import contact_manager

logger = logging.getLogger(__name__)

class AIEngine:
    def __init__(self) -> None:
        self.memory = memory_manager
        self.contacts = contact_manager
        self.client = genai.Client(api_key=settings.GEMINI_API_KEY)
        self.model_name = "gemini-2.5-flash"
        self.active_chats = {}

    def _parse_error(self, e: Exception) -> str:
        logger.error(f"AI Engine Runtime Error: {str(e)}")
        return f"System Error: {str(e)}"

    async def transcribe_audio(self, file_path: str) -> str:
        """Transcribes voice notes using Gemini's multi-modal audio processing (0 RAM cost)."""
        try:
            sample_file = await asyncio.to_thread(self.client.files.upload, file=file_path)
            prompt = (
                "Transcribe this audio accurately. Do not invent words if it is noisy. "
                "If the audio is completely unintelligible, just output: '[Audio Unclear]'. "
                "Provide ONLY the transcript text."
            )
            response = await asyncio.to_thread(
                self.client.models.generate_content,
                model=self.model_name,
                contents=[sample_file, prompt]
            )
            return response.text.strip()
        except Exception as e:
            return self._parse_error(e)

    async def _get_agent_config(self, user_id: int) -> types.GenerateContentConfig:
        """Constructs the strict behavior guidelines and injects Smart Memory & Contacts."""
        
        # 1. Get Conversation Memory
        memory_prompt = await self.memory.build_memory_prompt(user_id)
        
        # 2. Get Saved Contacts from Database
        try:
            from db.models import db_manager
            res = await db_manager.db.run(lambda: db_manager.db.client.table("contacts").select("*").eq("telegram_id", user_id).execute())
            contacts = getattr(res, 'data', [])
            contact_list = "\n".join([f"- {c['contact_alias']} : {c['email_address']}" for c in contacts])
        except:
            contact_list = "No saved contacts."

        system_instruction = (
            "You are a highly professional, enterprise-grade AI Email Assistant. "
            "You manage the user's Gmail. "
            "CRITICAL RULES:\n"
            "1. COMPOSING: Always confirm the 'To' address, 'Subject', and 'Body' before sending.\n"
            "2. CONCISENESS: Keep responses extremely concise and use clean Markdown formatting.\n\n"
            "=== YOUR SMART MEMORY ===\n"
            f"{memory_prompt}\n\n"
            "=== SAVED CONTACTS ===\n"
            "Use these emails if the user mentions these names:\n"
            f"{contact_list}"
        )

        return types.GenerateContentConfig(
            system_instruction=system_instruction,
            temperature=0.2
        )

    async def agent_chat(self, text: str, user_id: int) -> str:
        if not self.client: return "Error: AI System configuration missing."
        
        try:
            # 1. Background Task: Learn new contacts from the message
            asyncio.create_task(self.contacts.extract_contacts_from_text(user_id, text))

            # 2. Setup or update the chat session with latest memory
            chat_id = str(user_id)
            if chat_id not in self.active_chats:
                config = await self._get_agent_config(user_id)
                self.active_chats[chat_id] = self.client.chats.create(
                    model=self.model_name,
                    config=config
                )

            # 3. Get AI Response
            response = await asyncio.to_thread(self.active_chats[chat_id].send_message, text)
            bot_response = response.text

            # 4. Log interaction
            await self.memory.log_conversation(
                telegram_id=user_id, 
                user_message=text, 
                bot_response=bot_response, 
                interaction_type="chat"
            )

            # 5. Summarize if needed (Background task to save time)
            if await self.memory.should_generate_summary(user_id):
                asyncio.create_task(self._generate_and_save_summary(user_id, text, bot_response))

            return bot_response

        except Exception as e:
            if str(user_id) in self.active_chats:
                del self.active_chats[str(user_id)]
            return self._parse_error(e)

    async def _generate_and_save_summary(self, user_id: int, last_user_msg: str, last_ai_msg: str) -> None:
        try:
            prompt = (
                "Analyze this interaction and generate a JSON summary for long-term memory.\n"
                "Format required:\n"
                "{\n  \"summary_text\": \"Concise summary\",\n  \"key_facts\": [\"fact 1\"],\n  \"current_topic\": \"topic\"\n}\n\n"
                f"User: {last_user_msg}\nAI: {last_ai_msg}"
            )
            
            response = await asyncio.to_thread(
                self.client.models.generate_content,
                model="gemini-2.5-flash-lite",
                contents=prompt
            )
            
            json_str = response.text.replace('```json', '').replace('```', '').strip()
            data = json.loads(json_str)
            
            await self.memory.save_conversation_summary(
                telegram_id=user_id,
                summary_text=data.get("summary_text", "Conversation summary."),
                key_facts=data.get("key_facts", {}),
                email_addresses=[],
                current_topic=data.get("current_topic", "General"),
                tokens_used=0,
                message_count=10
            )
            
            # Reset chat session to force context reload next time
            if str(user_id) in self.active_chats:
                del self.active_chats[str(user_id)]
                
        except Exception as e:
            logger.error(f"Summary Error: {e}")