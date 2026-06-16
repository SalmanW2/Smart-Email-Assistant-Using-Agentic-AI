"""
Agentic AI Engine — Smart Email Assistant
=========================================
Core reasoning and decision-making module powered by Google Gemini 2.5 Flash.

Features:
1. Thread-safe isolated background execution loops for concurrent multi-user handling.
2. Dynamic Server-Side Chat Session Mappings via active multi-turn message trackers.
3. Token Exhaustion Management via strict chronological context history pruning.
4. Human-In-The-Loop (HITL) guardrails injected into Drafting and Scheduling logic.
5. Integrated fallback logic for Speech-to-Text (STT) conversions using Groq and Gemini.
6. Identity Locked: Enforces "Smart Email Assistant" persona, blocking generic LLM preambles.
7. Multi-Lingual & Voice Aware: Understands and generates regional languages (Punjabi, Urdu) for TTS.
"""

import asyncio
import json
import logging
import httpx
import re
import os
import tempfile
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, Optional, List
import threading

from google import genai
from google.genai import types

from config import settings
from db.memory import memory_manager
from bot.contact_manager import contact_manager
from bot.gmail_client import GmailClient
from db.models import db_manager

logger = logging.getLogger(__name__)

# ==========================================
# THREAD-SAFE CONCURRENT EXECUTION MANAGER
# ==========================================
_tool_loop: asyncio.AbstractEventLoop | None = None
_tool_loop_lock = threading.Lock()

def _get_tool_loop() -> asyncio.AbstractEventLoop:
    """
    Retrieves or initializes a thread-safe, dedicated background event loop.
    Prevents the blocking of the main thread pool during concurrent user sessions.
    """
    global _tool_loop
    with _tool_loop_lock:
        if _tool_loop is None or _tool_loop.is_closed():
            _tool_loop = asyncio.new_event_loop()
            t = threading.Thread(target=_tool_loop.run_forever, daemon=True)
            t.start()
        return _tool_loop

def _run_sync(coro) -> Any:
    """
    Safely executes an asynchronous coroutine inside Gemini's synchronous tool execution loops.
    """
    loop = _get_tool_loop()
    future = asyncio.run_coroutine_threadsafe(coro, loop)
    return future.result()

# ==========================================
# AI ENGINE CLASS
# ==========================================
class AIEngine:
    def __init__(self) -> None:
        """
        Initializes the Google Gemini client, sets the reasoning model,
        and provisions the Gmail API backend client wrapper.
        """
        self.client = genai.Client(api_key=settings.GEMINI_API_KEY)
        self.model_name = "gemini-2.5-flash"
        self.gmail_client = GmailClient()
        
        # Temporary runtime memory cache for mapping and staging drafted parameters
        self.pending_drafts: Dict[int, Dict[str, Any]] = {}

        # Multi-user conversation history cache for persistent stateful chat sessions
        self.active_chats: Dict[int, List[types.Content]] = {}

    # ==========================================
    # GEMINI TOOL DEFINITIONS (FUNCTION CALLING)
    # ==========================================

    def search_gmail_tool(self, query: str, user_id: int) -> str:
        """
        Tool: Searches the user's Gmail inbox for specific threads or messages.
        """
        logger.info(f"[Tool Execution] Searching Gmail for user {user_id} with query: {query}")
        results = _run_sync(self.gmail_client.search_emails(user_id, query, max_results=5))
        if not results:
            return "No emails found matching the search query parameters."
        return json.dumps(results)

    def prepare_email_draft_tool(self, to_email: str, subject: str, body: str, user_id: int) -> str:
        """
        Tool: Prepares and stages an immediate email draft.
        HITL Guardrail: If the explicit target email is unknown, the AI MUST output '[Specify Recipient Email]'.
        """
        logger.info(f"[Tool Execution] Preparing Draft | To: {to_email} for User: {user_id}")
        
        # Perform dynamic validation for missing address constraints
        to_clean = to_email.strip() if to_email else ""
        if not to_clean or "@" not in to_clean or "[Specify" in to_clean:
            to_clean = "[Specify Recipient Email]"

        draft = {
            "action": "prepare_draft",
            "to": to_clean,
            "subject": subject or "No Subject",
            "body": body or ""
        }
        
        # Cache draft within the instance memory for Telegram Handler retrieval
        self.pending_drafts[user_id] = draft
        return json.dumps({"status": "success", "draft": draft})

    def schedule_email_tool(self, to_email: str, subject: str, body: str, scheduled_time: str, user_id: int) -> str:
        """
        Tool: Schedules an email for future automated dispatch.
        HITL Guardrail: If the target email is unknown, the AI MUST output '[Specify Recipient Email]'.
        """
        logger.info(f"[Tool Execution] Scheduling Email | To: {to_email} | Time: {scheduled_time} for User: {user_id}")
        
        to_clean = to_email.strip() if to_email else ""
        if not to_clean or "@" not in to_clean or "[Specify" in to_clean:
            to_clean = "[Specify Recipient Email]"

        schedule_details = {
            "to_email": to_clean,
            "subject": subject or "No Subject",
            "body": body or "",
            "scheduled_time": scheduled_time,
            "status": "pending"
        }

        # Persist immediately to the scheduled_emails schema using Supabase DB Manager
        try:
            _run_sync(db_manager.db.run(lambda: db_manager.db.client.table("scheduled_emails").insert({
                "telegram_id": user_id,
                "to_email": to_clean,
                "subject": subject or "No Subject",
                "body": body or "",
                "scheduled_time": scheduled_time,
                "status": "pending"
            }).execute()))
            logger.info("Successfully registered scheduled email in database")
        except Exception as db_err:
            logger.error(f"Database error writing scheduled task: {db_err}")
            return json.dumps({"status": "error", "message": f"Database failure: {str(db_err)}"})

        return json.dumps({
            "action": "schedule_email",
            "schedule_details": schedule_details
        })

    def save_contact_tool(self, name: str, email: str, user_id: int) -> str:
        """
        Tool: Saves or updates an address book contact in the user's Supabase contacts table.
        Robust parsing implemented to prevent database composite key collision errors.
        """
        logger.info(f"[Tool Execution] Saving Contact | Name: {name} | Email: {email} for User: {user_id}")
        
        # Structural limits and constraints validation for DB injection
        clean_email = str(email).strip().lower()
        clean_name = str(name).strip()[:200]
        safe_uid = int(user_id)
        
        if not clean_email or "@" not in clean_email:
            return "Error: Invalid email format provided. Contact not saved."

        try:
            _run_sync(db_manager.db.run(lambda: db_manager.db.client.table("contacts").upsert({
                "telegram_id": safe_uid,
                "contact_alias": clean_name,
                "email_address": clean_email,
                "contact_name": clean_name
            }, on_conflict="telegram_id,email_address").execute()))
            return f"Contact '{clean_name}' with email '{clean_email}' saved successfully."
        except Exception as e:
            logger.error(f"Failed to upsert contact via Tool call: {e}")
            return f"Error: Contact could not be saved to DB due to a technical constraint: {str(e)}"

    # ==========================================
    # CORE AGENT REASONING ENGINE
    # ==========================================

    async def agent_chat(self, message: str, telegram_id: int) -> str:
        """
        Primary entry point for processing conversational user prompts.
        Applies strict Token Truncation, Contacts Context injection, and resolves
        dynamic tool calling models natively under Gemini 2.5 Flash constraints.
        """
        try:
            # 1. Fetch saved contacts to inject as contextual mapping
            contacts_list = await contact_manager.get_contacts(telegram_id)
            contacts_context = "\n".join([
                f"- {c.get('contact_alias')} ({c.get('contact_name')}): {c.get('email_address')}" 
                for c in contacts_list
            ])

            # 2. Token Exhaustion Management: Truncate chronological context records
            raw_summaries = await memory_manager.get_recent_summaries(telegram_id, limit=settings.MAX_CONTEXT_MESSAGES)
            recent_summaries = raw_summaries[:settings.MAX_CONTEXT_MESSAGES] if raw_summaries else []
            history_context = "\n".join([
                f"Topic: {s.get('current_topic')} | Summary: {s.get('summary_text')}" 
                for s in recent_summaries
            ])

            # 3. Dynamic current datetime matrix
            utc_now = datetime.utcnow().replace(tzinfo=timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")

            # 4. Standardized prompt system instruction with absolute identity & language locks
            system_instructions = (
                "IDENTITY LOCK: You are the 'Smart Email Assistant', an elite agentic system running inside Telegram.\n"
                "NEVER break character. NEVER use generic AI disclaimers like 'As a large language model' or 'As an AI'.\n"
                "Assume full identity and ownership of your email management capabilities.\n\n"
                "LANGUAGE & VOICE CAPABILITIES: You are multi-lingual. You must understand and generate text in the user's "
                "preferred language (e.g., English, Punjabi, Urdu, Roman Urdu). If the user asks for a voice message, "
                "audio summary, or spoken response, ALWAYS generate the response normally in the requested language text. "
                "The background Text-to-Speech (TTS) engine will read your text aloud. Do NOT apologize or claim you cannot send voice.\n\n"
                "Your goal is to assist the user in reading, searching, summarizing, drafting, and scheduling emails.\n"
                f"Current Date and Time: {utc_now}\n\n"
                f"User's Address Book (Always search here first when names are mentioned):\n"
                f"{contacts_context or 'No saved contacts in database yet.'}\n\n"
                f"Recent Conversation Memory Context (Use this to follow reference pronouns):\n"
                f"{history_context or 'No prior conversation history recorded.'}\n\n"
                "CRITICAL SYSTEM DIRECTIVES:\n"
                "1. If the user wants to fetch, read, list, search, or check emails, prioritize using the 'search_gmail_tool'.\n"
                "2. If the user wants to reply or draft, map context to the 'prepare_email_draft_tool'.\n"
                "3. If the user wants to schedule an email for a future date/time, use the 'schedule_email_tool'.\n"
                "4. HITL Guardrail: If preparing or scheduling a draft and you do not know the exact recipient email address "
                "from either the conversation history or the Address Book, you MUST strictly use the exact string "
                "'[Specify Recipient Email]' as the to_email parameter. NEVER make up or guess email addresses.\n"
                "5. Return a helpful, clean, professional plain-text response when no tool executions are needed."
            )

            # Register tools
            tools_map = {
                "search_gmail_tool": self.search_gmail_tool,
                "prepare_email_draft_tool": self.prepare_email_draft_tool,
                "schedule_email_tool": self.schedule_email_tool,
                "save_contact_tool": self.save_contact_tool
            }

            config = types.GenerateContentConfig(
                system_instruction=system_instructions,
                tools=list(tools_map.values()),
                temperature=0.2, # Low temperature for strict routing and tool call logic
            )

            # 5. Native Chat Session Management setup
            if telegram_id not in self.active_chats:
                self.active_chats[telegram_id] = []

            # Truncate active chat turn list to protect token limitations
            max_turns = settings.MAX_CONTEXT_MESSAGES * 2
            if len(self.active_chats[telegram_id]) > max_turns:
                self.active_chats[telegram_id] = self.active_chats[telegram_id][-max_turns:]

            # Construct message turns structure with current state
            user_part = types.Part.from_text(text=message)
            user_content = types.Content(role="user", parts=[user_part])
            contents = self.active_chats[telegram_id] + [user_content]

            logger.info(f"Triggering Gemini 2.5 Flash for user: {telegram_id} using stateful conversation tracking")
            response = await asyncio.to_thread(
                self.client.models.generate_content,
                model=self.model_name,
                contents=contents,
                config=config,
            )

            # Handle and process active Function / Tool Calls
            if response.function_calls:
                results_parts = []
                for fc in response.function_calls:
                    fn_name = fc.name
                    args = dict(fc.args)

                    # Inject contextual parameters
                    if fn_name in ["search_gmail_tool", "prepare_email_draft_tool", "schedule_email_tool", "save_contact_tool"]:
                        args["user_id"] = telegram_id

                    try:
                        func = tools_map[fn_name]
                        # Execute synchronous wrapper dynamically
                        result_str = func(**args)
                        
                        # HARD INTERCEPTOR: Stop AI Hallucinations if Token is Expired!
                        if "TOKEN_EXPIRED_REAUTH_REQUIRED" in result_str:
                            return "TOKEN_EXPIRED_REAUTH_REQUIRED"

                        # Intercept structural layout payloads for Drafting/Scheduling
                        if "prepare_draft" in result_str or "schedule_email" in result_str:
                            # Append turns to history before intercepting, keeping model context perfectly aligned
                            self.active_chats[telegram_id].append(user_content)
                            self.active_chats[telegram_id].append(response.candidates[0].content)
                            return result_str
                            
                        results_parts.append(
                            types.Part.from_function_response(name=fn_name, response={"result": result_str})
                        )
                    except Exception as tool_err:
                        logger.error(f"Error executing tool {fn_name}: {tool_err}")
                        results_parts.append(
                            types.Part.from_function_response(name=fn_name, response={"error": str(tool_err)})
                        )

                # Return the result back to Gemini to formulate the final conversational response
                final_response = await asyncio.to_thread(
                    self.client.models.generate_content,
                    model=self.model_name,
                    contents=contents + [response.candidates[0].content] + results_parts,
                    config=config,
                )
                
                # Append final message turns to history
                self.active_chats[telegram_id].append(user_content)
                self.active_chats[telegram_id].append(final_response.candidates[0].content)
                return final_response.text

            # Append plain chat responses to history
            self.active_chats[telegram_id].append(user_content)
            self.active_chats[telegram_id].append(response.candidates[0].content)
            return response.text

        except Exception as e:
            logger.error(f"AIEngine.agent_chat error: {e}")
            return "I encountered an internal tracking error while processing your request. Please try again shortly."

    def clear_chat_session(self, telegram_id: int) -> None:
        """Clears the dynamic chat session history for a specific user."""
        if telegram_id in self.active_chats:
            self.active_chats[telegram_id] = []
            logger.info(f"Cleared stateful chat session history for user {telegram_id}")

    # ==========================================
    # SPEECH-TO-TEXT (STT) ENGINE & FALLBACK
    # ==========================================

    async def transcribe_audio(self, file_path: str, telegram_id: int) -> str:
        """
        Transcribes voice messages. First attempts processing via Groq Whisper Large V3 API.
        If Groq is unconfigured or fails, falls back safely to Gemini's native file uploading transcription.
        Logs telemetry metrics to stt_usage upon completion.
        """
        start_time = datetime.now()
        method_used = "groq_whisper"
        transcription_text = ""

        # Attempt Groq Whisper Large V3 transcription
        if settings.GROQ_API_KEY:
            try:
                logger.info(f"Attempting STT transcription via Groq Whisper for user: {telegram_id}")
                url = "https://api.groq.com/openai/v1/audio/transcriptions"
                headers = {"Authorization": f"Bearer {settings.GROQ_API_KEY}"}
                
                with open(file_path, "rb") as f:
                    files = {"file": (os.path.basename(file_path), f, "audio/ogg")}
                    data = {"model": "whisper-large-v3", "response_format": "json"}
                    
                    async with httpx.AsyncClient(timeout=30.0) as client:
                        response = await client.post(url, headers=headers, files=files, data=data)
                        response.raise_for_status()
                        result = response.json()
                        transcription_text = result.get("text", "").strip()
                        
                logger.info("Successfully transcribed voice note via Groq Whisper Large V3.")
            except Exception as whisper_err:
                logger.warning(f"Groq Whisper transcription failed, starting fallback: {whisper_err}")

        # Fallback to Gemini's native file model uploader if Whisper was bypassed or failed
        if not transcription_text:
            try:
                logger.info("Triggering Gemini file upload STT fallback pipeline")
                method_used = "gemini_native"
                
                config = types.GenerateContentConfig(temperature=0.1)
                uploaded_file = await asyncio.to_thread(
                    self.client.files.upload,
                    file=file_path
                )
                
                response = await asyncio.to_thread(
                    self.client.models.generate_content,
                    model=self.model_name,
                    contents=[uploaded_file, "Accurately transcribe this audio. Return ONLY the transcription with no preambles."],
                    config=config
                )
                transcription_text = response.text.strip() if response.text else ""
            except Exception as gemini_err:
                logger.error(f"Fallback Gemini STT also failed: {gemini_err}")
                return "System Error: Speech-to-Text translation engine failed. Please type your message."

        # Compute voice note duration and persist telemetry metrics to Supabase
        if transcription_text:
            duration = int((datetime.now() - start_time).total_seconds())
            try:
                await db_manager.db.run(lambda: db_manager.db.client.table("stt_usage").insert({
                    "telegram_id": telegram_id,
                    "method": method_used,
                    "duration_seconds": max(duration, 1)
                }).execute())
                logger.info(f"Successfully logged STT metrics for user {telegram_id}")
            except Exception as db_err:
                logger.error(f"Failed logging STT usage parameters to DB: {db_err}")

            return transcription_text

        return "[Audio Unclear: Failed to extract written text context]"

    # ==========================================
    # UTILITY CORES
    # ==========================================

    async def summarize_email(self, email_body: str) -> str:
        """
        Generates a concise, actionable 3-bullet point email summary.
        """
        try:
            prompt = (
                "You are an executive email processing assistant. "
                "Analyze the email content below and extract exactly 3 short, actionable bullet points.\n"
                "Focus strictly on core dates, metrics, and actionable deliverables. Be extremely brief.\n\n"
                f"Email Body Content:\n{email_body[:5000]}"
            )
            response = await asyncio.to_thread(
                self.client.models.generate_content,
                model=self.model_name,
                contents=prompt
            )
            return response.text.strip() if response.text else "Summary unavailable."
        except Exception as e:
            logger.error(f"Summarize email error: {e}")
            return "Email abstractive summary failed due to internal analytical errors."

    async def analyze_attachment(self, file_path: str, prompt: str) -> str:
        """
        Analyzes locally downloaded document or image attachments using Gemini file uploader.
        """
        try:
            config = types.GenerateContentConfig(temperature=0.2)
            sample_file = await asyncio.to_thread(self.client.files.upload, file=file_path)
            response = await asyncio.to_thread(
                self.client.models.generate_content,
                model=self.model_name,
                contents=[sample_file, prompt],
                config=config,
            )
            return response.text
        except Exception as e:
            return f"Error processing attachment: {e}"

    async def generate_smart_replies(self, email_body: str) -> List[str]:
        """
        Generates exactly 3 professional, short quick reply options.
        """
        try:
            prompt = (
                "Read the following email and generate exactly 3 short, professional, distinct "
                "quick reply options (maximum 5 words each). "
                "Return ONLY a valid JSON array of strings. "
                "Example: [\"Received, thank you.\", \"I will check and revert.\", \"Noted.\"]\n\n"
                f"Email Body:\n{email_body[:2000]}"
            )
            config = types.GenerateContentConfig(response_mime_type="application/json")
            response = await asyncio.to_thread(
                self.client.models.generate_content,
                model=self.model_name,
                contents=prompt,
                config=config,
            )
            replies = json.loads(response.text.strip())
            return replies if isinstance(replies, list) and replies else ["Thanks!", "Noted.", "I'll reply soon."]
        except Exception as e:
            logger.error(f"Smart reply error: {e}")
            return ["Acknowledge.", "Will review.", "Thanks."]

# Singleton instance initialization
ai_engine = AIEngine()