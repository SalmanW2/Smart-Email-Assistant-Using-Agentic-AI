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
        self.current_user_id = None # Context for tools

    def _parse_error(self, e: Exception) -> str:
        err_msg = str(e)
        logger.error(f"AI Engine Runtime Error: {err_msg}")
        
        # Smart Error Handling for Better UX
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
        if not self.current_user_id: return "Error: User context missing."
        
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
            
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        return loop.run_until_complete(_search())

    def read_gmail_message(self, message_id: str) -> str:
        """Reads the full body content of a specific email using its ID."""
        if not self.current_user_id: return "Error: User context missing."
        
        import asyncio
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        return loop.run_until_complete(self.gmail_client.read_full_email(self.current_user_id, message_id))

    def draft_and_send_email(self, to_email: str, subject: str, body: str) -> str:
        """Sends an email. Call this when the user asks to send or reply to an email."""
        if not self.current_user_id: return "Error: User context missing."
        
        import asyncio
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        res = loop.run_until_complete(self.gmail_client.send_email(self.current_user_id, to_email, subject, body, []))
        return f"Email sent successfully: {res}"

    # ==========================================
    # CORE AI LOGIC
    # ==========================================

    async def transcribe_audio(self, file_path: str) -> str:
        """Transcribes voice notes using Groq Whisper (Primary) or Gemini (Fallback)."""
        # --- Primary: Groq Whisper API (Fast & 0 Gemini Quota) ---
        if settings.GROQ_API_KEY:
            try:
                import httpx
                async with httpx.AsyncClient(timeout=30) as client:
                    with open(file_path, "rb") as f:
                        files = {"file": (file_path, f, "audio/ogg")}
                        data = {"model": "whisper-large-v3"}
                        headers = {"Authorization": f"Bearer {settings.GROQ_API_KEY}"}
                        response = await client.post(
                            "https://api.groq.com/openai/v1/audio/transcriptions",
                            headers=headers,
                            data=data,
                            files=files
                        )
                        response.raise_for_status()
                        result = response.json()
                        text = result.get("text", "").strip()
                        if text:
                            return text
            except Exception as e:
                logger.warning(f"Groq STT failed, falling back to Gemini: {e}")

        # --- Fallback: Gemini Multi-modal ---
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

    def _get_agent_config(self, memory_prompt: str) -> types.GenerateContentConfig:
        """Constructs the strict behavior guidelines and equips the Agent with Tools."""
        system_instruction = (
            "You are an Agentic AI Email Assistant. YOU HAVE TOOLS TO INTERACT WITH GMAIL.\n"
            "CRITICAL RULES:\n"
            "1. INBOX ACCESS: You CAN search and read emails. If the user asks to check, list, read, or search emails, YOU MUST call the `search_gmail` tool first, then optionally `read_gmail_message`.\n"
            "2. SENDING: To send or reply to an email, YOU MUST call the `draft_and_send_email` tool.\n"
            "3. NEVER SAY 'I cannot access your inbox'. You are a fully integrated Agent. Use your tools!\n"
            "4. CONCISENESS: Keep conversational responses extremely brief and use Markdown.\n"
            "5. CONTACTS: Rely on the provided user memory to resolve names to email addresses.\n\n"
            f"{memory_prompt}"
        )

        return types.GenerateContentConfig(
            system_instruction=system_instruction,
            temperature=0.2,
            tools=[self.search_gmail, self.read_gmail_message, self.draft_and_send_email]
        )

    async def agent_chat(self, text: str, user_id: int) -> str:
        """Main interaction pipeline. Handles memory context, chat execution, and logging."""
        if not self.client: return "Error: AI System configuration missing."
        
        self.current_user_id = user_id # Set context for tools
        
        try:
            # 1. Proactively scan for and save new contacts
            asyncio.create_task(self.contact_manager.extract_contacts_from_text(user_id, text))

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

            # 4. Generate the response (Gemini will automatically call tools if needed!)
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
                asyncio.create_task(self._generate_and_save_summary(user_id, text, bot_response))

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
                "{\n  \"summary_text\": \"Concise summary of what occurred\",\n  \"key_facts\": [\"extracted fact 1\"],\n  \"email_addresses_mentioned\": [\"email@example.com\"],\n  \"current_topic\": \"Main topic\"\n}\n\n"
                f"User: {last_user_msg}\nAI: {last_ai_msg}"
            )
            response = await asyncio.to_thread(
                self.client.models.generate_content, model="gemini-2.5-flash-lite", contents=prompt
            )
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
        """Analyzes uploaded documents using Vision/Multi-modal capabilities."""
        try:
            prompt = f"Summarize or accurately answer the following request regarding this document:\n{query}"
            config = types.GenerateContentConfig(temperature=0.2, system_instruction="You are a highly capable document analysis assistant.")
            sample_file = await asyncio.to_thread(self.client.files.upload, file=file_path)
            response = await asyncio.to_thread(self.client.models.generate_content, model=self.model_name, contents=[sample_file, prompt], config=config)
            return response.text
        except Exception as e:
            return self._parse_error(e)