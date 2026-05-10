import asyncio
import json
import logging
from typing import Any, Dict, Optional
from google import genai
from google.genai import types
from config import settings
from db.memory import memory_manager
from bot.contact_manager import contact_manager
from bot.gmail_client import GmailClient

logger = logging.getLogger(__name__)

class AIEngine:
    def __init__(self) -> None:
        self.memory = memory_manager
        self.contact_manager = contact_manager
        self.gmail_client = GmailClient()
        self.client = genai.Client(api_key=settings.GEMINI_API_KEY)
        self.model_name = "gemini-2.5-flash"
        self.active_chats = {}

    def _parse_error(self, e: Exception) -> str:
        logger.error(f"AI Engine Runtime Error: {str(e)}")
        return f"System Error: {str(e)}"

    async def transcribe_audio(self, file_path: str) -> str:
        """Transcribes voice notes using the LLM's multi-modal capabilities."""
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

    async def get_search_query(self, user_text: str) -> str:
        """Converts natural language into a strict Gmail search query."""
        try:
            prompt = (
                "Convert this user request into a strict Gmail search query. "
                "Reply ONLY with the query string, nothing else.\n"
                f"User: {user_text}\n"
                "Examples:\nUser: search for emails from ali\nAI: from:ali\n"
                "User: find project emails\nAI: project"
            )
            response = await asyncio.to_thread(
                self.client.models.generate_content,
                model=self.model_name,
                contents=prompt
            )
            return response.text.strip()
        except Exception as e:
            logger.error(f"Search Query Gen Error: {e}")
            return ""

    def _get_agent_config(self, memory_prompt: str) -> types.GenerateContentConfig:
        """Constructs the strict behavior guidelines and memory context for the agent."""
        system_instruction = (
            "You are a highly professional, enterprise-grade AI Email Assistant. "
            "You manage the user's Gmail. "
            "CRITICAL RULES:\n"
            "1. COMPOSING: Always confirm the 'To' address, 'Subject', and 'Body' with the user before sending, unless explicitly told to send immediately.\n"
            "2. SEARCHING: Summarize results professionally (sender, subject, brief context).\n"
            "3. READING: Present email content clearly and extract action items if present.\n"
            "4. CONCISENESS: Keep responses extremely concise and use clean Markdown formatting.\n"
            "5. CONTACTS: Rely on the provided user memory to resolve names to email addresses.\n\n"
            f"{memory_prompt}"
        )

        return types.GenerateContentConfig(
            system_instruction=system_instruction,
            temperature=0.2
        )

    async def agent_chat(self, text: str, user_id: int) -> str:
        """Main interaction pipeline. Handles memory context, chat execution, and logging."""
        if not self.client:
            return "Error: AI System configuration missing."
        
        try:
            # 1. Proactively scan for and save new contacts
            await self.contact_manager.extract_contacts_from_text(user_id, text)

            # 2. Rebuild intelligent memory context to save tokens
            memory_prompt = await self.memory.build_memory_prompt(user_id)

            # 3. Setup or update the session
            chat_id = str(user_id)
            if chat_id not in self.active_chats:
                config = self._get_agent_config(memory_prompt)
                self.active_chats[chat_id] = self.client.chats.create(
                    model=self.model_name,
                    config=config
                )

            # 4. Generate the response
            response = await asyncio.to_thread(self.active_chats[chat_id].send_message, text)
            bot_response = response.text

            # 5. Log the interaction to Supabase Memory Table
            await self.memory.log_conversation(
                telegram_id=user_id, 
                user_message=text, 
                bot_response=bot_response, 
                interaction_type="chat"
            )

            # 6. Dynamically summarize memory if threshold is reached
            if await self.memory.should_generate_summary(user_id):
                await self._generate_and_save_summary(user_id, text, bot_response)

            return bot_response

        except Exception as e:
            if str(user_id) in self.active_chats:
                del self.active_chats[str(user_id)]  # Reset corrupted sessions
            return self._parse_error(e)

    async def _generate_and_save_summary(self, user_id: int, last_user_msg: str, last_ai_msg: str) -> None:
        """Summarizes recent chat activity into JSON and stores it to prevent token bloat."""
        try:
            prompt = (
                "Analyze this recent interaction and generate a JSON summary for long-term memory.\n"
                "Format required:\n"
                "{\n"
                "  \"summary_text\": \"Concise summary of what occurred\",\n"
                "  \"key_facts\": [\"extracted fact 1\", \"fact 2\"],\n"
                "  \"email_addresses_mentioned\": [\"email@example.com\"],\n"
                "  \"current_topic\": \"Main topic\"\n"
                "}\n\n"
                f"User: {last_user_msg}\nAI: {last_ai_msg}"
            )
            
            response = await asyncio.to_thread(
                self.client.models.generate_content,
                model="gemini-2.5-flash-lite",
                contents=prompt
            )
            
            # Safely extract and parse JSON payload
            json_str = response.text.replace('```json', '').replace('```', '').strip()
            data = json.loads(json_str)
            
            await self.memory.save_conversation_summary(
                telegram_id=user_id,
                summary_text=data.get("summary_text", "Conversation summary."),
                key_facts=data.get("key_facts", {}),
                email_addresses=data.get("email_addresses_mentioned", []),
                current_topic=data.get("current_topic", "General"),
                tokens_used=0,
                message_count=10
            )
        except Exception as e:
            logger.error(f"Memory Summary Engine Error: {e}")

    async def process_attachment(self, telegram_id: int, file_path: str, query: str) -> str:
        """Analyzes uploaded documents (PDFs, Images) using Vision/Multi-modal capabilities."""
        try:
            prompt = f"Summarize or accurately answer the following request regarding this document:\n{query}"
            
            config = types.GenerateContentConfig(
                temperature=0.2,
                system_instruction="You are a highly capable document analysis assistant. Provide accurate, professional answers."
            )
            
            sample_file = await asyncio.to_thread(self.client.files.upload, file=file_path)
            
            response = await asyncio.to_thread(
                self.client.models.generate_content,
                model=self.model_name,
                contents=[sample_file, prompt],
                config=config
            )
            return response.text
        except Exception as e:
            return self._parse_error(e)