"""
Agentic AI Engine — Smart Email Assistant
=========================================
Core reasoning and decision-making module powered by Google Gemini 2.5 Flash.

Features:
1. Standalone Tool Functions: Avoids deep-copy pickling errors from bound methods in SDK config.
2. Dynamic Server-Side Chat Session Mappings via active multi-turn message trackers.
3. Token Exhaustion Management via strict chronological context history pruning.
4. Human-In-The-Loop (HITL) guardrails injected into Drafting and Scheduling logic.
5. Token-Efficient Utility Calls: summarize_email / generate_tts_summary are single-turn
   direct LLM calls that do NOT pollute the multi-turn chat history or cost tool-setup tokens.
6. Integrated fallback logic for Speech-to-Text (STT) conversions using Groq and Gemini.
7. Identity Locked: Enforces "Smart Email Assistant" persona, blocking generic LLM preambles.
8. Multi-Lingual & Voice Aware: Understands and generates regional languages (Punjabi, Urdu) for TTS.
9. Groq Failover Pipeline: Instantly falls back to Llama-3-70b if Gemini hits a rate limit!
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
# MODULE-LEVEL SHARED STATE
# ==========================================
# These are module-level dicts so that standalone tool functions can access
# per-user state without being bound to the AIEngine class instance.
# This is the KEY fix that eliminates the `cannot pickle '_thread.lock'` error:
# Gemini's SDK deep-copies the tools config, so tool callables must NOT be bound
# methods (which drag in the entire instance including unpicklable Gemini client).
#
# The GmailClient and pending_drafts are lazily initialized here.
_module_gmail_client = None
_module_pending_drafts: Dict[int, Dict[str, Any]] = {}


def _get_gmail_client():
    """Lazily initializes a module-level GmailClient singleton."""
    global _module_gmail_client
    if _module_gmail_client is None:
        from bot.gmail_client import GmailClient
        _module_gmail_client = GmailClient()
    return _module_gmail_client


# ==========================================
# STANDALONE TOOL FUNCTIONS (NOT BOUND METHODS)
# ==========================================
# These functions are module-level to prevent deep-copy pickling errors
# when passed to types.GenerateContentConfig(tools=[...]).

def search_gmail_tool(query: str, user_id: int) -> str:
    """
    Tool: Searches the user's Gmail inbox for specific threads or messages.
    """
    logger.info(f"[Tool Execution] Searching Gmail for user {user_id} with query: {query}")
    gmail = _get_gmail_client()
    results = _run_sync(gmail.search_emails(user_id, query, max_results=5))
    if not results:
        return "No emails found matching the search query parameters."

    # Truncate email bodies before injecting into LLM context to prevent TPM limit exhaustion.
    # Full body is still available when the user taps 'Read Full Email' in the UI.
    optimized_results = []
    for email in results:
        if isinstance(email, dict):
            body = email.get("body", "")
            opt_email = {
                **email,
                "body": body[:1000] + ("... [Truncated for AI context]" if len(body) > 1000 else "")
            }
            optimized_results.append(opt_email)
        else:
            optimized_results.append(email)
    return json.dumps(optimized_results)


def prepare_email_draft_tool(to_email: str, subject: str, body: str, user_id: int) -> str:
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

    # Cache draft in module-level pending_drafts for Telegram Handler retrieval
    _module_pending_drafts[user_id] = draft
    return json.dumps({"status": "success", "draft": draft})


def schedule_email_tool(to_email: str, subject: str, body: str, scheduled_time: str, user_id: int) -> str:
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


def save_contact_tool(name: str, email: str, user_id: int) -> str:
    """
    Tool: Saves or updates an address book contact in the user's Supabase contacts table.
    """
    logger.info(f"[Tool Execution] Saving Contact | Name: {name} | Email: {email} for User: {user_id}")

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

        # Reference to the module-level pending_drafts for Telegram handler retrieval.
        # This lets TelegramBotManager pop drafts via ai_engine.pending_drafts (backward compat).
        self.pending_drafts = _module_pending_drafts

        # Multi-user conversation history cache for persistent stateful chat sessions
        self.active_chats: Dict[int, List[types.Content]] = {}

    # ==========================================
    # SCRIPT / LANGUAGE DETECTION
    # ==========================================

    @staticmethod
    def _detect_user_script(text: str) -> str:
        """
        Detects the script/language the user is writing in.
        Returns a human-readable instruction for the LLM to mirror.
        """
        # Gurmukhi (Punjabi native script)
        if re.search(r'[\u0A00-\u0A7F]', text):
            return "Punjabi (Gurmukhi script ਪੰਜਾਬੀ). Reply using Gurmukhi script."
        # Arabic/Urdu script
        if re.search(r'[\u0600-\u06FF]', text):
            return "Urdu (Arabic/Nastaliq script اردو). Reply using Urdu Arabic script."
        # Devanagari (Hindi)
        if re.search(r'[\u0900-\u097F]', text):
            return "Hindi (Devanagari script हिन्दी). Reply using Devanagari script."

        # Roman Urdu / Roman Punjabi detection (Latin script but South Asian language)
        # IMPORTANT: Only use unambiguous South Asian markers — NOT generic English words
        # like 'the', 'check', 'please' which previously caused false positive misclassifications.
        roman_urdu_markers = [
            'kya', 'hai', 'rha', 'rhi', 'krna', 'karo', 'mujhe', 'mujh',
            'tumhe', 'aap', 'yeh', 'woh', 'nahi', 'haan', 'bhai', 'yar',
            'bata', 'bhej', 'dekh', 'suna', 'sunao', 'bol', 'batao',
            'kaise', 'kaisa', 'kaisi', 'abhi', 'pehle', 'baad',
            'ko', 'ka', 'ki', 'hain', 'tha', 'thi',
            'ga', 'gi', 'ge', 'kar', 'kr', 'hn', 'hoon',
            'zaroor', 'shukriya', 'theek', 'acha', 'achha',
            'bhejo', 'likho', 'padho', 'dikhao',
        ]
        words = text.lower().split()
        # Require at least 2 markers OR a single marker in a very short message
        match_count = sum(1 for w in words if w in roman_urdu_markers)
        if match_count >= 2 or (len(words) <= 5 and match_count >= 1):
            return "Roman Urdu (Urdu written in Latin/English alphabet). Reply in Roman Urdu using Latin letters. Do NOT use Arabic/Nastaliq script."

        return "English. Reply in English."

    # ==========================================
    # GROQ FALLBACK PIPELINE
    # ==========================================

    async def _groq_fallback_chat(self, message: str, telegram_id: int, system_instructions: str, tools_map: dict) -> str:
        """
        Triggered automatically when Gemini hits API rate limits (429) or other errors.
        Routes the existing context and tools directly to Llama-3-70b on Groq.
        """
        if not settings.GROQ_API_KEY:
            return "⚠️ Gemini LLM limits reached and Groq API Fallback is not configured. Please wait a few seconds."

        # Map Gemini History Schema to Groq (OpenAI) Chat Schema
        raw_messages = []
        for turn in self.active_chats.get(telegram_id, []):
            role = "user" if turn.role == "user" else "assistant"
            text_content = ""
            for part in getattr(turn, "parts", []):
                if hasattr(part, "text") and part.text:
                    text_content += part.text
            if text_content.strip():
                raw_messages.append({"role": role, "content": text_content.strip()})

        # Append the current user request
        if message.strip():
            raw_messages.append({"role": "user", "content": message.strip()})

        # Alternate roles and merge consecutive roles to satisfy strict OpenAI/Groq requirements
        messages = [{"role": "system", "content": system_instructions}]
        for m in raw_messages:
            if messages and messages[-1]["role"] == m["role"]:
                messages[-1]["content"] += "\n" + m["content"]
            else:
                messages.append(m)

        # Map Custom Tools to Groq Functions
        groq_tools = [
            {
                "type": "function",
                "function": {
                    "name": "search_gmail_tool",
                    "description": "Searches the user's Gmail inbox for specific threads or messages.",
                    "parameters": {"type": "object", "properties": {"query": {"type": "string"}}, "required": ["query"]}
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "prepare_email_draft_tool",
                    "description": "Prepares and stages an immediate email draft.",
                    "parameters": {"type": "object", "properties": {"to_email": {"type": "string"}, "subject": {"type": "string"}, "body": {"type": "string"}}, "required": ["to_email", "subject", "body"]}
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "schedule_email_tool",
                    "description": "Schedules an email for future automated dispatch.",
                    "parameters": {"type": "object", "properties": {"to_email": {"type": "string"}, "subject": {"type": "string"}, "body": {"type": "string"}, "scheduled_time": {"type": "string"}}, "required": ["to_email", "subject", "body", "scheduled_time"]}
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "save_contact_tool",
                    "description": "Saves or updates an address book contact.",
                    "parameters": {"type": "object", "properties": {"name": {"type": "string"}, "email": {"type": "string"}}, "required": ["name", "email"]}
                }
            }
        ]

        url = "https://api.groq.com/openai/v1/chat/completions"
        headers = {"Authorization": f"Bearer {settings.GROQ_API_KEY}", "Content-Type": "application/json"}
        payload = {
            "model": "llama-3.3-70b-versatile",
            "messages": messages,
            "tools": groq_tools,
            "tool_choice": "auto",
            "temperature": 0.2
        }

        try:
            async with httpx.AsyncClient(timeout=45.0) as client:
                response = await client.post(url, headers=headers, json=payload)
                # Log full response body on error for easier debugging
                if response.status_code != 200:
                    logger.error(f"Groq API returned {response.status_code}: {response.text}")
                response.raise_for_status()
                data = response.json()

                choice = data["choices"][0]["message"]

                if choice.get("tool_calls"):
                    tool_call = choice["tool_calls"][0]
                    fn_name = tool_call["function"]["name"]
                    args = json.loads(tool_call["function"]["arguments"])
                    args["user_id"] = telegram_id

                    try:
                        func = tools_map[fn_name]
                        result_str = func(**args)

                        if "TOKEN_EXPIRED_REAUTH_REQUIRED" in result_str:
                            return "TOKEN_EXPIRED_REAUTH_REQUIRED"

                        # Intercept interactive UI cards and return early
                        if "prepare_draft" in result_str or "schedule_email" in result_str:
                            # Store a clean user+model pair so Groq history stays valid
                            self.active_chats.setdefault(telegram_id, []).append(
                                types.Content(role="user", parts=[types.Part.from_text(text=message)])
                            )
                            self.active_chats[telegram_id].append(
                                types.Content(role="model", parts=[types.Part.from_text(text="Draft/schedule prepared and displayed to user.")])
                            )
                            return result_str

                        # Complete standard tool-return execution for Groq
                        messages.append(choice)
                        messages.append({
                            "role": "tool",
                            "tool_call_id": tool_call["id"],
                            "name": fn_name,
                            "content": result_str
                        })
                        payload["messages"] = messages

                        resp2 = await client.post(url, headers=headers, json=payload)
                        if resp2.status_code != 200:
                            logger.error(f"Groq second call returned {resp2.status_code}: {resp2.text}")
                        resp2.raise_for_status()
                        final_text = resp2.json()["choices"][0]["message"].get("content", "")

                        self.active_chats.setdefault(telegram_id, []).append(
                            types.Content(role="user", parts=[types.Part.from_text(text=message)])
                        )
                        self.active_chats[telegram_id].append(
                            types.Content(role="model", parts=[types.Part.from_text(text=final_text)])
                        )
                        return final_text

                    except Exception as tool_err:
                        logger.error(f"Groq tool error: {tool_err}")
                        return f"Error executing tool during fallback: {tool_err}"
                else:
                    # Plain chat response
                    content = choice.get("content", "")
                    self.active_chats.setdefault(telegram_id, []).append(
                        types.Content(role="user", parts=[types.Part.from_text(text=message)])
                    )
                    self.active_chats[telegram_id].append(
                        types.Content(role="model", parts=[types.Part.from_text(text=content)])
                    )
                    return content

        except httpx.HTTPStatusError as e:
            logger.error(f"Groq HTTP error {e.response.status_code}: {e.response.text}")
            return "⚠️ System is experiencing extremely high traffic and both AI nodes failed. Please try again shortly."
        except Exception as e:
            logger.error(f"Groq Fallback also failed: {e}")
            return "⚠️ System is experiencing extremely high traffic and both AI nodes failed. Please try again shortly."

    # ==========================================
    # CORE AGENT REASONING ENGINE
    # ==========================================

    async def agent_chat(self, message: str, telegram_id: int) -> str:
        """
        Primary entry point for processing conversational user prompts.
        Wrapped in Try-Except to failover to Groq seamlessly.
        """
        try:
            contacts_list = await contact_manager.get_contacts(telegram_id)
            contacts_context = "\n".join([
                f"- {c.get('contact_alias')} ({c.get('contact_name')}): {c.get('email_address')}"
                for c in contacts_list
            ])

            raw_summaries = await memory_manager.get_recent_summaries(telegram_id, limit=settings.MAX_CONTEXT_MESSAGES)
            recent_summaries = raw_summaries[:settings.MAX_CONTEXT_MESSAGES] if raw_summaries else []
            history_context = "\n".join([
                f"Topic: {s.get('current_topic')} | Summary: {s.get('summary_text')}"
                for s in recent_summaries
            ])

            utc_now = datetime.utcnow().replace(tzinfo=timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")

            # Detect the user's script/language for mirroring
            detected_script = self._detect_user_script(message)

            system_instructions = (
                "IDENTITY LOCK: You are the 'Smart Email Assistant', an elite agentic system running inside Telegram.\n"
                "NEVER break character. NEVER use generic AI disclaimers like 'As a large language model' or 'As an AI'.\n"
                "You ALREADY have full authorization and direct access to the user's Gmail via your tools. NEVER claim you lack access. NEVER claim you are just an AI model.\n\n"

                f"LANGUAGE & SCRIPT MIRRORING (MANDATORY):\n"
                f"The user is currently writing in: {detected_script}\n"
                f"You MUST respond using the EXACT SAME language and script/alphabet as the user. "
                f"If user writes in Roman Urdu (Latin letters), reply in Roman Urdu using Latin letters. "
                f"If user writes in Gurmukhi, reply in Gurmukhi. If user writes in Urdu script, reply in Urdu script. "
                f"NEVER switch to a different alphabet than what the user is using. CRITICAL: If the user writes in Roman Urdu, you MUST write your reply in Roman Urdu (Latin alphabet). DO NOT reply in Arabic script or Devanagari script.\n\n"

                "VOICE TAG RULES (STRICT):\n"
                "Append the tag '[VOICE]' at the VERY END of your response ONLY if the user's CURRENT message "
                "explicitly requests a voice or audio response using words like: 'voice', 'voice mein', 'audio', "
                "'suna', 'sunao', 'bol ke batao', 'speak', 'read aloud', 'voice note'.\n"
                "DO NOT add [VOICE] for any other reason. DO NOT add [VOICE] just because the user is speaking a regional language. "
                "DO NOT add [VOICE] for language translation requests. DO NOT add [VOICE] for drafting or searching emails.\n\n"

                "DIRECT RESPONSE RULE:\n"
                "Answer the user's exact intent directly and concisely. Do NOT send greeting messages or emojis when performing actions. NEVER output raw JSON data or function call payloads directly in the text response. Focus purely on fulfilling the user's request with minimum filler.\n\n"

                f"Your goal is to assist the user in reading, searching, summarizing, drafting, and scheduling emails.\n"
                f"Current Date and Time: {utc_now}\n\n"
                f"User's Address Book (Always search here first when names are mentioned):\n"
                f"{contacts_context or 'No saved contacts in database yet.'}\n\n"
                f"Recent Conversation Memory Context:\n"
                f"{history_context or 'No prior conversation history recorded.'}\n\n"

                "CRITICAL SYSTEM DIRECTIVES (STRICT COMPLIANCE REQUIRED):\n"
                "1. SEARCHING EMAILS: When the user asks to search, find, read, or check their inbox, you MUST IMMEDIATELY call the 'search_gmail_tool'. DO NOT explain that you are an AI, DO NOT make excuses. Just call the tool.\n"
                "2. DRAFTING/SENDING EMAILS: When the user asks to write, draft, reply, or send an email, you MUST IMMEDIATELY call the 'prepare_email_draft_tool'. NEVER write the email draft as plain text in your response. NEVER ask 'Shall I prepare it?' or 'Shall I send it?'. Call the tool immediately so the system can render the interactive Draft UI Card.\n"
                "3. SCHEDULING EMAILS: When the user asks to schedule an email, IMMEDIATELY call the 'schedule_email_tool'.\n"
                "4. HITL GUARDRAIL: If calling 'prepare_email_draft_tool' or 'schedule_email_tool' and you do not know the exact recipient email address (from history or Address Book), you MUST strictly use '[Specify Recipient Email]' as the to_email parameter. NEVER make up or guess email addresses.\n"
                "5. PLAIN CHAT: Only return a normal conversational response when answering general questions that do not require email actions.\n"
                "6. EMAIL DISPLAY: When the user asks to show, read, check, or get a specific email from search results, "
                "include the email's message ID in your response using this exact format: [SHOW_EMAIL:<message_id>]. "
                "This will trigger the interactive email card UI. Only use this tag when you have a real message ID from search results.\n"
                "EXAMPLE DIALOGUE:\n"
                "User: Show my last email.\n"
                "AI Call: search_gmail_tool(...)\n"
                'Tool Response: [{"id": "18f9a...", "subject": "Meeting"}]\n'
                'AI Response: I found your last email about "Meeting". [SHOW_EMAIL:18f9a...]'
            )

            # Build the tools map referencing standalone module-level functions.
            # CRITICAL: These MUST be module-level functions (not self.method) to avoid
            # the `cannot pickle '_thread.lock'` error caused by SDK deep-copying the config.
            tools_map = {
                "search_gmail_tool": search_gmail_tool,
                "prepare_email_draft_tool": prepare_email_draft_tool,
                "schedule_email_tool": schedule_email_tool,
                "save_contact_tool": save_contact_tool,
            }

            # Safety settings set to BLOCK_NONE across all harm categories.
            # Without this, Gemini's default filters silently block tool calls for
            # email access and the model hallucinates "authentication error" excuses
            # instead of calling search_gmail_tool / prepare_email_draft_tool.
            _safety_off = [
                types.SafetySetting(category="HARM_CATEGORY_DANGEROUS_CONTENT",  threshold="OFF"),
                types.SafetySetting(category="HARM_CATEGORY_HARASSMENT",          threshold="OFF"),
                types.SafetySetting(category="HARM_CATEGORY_HATE_SPEECH",         threshold="OFF"),
                types.SafetySetting(category="HARM_CATEGORY_SEXUALLY_EXPLICIT",   threshold="OFF"),
                types.SafetySetting(category="HARM_CATEGORY_CIVIC_INTEGRITY",     threshold="OFF"),
            ]
            config = types.GenerateContentConfig(
                system_instruction=system_instructions,
                tools=list(tools_map.values()),
                temperature=0.2,
                safety_settings=_safety_off,
            )

            if telegram_id not in self.active_chats:
                self.active_chats[telegram_id] = []

            # Prune history: keep within token budget, always starting with a user turn
            max_turns = settings.MAX_CONTEXT_MESSAGES * 2
            if len(self.active_chats[telegram_id]) > max_turns:
                trimmed = self.active_chats[telegram_id][-max_turns:]
                # Scan forward to find first user-role turn to avoid broken tool sequences
                for i in range(len(trimmed)):
                    if getattr(trimmed[i], "role", "") == "user":
                        trimmed = trimmed[i:]
                        break
                self.active_chats[telegram_id] = trimmed

            user_part = types.Part.from_text(text=message)
            user_content = types.Content(role="user", parts=[user_part])
            contents = self.active_chats[telegram_id] + [user_content]

            logger.info(f"Triggering Gemini 2.5 Flash for user: {telegram_id}")

            try:
                response = await self.client.aio.models.generate_content(
                    model=self.model_name,
                    contents=contents,
                    config=config,
                )
            except Exception as gemini_err:
                logger.warning(f"Gemini Engine Blocked/Rate-limited ({gemini_err}). Triggering Groq Fallback...")
                return await self._groq_fallback_chat(message, telegram_id, system_instructions, tools_map)

            # --- STANDARD GEMINI PROCESSING ---
            if response.function_calls:
                results_parts = []
                for fc in response.function_calls:
                    fn_name = fc.name
                    args = dict(fc.args)

                    if fn_name in ["search_gmail_tool", "prepare_email_draft_tool", "schedule_email_tool", "save_contact_tool"]:
                        args["user_id"] = telegram_id

                    try:
                        func = tools_map[fn_name]
                        result_str = func(**args)

                        if "TOKEN_EXPIRED_REAUTH_REQUIRED" in result_str:
                            return "TOKEN_EXPIRED_REAUTH_REQUIRED"

                        if "prepare_draft" in result_str or "schedule_email" in result_str:
                            # Append valid 4-step history: user -> model(tool_call) -> tool(result) -> model(ack)
                            # This prevents Gemini 400 errors on the next message due to incomplete tool loops.
                            self.active_chats[telegram_id].append(user_content)
                            self.active_chats[telegram_id].append(response.candidates[0].content)
                            tool_ack_part = types.Part.from_function_response(
                                name=fn_name, response={"result": result_str}
                            )
                            self.active_chats[telegram_id].append(
                                types.Content(role="tool", parts=[tool_ack_part])
                            )
                            self.active_chats[telegram_id].append(
                                types.Content(role="model", parts=[types.Part.from_text(text="Draft/schedule prepared and displayed to user.")])
                            )
                            return result_str

                        results_parts.append(
                            types.Part.from_function_response(name=fn_name, response={"result": result_str})
                        )
                    except Exception as tool_err:
                        logger.error(f"Error executing tool {fn_name}: {tool_err}")
                        results_parts.append(
                            types.Part.from_function_response(name=fn_name, response={"error": str(tool_err)})
                        )

                try:
                    # Gemini SDK requires function-response parts to be wrapped
                    # inside a Content object (role="tool") — passing a bare List[Part]
                    # causes the SDK to reject or silently misparse the payload, which
                    # makes the second call fail and drops to Groq unnecessarily.
                    tool_result_content = types.Content(
                        role="tool",
                        parts=results_parts,
                    )
                    _call_contents = contents + [response.candidates[0].content, tool_result_content]
                    final_response = await self.client.aio.models.generate_content(
                        model=self.model_name,
                        contents=_call_contents,
                        config=config,
                    )
                    self.active_chats[telegram_id].append(user_content)
                    self.active_chats[telegram_id].append(response.candidates[0].content)
                    self.active_chats[telegram_id].append(tool_result_content)
                    self.active_chats[telegram_id].append(final_response.candidates[0].content)
                    return final_response.text or "I completed the action successfully."
                except Exception as final_err:
                    logger.warning(f"Gemini secondary tool parsing failed ({final_err}). Falling back to Groq...")
                    return await self._groq_fallback_chat(message, telegram_id, system_instructions, tools_map)

            self.active_chats[telegram_id].append(user_content)
            self.active_chats[telegram_id].append(response.candidates[0].content)
            return response.text or "I processed your request."

        except Exception as e:
            logger.error(f"AIEngine.agent_chat error: {e}", exc_info=True)
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
                        if response.status_code != 200:
                            logger.error(f"Groq Whisper error {response.status_code}: {response.text}")
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
                uploaded_file = await self.client.aio.files.upload(
                    file=file_path
                )

                response = await self.client.aio.models.generate_content(
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
    # TOKEN-EFFICIENT UTILITY CORES
    # ==========================================
    # These methods use direct single-turn LLM calls (no tools, no history) to keep
    # token costs minimal and prevent email body content from polluting the chat session.

    async def summarize_email(self, email_body: str) -> str:
        """
        Generates a concise, actionable 3-bullet point email summary.
        Uses a direct single-turn call — does NOT update active_chats history.
        """
        try:
            prompt = (
                "You are an executive email processing assistant. "
                "Analyze the email content below and extract exactly 3 short, actionable bullet points.\n"
                "Focus strictly on core dates, metrics, and actionable deliverables. Be extremely brief.\n\n"
                f"Email Body Content:\n{email_body[:5000]}"
            )
            response = await self.client.aio.models.generate_content(
                model=self.model_name,
                contents=prompt
            )
            return response.text.strip() if response.text else "Summary unavailable."
        except Exception as e:
            logger.error(f"Summarize email error: {e}")
            return "Email abstractive summary failed due to internal analytical errors."

    async def generate_tts_summary(self, email_body: str) -> str:
        """
        Generates a 2-3 sentence spoken summary optimized for text-to-speech delivery.
        Uses a direct single-turn call — does NOT update active_chats history.
        """
        try:
            prompt = (
                "You are a voice assistant. Read the following email and write a natural, spoken summary "
                "in exactly 2-3 sentences. Use simple, clear language suitable for text-to-speech playback. "
                "Do not use bullet points, markdown symbols, or special characters.\n\n"
                f"Email:\n{email_body[:3000]}"
            )
            response = await self.client.aio.models.generate_content(
                model=self.model_name,
                contents=prompt
            )
            return response.text.strip() if response.text else "Unable to generate audio summary."
        except Exception as e:
            logger.error(f"TTS summary generation error: {e}")
            return "Audio summary generation failed."

    async def analyze_attachment(self, file_path: str, prompt: str) -> str:
        """
        Analyzes locally downloaded document or image attachments using Gemini file uploader.
        Uses a direct single-turn call — does NOT update active_chats history.
        """
        try:
            config = types.GenerateContentConfig(temperature=0.2)
            sample_file = await self.client.aio.files.upload(file=file_path)
            response = await self.client.aio.models.generate_content(
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
        Uses a direct single-turn call — does NOT update active_chats history.
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
            response = await self.client.aio.models.generate_content(
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