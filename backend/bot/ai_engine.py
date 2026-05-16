import asyncio
import json
import logging
import httpx
from datetime import datetime, timezone
from typing import Any, Dict, Optional, List
from google import genai
from google.genai import types
from config import settings
from db.memory import memory_manager
from bot.contact_manager import contact_manager
from bot.gmail_client import GmailClient
from db.models import db_manager

logger = logging.getLogger(__name__)

class AIEngine:
    def __init__(self) -> None:
        self.memory = memory_manager
        self.contact_manager = contact_manager
        self.gmail_client = GmailClient()
        self.db = db_manager
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
        try:
            return asyncio.run(_search())
        except Exception as e:
            return f"Error during search: {e}"

    def read_gmail_message(self, message_id: str) -> str:
        """Reads the full body content of a specific email using its ID."""
        if not self.current_user_id: 
            return "Error: User context missing."
        import asyncio
        try:
            return asyncio.run(self.gmail_client.read_full_email(self.current_user_id, message_id))
        except Exception as e:
            return f"Error reading email: {e}"

    def draft_and_send_email(self, to_email: str, subject: str, body: str) -> str:
        """Sends an email immediately. Call this when the user asks to send or reply to an email right now."""
        if not self.current_user_id: 
            return "Error: User context missing."
        import asyncio
        try:
            res = asyncio.run(self.gmail_client.send_email(self.current_user_id, to_email, subject, body, []))
            return f"Email sent successfully: {res}"
        except Exception as e:
            return f"Error sending email: {e}"

    def schedule_email(self, to_email: str, subject: str, body: str, send_time_utc: str) -> str:
        """
        Schedules an email to be sent later. Call this if the user says 'send tomorrow', 'send at 9am', etc.
        'send_time_utc' MUST be formatted as 'YYYY-MM-DD HH:MM:SS' in UTC timezone.
        """
        if not self.current_user_id: 
            return "Error: User context missing."
        import asyncio
        async def _schedule():
            await self.db.db.run(lambda: self.db.db.client.table("scheduled_emails").insert({
                "telegram_id": self.current_user_id,
                "to_email": to_email,
                "subject": subject,
                "body": body,
                "scheduled_time": send_time_utc
            }).execute())
            return f"Email successfully scheduled for {send_time_utc} UTC."
        try:
            return asyncio.run(_schedule())
        except Exception as e:
            return f"Error scheduling email: {e}"

    def save_contact(self, name: str, email: str) -> str:
        """Saves a new contact to the user's database. Call this ONLY when the user tells you someone's email address."""
        if not self.current_user_id: 
            return "Error: User context missing."
        import asyncio
        async def _save():
            await self.db.db.run(lambda: self.db.db.client.table("contacts").upsert({
                "telegram_id": self.current_user_id,
                "contact_alias": name,
                "email_address": email,
                "contact_name": name
            }, on_conflict="telegram_id,email_address").execute())
            return f"Contact {name} ({email}) saved successfully."
        try:
            return asyncio.run(_save())
        except Exception as e:
            return f"Error saving contact: {e}"

    def read_memory_document(self, query: str) -> str:
        """
        Reads and analyzes the document/image the user recently uploaded. 
        Call this when the user asks 'read the file I just sent' or 'what is in the invoice'.
        """
        if not self.current_user_id: 
            return "Error: User context missing."
        import asyncio
        async def _read():
            files = self.gmail_client.get_user_attachments(self.current_user_id)
            if not files:
                return "Error: No files found in memory. Please tell the user to upload the document first."
            latest_file = files[-1]
            return await self.process_attachment(self.current_user_id, latest_file, query)
        try:
            return asyncio.run(_read())
        except Exception as e:
            return f"Error reading document: {e}"

    # ==========================================
    # CORE AI LOGIC
    # ==========================================

    async def transcribe_audio(self, file_path: str, user_id: int) -> str:
        """Transcribes voice notes using Groq Whisper (Primary) or Gemini (Fallback) and tracks usage."""
        text_result = ""
        method_used = "groq_whisper"
        
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
                        text_result = result.get("text", "").strip()
            except Exception as e:
                logger.warning(f"Groq STT failed, falling back to Gemini: {e}")
                text_result = ""

        if not text_result:
            try:
                method_used = "gemini_fallback"
                sample_file = await asyncio.to_thread(self.client.files.upload, file=file_path)
                prompt = "Transcribe this audio accurately. If completely unintelligible, output: '[Audio Unclear]'. Provide ONLY the transcript text."
                response = await asyncio.to_thread(self.client.models.generate_content, model=self.model_name, contents=[sample_file, prompt])
                text_result = response.text.strip()
            except Exception as e:
                return self._parse_error(e)

        # STT Usage Tracking (Estimated duration based on text length: ~15 chars = 1 sec)
        if text_result and "[Audio Unclear]" not in text_result:
            try:
                est_seconds = max(1, len(text_result) // 15)
                await self.db.db.run(lambda: self.db.db.client.table("stt_usage").insert({
                    "telegram_id": user_id,
                    "method": method_used,
                    "duration_seconds": est_seconds
                }).execute())
            except Exception as e:
                logger.error(f"Failed to log STT usage: {e}")

        return text_result

    def _get_agent_config(self, memory_prompt: str) -> types.GenerateContentConfig:
        current_utc = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
        system_instruction = (
            f"You are an Agentic AI Email Assistant. Current Time: {current_utc}\n"
            "YOU HAVE TOOLS TO INTERACT WITH GMAIL AND DATABASE. CRITICAL RULES:\n"
            "1. INBOX: You CAN search and read emails. Call `search_gmail` first, then optionally `read_gmail_message`.\n"
            "2. SENDING (NOW): To send an email immediately, call `draft_and_send_email`.\n"
            "3. SENDING (LATER): If user says 'send later' or specifies a time, calculate the exact UTC time and call `schedule_email`.\n"
            "4. DOCUMENTS: If user asks about a file/image they uploaded, call `read_memory_document`.\n"
            "5. CONTACTS: If user provides an email address for a name, call `save_contact`.\n"
            "6. Keep responses concise, professional, and use Markdown formatting.\n"
            "7. Do NOT generate long unnecessary paragraphs. Be helpful and direct.\n\n"
            f"{memory_prompt}"
        )
        return types.GenerateContentConfig(
            system_instruction=system_instruction,
            temperature=0.2,
            tools=[self.search_gmail, self.read_gmail_message, self.draft_and_send_email, self.schedule_email, self.save_contact, self.read_memory_document]
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