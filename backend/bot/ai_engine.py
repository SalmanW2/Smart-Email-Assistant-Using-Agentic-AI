import asyncio
import json
import logging
import httpx
import re
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

# Dedicated thread-local event loop for sync tool execution
# (Gemini calls tools synchronously from within an async context,
#  so asyncio.run() would crash. We use a dedicated background loop instead.)
import threading

_tool_loop: asyncio.AbstractEventLoop | None = None
_tool_loop_lock = threading.Lock()

def _get_tool_loop() -> asyncio.AbstractEventLoop:
    global _tool_loop
    with _tool_loop_lock:
        if _tool_loop is None or _tool_loop.is_closed():
            _tool_loop = asyncio.new_event_loop()
            t = threading.Thread(target=_tool_loop.run_forever, daemon=True)
            t.start()
        return _tool_loop

def _run_sync(coro) -> Any:
    """Run an async coroutine from sync context using the dedicated tool loop."""
    loop = _get_tool_loop()
    future = asyncio.run_coroutine_threadsafe(coro, loop)
    return future.result(timeout=30)


class AIEngine:
    def __init__(self) -> None:
        self.memory          = memory_manager
        self.contact_manager = contact_manager
        self.gmail_client    = GmailClient()
        self.db              = db_manager
        self.client          = genai.Client(api_key=settings.GEMINI_API_KEY)
        self.model_name      = "gemini-2.5-flash"
        self.active_chats:   dict = {}
        self.current_user_id: int | None = None
        self.pending_drafts: dict = {}

    def _parse_error(self, e: Exception) -> str:
        err = str(e)
        logger.error(f"AI Engine error: {err}")
        if "429" in err or "RESOURCE_EXHAUSTED" in err:
            return json.dumps({"text": "⏳ *Quota Limit:* AI quota temporarily exhausted. Please retry in a moment.", "response_type": "text"})
        if "503" in err or "UNAVAILABLE" in err:
            return json.dumps({"text": "🔌 *Server Overload:* AI servers are busy. Please retry in 10–20 seconds.", "response_type": "text"})
        return json.dumps({"text": "❌ *System Error:* Unable to process request. Please try again.", "response_type": "text"})

    # ──────────────────────────────────────────────────────────
    # AGENTIC TOOLS  (Gemini calls these synchronously)
    # All async DB/HTTP calls go through _run_sync()
    # ──────────────────────────────────────────────────────────

    def search_gmail(self, query: str, max_results: int = 5) -> str:
        """Search Gmail for emails matching a query string."""
        if not self.current_user_id:
            return "Error: User context missing."
        async def _inner():
            emails = await self.gmail_client.get_emails(
                self.current_user_id, query=query, max_results=max_results)
            if not emails:
                return "No emails found for this query."
            output = []
            for m in emails:
                meta = await self.gmail_client.get_email_metadata(self.current_user_id, m["id"])
                if "error" not in meta:
                    output.append(
                        f"ID: {m['id']} | From: {meta.get('sender')} | Subject: {meta.get('subject')}")
            return "\n".join(output) if output else "Could not retrieve email metadata."
        try:
            return _run_sync(_inner())
        except Exception as e:
            return f"Error during search: {e}"

    def read_gmail_message(self, message_id: str) -> str:
        """Read the full body of a specific Gmail message by its ID."""
        if not self.current_user_id:
            return "Error: User context missing."
        try:
            return _run_sync(
                self.gmail_client.read_full_email(self.current_user_id, message_id))
        except Exception as e:
            return f"Error reading email: {e}"

    def prepare_email_draft(self, to_email: str, subject: str, body: str) -> str:
        """Prepare an email draft for the user to review before sending. Always use this instead of sending directly."""
        if not self.current_user_id:
            return "Error: User context missing."
        
        # HITL Interceptor: Strict enforcement of recipient placeholder if empty or unknown
        if not to_email or not to_email.strip() or "example.com" in to_email.lower() or "unknown" in to_email.lower():
            to_email = "[Specify Recipient Email]"
            
        self.pending_drafts[self.current_user_id] = {
            "to":      to_email,
            "subject": subject,
            "body":    body,
        }
        return "Draft prepared successfully. Inform the user that the draft is ready for their review."

    def schedule_email(self, to_email: str, subject: str, body: str, send_time_utc: str) -> str:
        """Schedule an email to be sent at a specific UTC time in format 'YYYY-MM-DD HH:MM:SS'."""
        if not self.current_user_id:
            return "Error: User context missing."
        async def _inner():
            await self.db.db.run(
                lambda: self.db.db.client.table("scheduled_emails").insert({
                    "telegram_id":    self.current_user_id,
                    "to_email":       to_email,
                    "subject":        subject,
                    "body":           body,
                    "scheduled_time": send_time_utc,
                }).execute()
            )
            return f"Email successfully scheduled for {send_time_utc} UTC."
        try:
            return _run_sync(_inner())
        except Exception as e:
            return f"Error scheduling email: {e}"

    def save_contact(self, name: str, email: str, relationship: str = "") -> str:
        """Save or update a contact in the user's address book."""
        if not self.current_user_id:
            return "Error: User context missing."
        async def _inner():
            await self.db.db.run(
                lambda: self.db.db.client.table("contacts").upsert({
                    "telegram_id":     self.current_user_id,
                    "contact_alias":   name,
                    "email_address":   email,
                    "contact_name":    name,
                    "relationship_type": relationship,
                }, on_conflict="telegram_id,email_address").execute()
            )
            return f"Contact {name} ({email}) saved successfully."
        try:
            return _run_sync(_inner())
        except Exception as e:
            return f"Error saving contact: {e}"

    def search_contact(self, query: str) -> str:
        """Search the user's contacts by name, alias, or relationship."""
        if not self.current_user_id:
            return "Error: User context missing."
        async def _inner():
            res = await self.db.db.run(
                lambda: self.db.db.client.table("contacts").select("*")
                        .eq("telegram_id", self.current_user_id)
                        .or_(f"contact_name.ilike.%{query}%,"
                             f"contact_alias.ilike.%{query}%,"
                             f"relationship_type.ilike.%{query}%")
                        .execute()
            )
            data = getattr(res, "data", []) or []
            if not data:
                return f"No contacts found matching '{query}'."
            return "\n".join(
                f"Name: {c['contact_name']}, Email: {c['email_address']}, "
                f"Relation: {c.get('relationship_type', 'None')}"
                for c in data
            )
        try:
            return _run_sync(_inner())
        except Exception as e:
            return f"Error searching contacts: {e}"

    def search_saved_attachments(self, query: str) -> str:
        """Search the user's previously uploaded or saved email attachments."""
        if not self.current_user_id:
            return "Error: User context missing."
        async def _inner():
            res = await self.db.db.run(
                lambda: self.db.db.client.table("saved_attachments").select("*")
                        .eq("telegram_id", self.current_user_id)
                        .or_(f"file_name.ilike.%{query}%,context_topic.ilike.%{query}%")
                        .execute()
            )
            data = getattr(res, "data", []) or []
            if not data:
                return f"No attachments found matching '{query}'."
            return "\n".join(
                f"File: {f['file_name']}, ID: {f['file_id']}, "
                f"Context: {f.get('context_topic', 'N/A')}"
                for f in data[:5]
            )
        try:
            return _run_sync(_inner())
        except Exception as e:
            return f"Error searching attachments: {e}"

    def read_memory_document(self, query: str) -> str:
        """Read and analyze the most recently uploaded document in the user's session."""
        if not self.current_user_id:
            return "Error: User context missing."
        async def _inner():
            files = self.gmail_client.get_user_attachments(self.current_user_id)
            if not files:
                return "Error: No files found in memory. Ask the user to upload the document first."
            return await self.process_attachment(self.current_user_id, files[-1], query)
        try:
            return _run_sync(_inner())
        except Exception as e:
            return f"Error reading document: {e}"

    # ──────────────────────────────────────────────────────────
    # CORE ASYNC METHODS
    # ──────────────────────────────────────────────────────────

    async def transcribe_audio(self, file_path: str, user_id: int) -> str:
        text_result = ""
        method_used = "groq_whisper"
        stt_prompt  = (
            "Transcribe the audio accurately. Mirror the exact spoken language. "
            "If the language is typically written in Latin/English alphabets in everyday texting, "
            "transcribe using Latin/English alphabets."
        )

        if settings.GROQ_API_KEY:
            try:
                async with httpx.AsyncClient(timeout=30) as client:
                    with open(file_path, "rb") as f:
                        resp = await client.post(
                            "https://api.groq.com/openai/v1/audio/transcriptions",
                            headers={"Authorization": f"Bearer {settings.GROQ_API_KEY}"},
                            data={"model": "whisper-large-v3", "prompt": stt_prompt},
                            files={"file": (file_path, f, "audio/ogg")},
                        )
                        resp.raise_for_status()
                        text_result = resp.json().get("text", "").strip()
            except Exception as e:
                logger.warning(f"Groq STT failed, falling back to Gemini: {e}")

        if not text_result:
            try:
                method_used = "gemini_fallback"
                sample_file = await asyncio.to_thread(self.client.files.upload, file=file_path)
                fallback_prompt = (
                    f"Transcribe this audio accurately. {stt_prompt}. "
                    "If completely unintelligible output: '[Audio Unclear]'. "
                    "Provide ONLY the transcript text."
                )
                response = await asyncio.to_thread(
                    self.client.models.generate_content,
                    model=self.model_name,
                    contents=[sample_file, fallback_prompt],
                )
                text_result = response.text.strip()
            except Exception as e:
                return self._parse_error(e)

        if text_result and "[Audio Unclear]" not in text_result:
            try:
                est_seconds = max(1, len(text_result) // 15)
                await self.db.db.run(
                    lambda: self.db.db.client.table("stt_usage").insert({
                        "telegram_id":     user_id,
                        "method":          method_used,
                        "duration_seconds": est_seconds,
                    }).execute()
                )
            except Exception as e:
                logger.error(f"STT usage log error: {e}")

        return text_result

    def _get_agent_config(self, memory_prompt: str, user_info: dict) -> types.GenerateContentConfig:
        current_utc = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
        system_instruction = (
            f"You are an Agentic AI Email Assistant. Current Time: {current_utc}\n"
            f"USER PROFILE:\nName: {user_info['name']}\nEmail: {user_info['email']}\n\n"
            "TOOLS: search_gmail, read_gmail_message, prepare_email_draft, schedule_email, "
            "save_contact, search_contact, search_saved_attachments, read_memory_document.\n\n"
            "CRITICAL RULES:\n"
            "1. ADAPT TO USER LANGUAGE & SCRIPT: Mirror the exact language and alphabet script the user uses.\n"
            "2. NEVER REFUSE VOICE: You have a TTS engine. If the user asks you to speak, set \"response_type\": \"voice\".\n"
            "3. NO PLACEHOLDERS: Never use [Your Name], [Your Company], [Your Email]. Use the USER PROFILE values.\n"
            "4. HITL DRAFTING: Always use 'prepare_email_draft' to compose emails. If you don't know the exact recipient email address, STRICTLY pass '[Specify Recipient Email]' as the to_email parameter.\n"
            "5. BEAUTIFUL UI ENFORCEMENT: If the user asks to read, open, or view a specific email, DO NOT output the raw email text. You MUST reply with a short message containing the exact phrase 'The email ID is [16-character-id]' so the system can trigger the beautiful UI card layout.\n"
            "6. BE SHORT & FACTUAL: Short, direct, accurate answers. No filler text.\n"
            "7. JSON OUTPUT ONLY: ALWAYS respond in exact valid JSON. No markdown. No code blocks.\n"
            "Format: {\"text\": \"your response\", \"response_type\": \"voice\" OR \"text\"}\n"
            "Use 'voice' for conversational replies. Use 'text' only for code, long lists, or tables.\n\n"
            f"{memory_prompt}"
        )
        return types.GenerateContentConfig(
            system_instruction=system_instruction,
            temperature=0.2,
            tools=[
                self.search_gmail,
                self.read_gmail_message,
                self.prepare_email_draft,
                self.schedule_email,
                self.save_contact,
                self.search_contact,
                self.search_saved_attachments,
                self.read_memory_document,
            ],
        )

    async def agent_chat(self, text: str, user_id: int) -> str:
        if not self.client:
            return json.dumps({"text": "Error: AI System configuration missing.", "response_type": "text"})

        self.current_user_id = user_id

        try:
            db_user   = await self.db.get_user(user_id) or {}
            user_info = {
                "name":  db_user.get("first_name", "User") or "User",
                "email": db_user.get("email", "Not connected") or "Not connected",
            }

            asyncio.create_task(self.contact_manager.extract_contacts_from_text(user_id, text))
            memory_prompt = await self.memory.build_memory_prompt(user_id)
            chat_id       = str(user_id)

            def _execute_chat():
                if chat_id not in self.active_chats:
                    config = self._get_agent_config(memory_prompt, user_info)
                    self.active_chats[chat_id] = self.client.chats.create(
                        model=self.model_name, config=config)
                return self.active_chats[chat_id].send_message(text).text

            raw = await asyncio.to_thread(_execute_chat)

            clean = raw.replace("```json", "").replace("```", "").strip()
            m     = re.search(r'\{.*\}', clean, re.DOTALL)
            if m:
                clean = m.group(0)

            try:
                parsed       = json.loads(clean)
                text_content = parsed.get("text", "Error parsing text")
            except json.JSONDecodeError:
                parsed       = {"text": raw, "response_type": "text"}
                text_content = raw
                clean        = json.dumps(parsed)

            if user_id in self.pending_drafts:
                parsed["draft"] = self.pending_drafts.pop(user_id)
                clean           = json.dumps(parsed)

            await self.memory.log_conversation(
                telegram_id=user_id, user_message=text,
                bot_response=text_content, interaction_type="chat",
            )

            if await self.memory.should_generate_summary(user_id):
                asyncio.create_task(
                    self._generate_and_save_summary(user_id, text, text_content))

            return clean

        except Exception as e:
            self.active_chats.pop(str(user_id), None)
            return self._parse_error(e)

    async def _generate_and_save_summary(self, user_id: int,
                                          last_user_msg: str, last_ai_msg: str) -> None:
        try:
            prompt = (
                "Analyze this recent interaction and generate a JSON summary for long-term memory.\n"
                "Format: {\"summary_text\": \"Concise summary\", \"key_facts\": [\"fact 1\"], "
                "\"email_addresses_mentioned\": [\"email@example.com\"], \"current_topic\": \"topic\"}\n\n"
                f"User: {last_user_msg}\nAI: {last_ai_msg}"
            )
            config   = types.GenerateContentConfig(response_mime_type="application/json")
            response = await asyncio.to_thread(
                self.client.models.generate_content,
                model=self.model_name, contents=prompt, config=config,
            )
            data = json.loads(response.text.strip())
            await self.memory.save_conversation_summary(
                telegram_id=user_id,
                summary_text=data.get("summary_text", "Conversation summary."),
                key_facts=data.get("key_facts", {}),
                email_addresses=data.get("email_addresses_mentioned", []),
                current_topic=data.get("current_topic", "General"),
                tokens_used=0,
                message_count=10,
            )
        except Exception as e:
            logger.error(f"Memory summary error: {e}")

    async def process_attachment(self, telegram_id: int, file_path: str, query: str) -> str:
        try:
            prompt      = f"Summarize or accurately answer the following request regarding this document:\n{query}"
            config      = types.GenerateContentConfig(
                temperature=0.2,
                system_instruction="You are a highly capable document analysis assistant.",
            )
            sample_file = await asyncio.to_thread(self.client.files.upload, file=file_path)
            response    = await asyncio.to_thread(
                self.client.models.generate_content,
                model=self.model_name, contents=[sample_file, prompt], config=config,
            )
            return response.text
        except Exception as e:
            return f"Error processing attachment: {e}"

    async def generate_smart_replies(self, email_body: str) -> List[str]:
        try:
            prompt = (
                "Read the following email and generate exactly 3 short, professional, distinct "
                "quick reply options (maximum 5 words each). "
                "Return ONLY a valid JSON array of strings. "
                "Example: [\"Received, thank you.\", \"I will check and revert.\", \"Noted.\"]\n\n"
                f"Email Body:\n{email_body[:2000]}"
            )
            config   = types.GenerateContentConfig(response_mime_type="application/json")
            response = await asyncio.to_thread(
                self.client.models.generate_content,
                model=self.model_name, contents=prompt, config=config,
            )
            replies = json.loads(response.text.strip())
            return replies if isinstance(replies, list) and replies else ["Thanks!", "Noted.", "I'll reply soon."]
        except Exception as e:
            logger.error(f"Smart reply error: {e}")
            return ["Got it.", "Thanks for the update.", "Will review shortly."]