import asyncio
import json
import logging
import httpx
from typing import Any, Dict, Optional, List
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
        # UNIFIED MODEL: Prevents 429 Quota Burst Errors
        self.model_name = "gemini-2.5-flash" 
        self.active_chats = {}
        self.current_user_id = None

    def _parse_error(self, e: Exception) -> str:
        err_msg = str(e)
        logger.error(f"AI Engine Runtime Error: {err_msg}")
        
        if "429" in err_msg or "RESOURCE_EXHAUSTED" in err_msg:
            return "⏳ *System Limit Reached:* AI processing quota is temporarily exhausted. Please try again later."
        elif "503" in err_msg or "UNAVAILABLE" in err_msg:
            return "🔌 *Server Overload:* AI servers are currently experiencing high traffic. Please retry in 10-20 seconds."
        else:
            return "❌ *System Error:* Unable to process the request at this moment. Please try again later."

    # ==========================================
    # 🛠️ AGENTIC TOOLS (Functions Gemini Can Call)
    # ==========================================
    
    def search_gmail(self, query: str, max_results: int = 5) -> str:
        """Searches the user's Gmail inbox. Use standard Gmail search operators like 'is:unread', 'from:name', or keywords."""
        if not self.current_user_id: 
            return "Error: User context missing."
        import asyncio
        async def _search():
            emails = await self.gmail_client.get_emails(self.current_user_id, query=query, max_results=max_results)
            if not emails: return "No emails found for this query."
            output = []
            for m in emails:
                meta = await self.gmail_client.get_email_metadata(self.current_user_id, m['id'])
                if "error" not in meta:
                    output.append(f"ID: {m['id']} | From: {meta.get('sender')} | Subject: {meta.get('subject')}")
            return "\n".join(output) if output else "Metadata could not be retrieved."
        return asyncio.run(_search())

    def read_gmail_message(self, message_id: str) -> str:
        """Reads the full body content of a specific email using its ID."""
        if not self.current_user_id: 
            return "Error: User context missing."
        import asyncio
        return asyncio.run(self.gmail_client.read_full_email(self.current_user_id, message_id))

    def draft_and_send_email(self, to_email: str, subject: str, body: str) -> str:
        """Sends an email. Call this when the user asks to send or reply to an email."""
        if not self.current_user_id: 
            return "Error: User context missing."
        import asyncio
        res = asyncio.run(self.gmail_client.send_email(self.current_user_id, to_email, subject, body, []))
        return f"Email sent successfully: {res}"

    def save_contact(self, name: str, email: str) -> str:
        """Saves a new contact to the user's database. Call this ONLY when the user tells you someone's email address."""
        if not self.current_user_id: 
            return "Error: User context missing."
        import asyncio
        async def _save():
            from db.models import db_manager
            await db_manager.db.run(lambda: db_manager.db.client.table("contacts").upsert({
                "telegram_id": self.current_user_id,
                "contact_alias": name,
                "email_address": email,
                "contact_name": name
            }, on_conflict="telegram_id,email_address").execute())
            return f"Contact {name} ({email}) saved successfully."
        return asyncio.run(_save())

    # ==========================================
    # CORE AI LOGIC
    # ==========================================

    async def transcribe_audio(self, file_path: str) -> str:
        """Transcribes voice notes using Groq Whisper (Primary) or Gemini (Fallback)."""
        if settings.GROQ_API_KEY:
            try:
                async with httpx.AsyncClient(timeout=30) as client:
                    with open(file_path, "rb") as f:
                        files = {"file": (file_path, f, "audio/ogg")}
                        data = {"model": "whisper-large-v3"}
                        headers = {"Authorization": f"Bearer {settings.GROQ_API_KEY}"}
                        response = await client.post("https://api.groq.com/openai/v1/audio/transcriptions", headers=headers, data=data, files=files)
                        response.raise_for_status()
                        result = response.json()
                        text = result.get("text", "").strip()
                        if text: return text
            except Exception as e:
                logger.warning(f"Groq STT failed, falling back to Gemini: {e}")

        try:
            sample_file = await asyncio.to_thread(self.client.files.upload, file=file_path)
            prompt = "Transcribe this audio accurately. If completely unintelligible, output: '[Audio Unclear]'. Provide ONLY the transcript text."
            response = await asyncio.to_thread(self.client.models.generate_content, model=self.model_name, contents=[sample_file, prompt])
            return response.text.strip()
        except Exception as e:
            return self._parse_error(e)

    def _get_agent_config(self, memory_prompt: str) -> types.GenerateContentConfig:
        system_instruction = (
            "You are an Agentic AI Email Assistant. YOU HAVE TOOLS TO INTERACT WITH GMAIL AND DATABASE.\n"
            "CRITICAL RULES:\n"
            "1. INBOX ACCESS: You CAN search and read emails. MUST call `search_gmail` tool first, then optionally `read_gmail_message`.\n"
            "2. SENDING: To send or reply to an email, MUST call `draft_and_send_email` tool.\n"
            "3. CONTACTS: If the user provides an email address for a name, MUST call `save_contact` tool immediately.\n"
            "4. NEVER SAY 'I cannot access your inbox'. You are a fully integrated Agent. Use your tools!\n"
            "5. CONCISENESS: Keep conversational responses extremely brief and use Markdown.\n\n"
            f"{memory_prompt}"
        )
        return types.GenerateContentConfig(
            system_instruction=system_instruction,
            temperature=0.2,
            tools=[self.search_gmail, self.read_gmail_message, self.draft_and_send_email, self.save_contact]
        )

    async def agent_chat(self, text: str, user_id: int) -> str:
        if not self.client: return "Error: AI System configuration missing."
        self.current_user_id = user_id 
        
        try:
            # Passive background task for parsing explicit contacts
            asyncio.create_task(self.contact_manager.extract_contacts_from_text(user_id, text))
            
            memory_prompt = await self.memory.build_memory_prompt(user_id)
            chat_id = str(user_id)

            def _execute_chat():
                if chat_id not in self.active_chats:
                    config = self._get_agent_config(memory_prompt)
                    self.active_chats[chat_id] = self.client.chats.create(model=self.model_name, config=config)
                return self.active_chats[chat_id].send_message(text).text

            bot_response = await asyncio.to_thread(_execute_chat)

            await self.memory.log_conversation(telegram_id=user_id, user_message=text, bot_response=bot_response, interaction_type="chat")

            if await self.memory.should_generate_summary(user_id):
                asyncio.create_task(self._generate_and_save_summary(user_id, text, bot_response))

            return bot_response
            
        except Exception as e:
            if str(user_id) in self.active_chats: del self.active_chats[str(user_id)] 
            return self._parse_error(e)

    async def _generate_and_save_summary(self, user_id: int, last_user_msg: str, last_ai_msg: str) -> None:
        try:
            prompt = (
                "Analyze this recent interaction and generate a JSON summary for long-term memory.\n"
                "Format required: {\"summary_text\": \"Concise summary\", \"key_facts\": [\"fact 1\"], \"email_addresses_mentioned\": [\"email@example.com\"], \"current_topic\": \"topic\"}\n\n"
                f"User: {last_user_msg}\nAI: {last_ai_msg}"
            )
            response = await asyncio.to_thread(self.client.models.generate_content, model=self.model_name, contents=prompt)
            json_str = response.text.replace('```json', '').replace('```', '').strip()
            data = json.loads(json_str)
            
            await self.memory.save_conversation_summary(
                telegram_id=user_id, summary_text=data.get("summary_text", "Conversation summary."),
                key_facts=data.get("key_facts", {}), email_addresses=data.get("email_addresses_mentioned", []),
                current_topic=data.get("current_topic", "General"), tokens_used=0, message_count=10
            )
        except Exception as e:
            logger.error(f"Memory Summary Engine Error: {e}")

    async def process_attachment(self, telegram_id: int, file_path: str, query: str) -> str:
        try:
            prompt = f"Summarize or accurately answer the following request regarding this document:\n{query}"
            config = types.GenerateContentConfig(temperature=0.2, system_instruction="You are a highly capable document analysis assistant.")
            sample_file = await asyncio.to_thread(self.client.files.upload, file=file_path)
            response = await asyncio.to_thread(self.client.models.generate_content, model=self.model_name, contents=[sample_file, prompt], config=config)
            return response.text
        except Exception as e:
            return self._parse_error(e)

    async def generate_smart_replies(self, email_body: str) -> List[str]:
        """Analyzes an incoming email and generates 3 short suggested replies."""
        try:
            prompt = (
                "You are an AI Email Assistant. Read the following email and generate exactly 3 short, "
                "professional, and distinct quick reply options (maximum 4-5 words each). "
                "Return ONLY a valid JSON array of strings. Example: [\"Received, thank you.\", \"I will check and revert.\", \"Noted.\"]\n\n"
                f"Email Body:\n{email_body[:2000]}"
            )
            response = await asyncio.to_thread(self.client.models.generate_content, model=self.model_name, contents=prompt)
            json_str = response.text.replace('```json', '').replace('```', '').strip()
            replies = json.loads(json_str)
            return replies if isinstance(replies, list) and len(replies) > 0 else ["Thanks!", "Noted.", "I'll reply soon."]
        except Exception as e:
            logger.error(f"Smart Reply Generation Error: {e}")
            return ["Got it.", "Thanks for the update.", "Will review shortly."]