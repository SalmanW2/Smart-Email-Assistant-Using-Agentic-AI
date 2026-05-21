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

class AIEngine:
    def __init__(self) -> None:
        self.memory = memory_manager
        self.contact_manager = contact_manager
        self.gmail_client = GmailClient()
        self.db = db_manager
        self.client = genai.Client(api_key=settings.GEMINI_API_KEY)
        self.model_name = "gemini-2.5-flash" 
        self.active_chats = {}
        self.current_user_id = None
        self.pending_drafts = {}

    def _parse_error(self, e: Exception) -> str:
        err_msg = str(e)
        logger.error(f"AI Engine Runtime Error: {err_msg}")
        
        if "429" in err_msg or "RESOURCE_EXHAUSTED" in err_msg:
            return json.dumps({"text": "⏳ *System Limit Reached:* AI processing quota is temporarily exhausted. Please try again later.", "response_type": "text"})
        elif "503" in err_msg or "UNAVAILABLE" in err_msg:
            return json.dumps({"text": "🔌 *Server Overload:* AI servers are currently experiencing high traffic. Please retry in 10-20 seconds.", "response_type": "text"})
        else:
            return json.dumps({"text": "❌ *System Error:* Unable to process the request at this moment. Please try again later.", "response_type": "text"})

    # ==========================================
    # 🛠️ AGENTIC TOOLS (Functions Gemini Can Call)
    # ==========================================
    
    def search_gmail(self, query: str, max_results: int = 5) -> str:
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
        if not self.current_user_id: 
            return "Error: User context missing."
        import asyncio
        try:
            return asyncio.run(self.gmail_client.read_full_email(self.current_user_id, message_id))
        except Exception as e:
            return f"Error reading email: {e}"

    def prepare_email_draft(self, to_email: str, subject: str, body: str) -> str:
        """Prepares an email draft for the user to review. MUST be called when the user asks to send or reply to an email."""
        if not self.current_user_id: 
            return "Error: User context missing."
        
        # If AI doesn't know the recipient, mark it dynamically
        if not to_email or to_email.strip() == "":
            to_email = "[Specify Recipient]"
            
        self.pending_drafts[self.current_user_id] = {
            "to": to_email,
            "subject": subject,
            "body": body
        }
        return "Draft prepared successfully. Inform the user that the draft is ready for their review."

    def schedule_email(self, to_email: str, subject: str, body: str, send_time_utc: str) -> str:
        """Schedules an email to be sent later in UTC 'YYYY-MM-DD HH:MM:SS' format."""
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

    def save_contact(self, name: str, email: str, relationship: str = "") -> str:
        if not self.current_user_id: 
            return "Error: User context missing."
        import asyncio
        async def _save():
            await self.db.db.run(lambda: self.db.db.client.table("contacts").upsert({
                "telegram_id": self.current_user_id,
                "contact_alias": name,
                "email_address": email,
                "contact_name": name,
                "relationship_type": relationship
            }, on_conflict="telegram_id,email_address").execute())
            return f"Contact {name} ({email}) saved successfully."
        try:
            return asyncio.run(_save())
        except Exception as e:
            return f"Error saving contact: {e}"

    def search_contact(self, query: str) -> str:
        if not self.current_user_id: return "Error: User context missing."
        import asyncio
        async def _search():
            res = await self.db.db.run(lambda: self.db.db.client.table("contacts").select("*").eq("telegram_id", self.current_user_id).or_(f"contact_name.ilike.%{query}%,contact_alias.ilike.%{query}%,relationship_type.ilike.%{query}%").execute())
            data = getattr(res, 'data', [])
            if not data: return f"No contacts found matching '{query}'."
            return "\n".join([f"Name: {c['contact_name']}, Email: {c['email_address']}, Relation: {c.get('relationship_type', 'None')}" for c in data])
        try:
            return asyncio.run(_search())
        except Exception as e:
            return f"Error searching contacts: {e}"

    def search_saved_attachments(self, query: str) -> str:
        if not self.current_user_id: return "Error: User context missing."
        import asyncio
        async def _search():
            res = await self.db.db.run(lambda: self.db.db.client.table("saved_attachments").select("*").eq("telegram_id", self.current_user_id).or_(f"file_name.ilike.%{query}%,context_topic.ilike.%{query}%").execute())
            data = getattr(res, 'data', [])
            if not data: return f"No attachments found matching '{query}'."
            return "\n".join([f"File: {f['file_name']}, ID: {f['file_id']}, Context: {f.get('context_topic', 'N/A')}" for f in data[:5]])
        try:
            return asyncio.run(_search())
        except Exception as e:
            return f"Error searching attachments: {e}"

    def read_memory_document(self, query: str) -> str:
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
        text_result = ""
        method_used = "groq_whisper"
        
        stt_prompt = "Transcribe the audio accurately. Mirror the exact spoken language. If the language is typically written in Latin/English alphabets in everyday texting, transcribe using Latin/English alphabets."

        if settings.GROQ_API_KEY:
            try:
                async with httpx.AsyncClient(timeout=30) as client:
                    with open(file_path, "rb") as f:
                        files = {"file": (file_path, f, "audio/ogg")}
                        data = {
                            "model": "whisper-large-v3", 
                            "prompt": stt_prompt
                        }
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
                fallback_prompt = f"Transcribe this audio accurately. {stt_prompt}. If completely unintelligible, output: '[Audio Unclear]'. Provide ONLY the transcript text."
                response = await asyncio.to_thread(self.client.models.generate_content, model=self.model_name, contents=[sample_file, fallback_prompt])
                text_result = response.text.strip()
            except Exception as e:
                return self._parse_error(e)

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

    def _get_agent_config(self, memory_prompt: str, user_info: dict) -> types.GenerateContentConfig:
        current_utc = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
        system_instruction = (
            f"You are an Agentic AI Email Assistant. Current Time: {current_utc}\n"
            f"USER PROFILE:\nName: {user_info['name']}\nEmail: {user_info['email']}\n\n"
            "TOOLS AVAILABLE: search_gmail, read_gmail_message, prepare_email_draft, schedule_email, save_contact, search_contact, search_saved_attachments, read_memory_document.\n\n"
            "CRITICAL RULES:\n"
            "1. ADAPT TO USER LANGUAGE & SCRIPT: You must perfectly mirror the exact language and the exact alphabet script the user uses. Do not force standard English or native scripts if the user is using a dialect or transliteration.\n"
            "2. NEVER REFUSE VOICE: You are equipped with a Text-to-Speech (TTS) engine. If the user asks you to speak, send a voice note, or talk, NEVER say you cannot. Simply set \"response_type\": \"voice\" in your JSON.\n"
            "3. NO PLACEHOLDERS: NEVER use placeholders like [Your Name], [Your Company], or [Your Email]. Always use the exact Name and Email provided in the USER PROFILE above.\n"
            "4. NO BLIND SENDING: Do not send emails directly. Always use the 'prepare_email_draft' tool. Once the tool returns success, tell the user the draft is ready. If the recipient is missing, set to_email to '[Specify Recipient]'.\n"
            "5. BE SHORT & FACTUAL: Provide short, direct, accurate, 100% correct, and factual answers without unnecessary pleasantries or filler text.\n"
            "6. JSON OUTPUT ONLY: YOU MUST ALWAYS RESPOND IN EXACT, VALID JSON FORMAT. Escape internal quotes properly using \\\". Do not wrap it in markdown code blocks. Format:\n"
            "{\"text\": \"Your actual response message here\", \"response_type\": \"voice\" OR \"text\"}\n"
            "Use 'voice' for standard conversational replies. Use 'text' ONLY if the response contains code, long lists, or data that must be read on screen.\n\n"
            f"{memory_prompt}"
        )
        return types.GenerateContentConfig(
            system_instruction=system_instruction,
            temperature=0.2,
            tools=[self.search_gmail, self.read_gmail_message, self.prepare_email_draft, self.schedule_email, 
                   self.save_contact, self.search_contact, self.search_saved_attachments, self.read_memory_document]
        )

    async def agent_chat(self, text: str, user_id: int) -> str:
        if not self.client: return json.dumps({"text": "Error: AI System configuration missing.", "response_type": "text"})
        self.current_user_id = user_id 
        
        try:
            db_user = await self.db.get_user(user_id) or {}
            user_info = {
                "name": db_user.get("first_name", "User") or "User",
                "email": db_user.get("email", "Not connected") or "Not connected"
            }

            asyncio.create_task(self.contact_manager.extract_contacts_from_text(user_id, text))
            memory_prompt = await self.memory.build_memory_prompt(user_id)
            chat_id = str(user_id)

            def _execute_chat():
                if chat_id not in self.active_chats:
                    config = self._get_agent_config(memory_prompt, user_info)
                    self.active_chats[chat_id] = self.client.chats.create(model=self.model_name, config=config)
                return self.active_chats[chat_id].send_message(text).text

            raw_bot_response = await asyncio.to_thread(_execute_chat)
            
            clean_json = raw_bot_response.replace('```json', '').replace('```', '').strip()
            json_match = re.search(r'\{.*\}', clean_json, re.DOTALL)
            if json_match:
                clean_json = json_match.group(0)
            
            try:
                parsed_response = json.loads(clean_json)
                text_content = parsed_response.get("text", "Error parsing text")
            except json.JSONDecodeError:
                parsed_response = {"text": raw_bot_response, "response_type": "text"}
                text_content = raw_bot_response
                clean_json = json.dumps(parsed_response)

            # Inject the drafted email into the JSON so TelegramHandler can trigger the UI
            if user_id in self.pending_drafts:
                parsed_response["draft"] = self.pending_drafts.pop(user_id)
                clean_json = json.dumps(parsed_response)

            await self.memory.log_conversation(telegram_id=user_id, user_message=text, bot_response=text_content, interaction_type="chat")

            if await self.memory.should_generate_summary(user_id):
                asyncio.create_task(self._generate_and_save_summary(user_id, text, text_content))

            return clean_json
            
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
            config = types.GenerateContentConfig(response_mime_type="application/json")
            response = await asyncio.to_thread(self.client.models.generate_content, model=self.model_name, contents=prompt, config=config)
            
            json_str = response.text.strip()
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
            return f"Error processing attachment: {e}"

    async def generate_smart_replies(self, email_body: str) -> List[str]:
        try:
            prompt = (
                "You are an AI Email Assistant. Read the following email and generate exactly 3 short, "
                "professional, and distinct quick reply options (maximum 4-5 words each). "
                "Return ONLY a valid JSON array of strings. Example: [\"Received, thank you.\", \"I will check and revert.\", \"Noted.\"]\n\n"
                f"Email Body:\n{email_body[:2000]}"
            )
            config = types.GenerateContentConfig(response_mime_type="application/json")
            response = await asyncio.to_thread(self.client.models.generate_content, model=self.model_name, contents=prompt, config=config)
            
            json_str = response.text.strip()
            replies = json.loads(json_str)
            return replies if isinstance(replies, list) and len(replies) > 0 else ["Thanks!", "Noted.", "I'll reply soon."]
        except Exception as e:
            logger.error(f"Smart Reply Generation Error: {e}")
            return ["Got it.", "Thanks for the update.", "Will review shortly."]