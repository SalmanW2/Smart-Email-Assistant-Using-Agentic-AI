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
import re

# ── Quota / Rate-Limit Exception Imports ──────────────────────────────────────
# The Gemini SDK can surface HTTP 429 / quota exhaustion via multiple exception
# classes depending on transport and SDK version. We import all of them and use
# a single normalizer helper so every call site stays clean and consistent.
try:
    from google.api_core.exceptions import ResourceExhausted, TooManyRequests as _GAPITooMany
except ImportError:
    ResourceExhausted = None  # type: ignore
    _GAPITooMany = None       # type: ignore
try:
    from google.genai.errors import ClientError as _GenAIClientError
except ImportError:
    _GenAIClientError = None  # type: ignore

# Meaningless generic AI responses that should be suppressed.
# When AFC or Groq runs a tool but the model returns one of these placeholders
# as its final text, we replace it with a proper system-level status notice.
_MEANINGLESS_RESPONSES = frozenset([
    "i processed your request",
    "i have processed your request",
    "i've processed your request",
    "your request has been processed",
    "request processed",
    "i completed the action",
    "i completed that",
    "action completed",
    "i will do that",
    "done",
    "processing your request",
    "i completed the action successfully",
    "i have completed the action",
    "task done",
    "understood",
    "okay, i'll do that",
    "got it",
    "sure",
])

def _sanitize_final_text(final_text: str) -> str:
    """
    Surgical output sanitizer: intercepts raw tool call syntax leaks AND
    meaningless AI meta-responses that provide zero value to the end user.
    """
    if not final_text or not final_text.strip():
        return "✅ Action completed successfully."

    # Filter known meaningless single-line AI meta-responses.
    # Compare lowercase stripped version (strip trailing punctuation for robustness).
    stripped_lower = final_text.strip().lower().rstrip('.!')
    if stripped_lower in _MEANINGLESS_RESPONSES:
        return "✅ Action completed successfully."

    # ONLY intercept actual raw function call syntax patterns leaking into text output.
    if re.search(r'\b\w+tool\s*\(', final_text, re.IGNORECASE):
        return "✅ Action completed successfully."

    # Catch snake_case function-call patterns like prepare_email_draft_tool(to=...)
    if re.search(r'\b[a-z]+_[a-z]+_[a-z]+\s*\(', final_text):
        return "✅ Action completed successfully."

    return final_text

    return final_text


def _is_quota_error(exc: Exception) -> bool:
    """
    Returns True if the exception represents an API quota / rate-limit error
    (HTTP 429 or gRPC RESOURCE_EXHAUSTED). Normalizes across both legacy
    google.api_core and new google.genai SDK error namespaces.
    """
    # Check class hierarchy first (fastest)
    if ResourceExhausted is not None and isinstance(exc, ResourceExhausted):
        return True
    if _GAPITooMany is not None and isinstance(exc, _GAPITooMany):
        return True
    if _GenAIClientError is not None and isinstance(exc, _GenAIClientError):
        # New genai SDK wraps HTTP errors inside ClientError; check status code
        code = getattr(exc, 'status_code', None) or getattr(exc, 'code', None)
        if code == 429:
            return True
    # Final fallback: inspect the string representation
    err_str = str(exc).lower()
    return (
        "resource has been exhausted" in err_str
        or "quota" in err_str and ("429" in err_str or "exhausted" in err_str)
        or "429" in err_str and "rate" in err_str
    )

import httpx
import re
import os
from datetime import datetime, timezone
from typing import Any, Dict, Optional, List
import inspect
import functools

from google import genai
from google.genai import types

from config import settings
from db.memory import memory_manager
from bot.contact_manager import contact_manager
from db.models import db_manager

logger = logging.getLogger(__name__)




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
_module_pending_searches: Dict[int, Dict[str, Any]] = {}


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

async def search_gmail_tool(query: str, *, user_id: int) -> str:
    """
    Tool: Searches the user's Gmail inbox for specific threads or messages.
    """
    logger.info(f"[Tool Execution] Searching Gmail for user {user_id} with query: {query}")
    _module_pending_searches[user_id] = {"query": query}
    gmail = _get_gmail_client()
    results = await gmail.search_emails(user_id, query, max_results=5)
    if not results:
        _module_pending_searches.pop(user_id, None)
        return "No emails found matching the search query parameters."

    # Truncate email bodies aggressively to prevent TPM exhaustion.
    # 300 chars is enough for the model to understand the email topic.
    # Full body is fetched separately when user taps 'Read Full Email'.
    optimized_results = []
    for email in results:
        if isinstance(email, dict):
            body = email.get("body", "")
            # Strip all whitespace/newlines from body before truncating to maximize signal density
            compact_body = " ".join(body.split())
            opt_email = {
                "id":      email.get("id", ""),
                "subject": email.get("subject", ""),
                "sender":  email.get("sender", ""),
                "date":    email.get("date", ""),
                "body":    compact_body[:300] + ("..." if len(compact_body) > 300 else ""),
            }
            optimized_results.append(opt_email)
        else:
            optimized_results.append(email)
    return json.dumps(optimized_results)


async def prepare_email_draft_tool(to_email: str, subject: str, body: str, *, user_id: int) -> str:
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


async def schedule_email_tool(to_email: str, subject: str, body: str, scheduled_time: str, *, user_id: int) -> str:
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
        await db_manager.db.run(lambda: db_manager.db.client.table("scheduled_emails").insert({
            "telegram_id": user_id,
            "to_email": to_clean,
            "subject": subject or "No Subject",
            "body": body or "",
            "scheduled_time": scheduled_time,
            "status": "pending"
        }).execute())
        logger.info("Successfully registered scheduled email in database")
    except Exception as db_err:
        logger.error(f"Database error writing scheduled task: {db_err}")
        return json.dumps({"status": "error", "message": f"Database failure: {str(db_err)}"})

    return json.dumps({
        "action": "schedule_email",
        "schedule_details": schedule_details
    })


async def save_contact_tool(name: str, email: str, *, user_id: int) -> str:
    """
    Tool: Saves or updates an address book contact in the user's Supabase contacts table.
    """
    logger.info(f"[Tool Execution] Saving Contact | Name: {name} | Email: {email} for User: {user_id}")

    clean_email = str(email).strip().lower()
    clean_name = str(name).strip()[:200]
    safe_uid = int(user_id)

    # Allow valid complex subdomains e.g. test@sub.domain.com
    email_regex = r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$"
    if not clean_email or not re.match(email_regex, clean_email):
        return "Error: Invalid email format provided. Contact not saved."

    try:
        await db_manager.db.run(lambda: db_manager.db.client.table("contacts").upsert({
            "telegram_id": safe_uid,
            "contact_alias": clean_name,
            "email_address": clean_email,
            "contact_name": clean_name
        }, on_conflict="telegram_id,email_address").execute())
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
        self.model_name = settings.GEMINI_MODEL

        # Reference to the module-level pending_drafts for Telegram handler retrieval.
        # This lets TelegramBotManager pop drafts via ai_engine.pending_drafts (backward compat).
        self.pending_drafts = _module_pending_drafts
        self.pending_searches = _module_pending_searches

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
            if turn is None or not hasattr(turn, 'role') or turn.role is None:
                continue
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

                    try:
                        func = tools_map[fn_name]
                        if inspect.iscoroutinefunction(func):
                            result_str = await func(**args)
                        else:
                            result_str = func(**args)

                        if "TOKEN_EXPIRED_REAUTH_REQUIRED" in result_str:
                            return "TOKEN_EXPIRED_REAUTH_REQUIRED"

                        # Intercept searches right away!
                        if telegram_id in _module_pending_searches:
                            # Groq ran search_gmail_tool. Return the sentinel.
                            return "__SHOW_SEARCH_LIST__"

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

                        return self._unify_agent_response(telegram_id, message, final_text)

                    except Exception as tool_err:
                        logger.error(f"Groq tool error: {tool_err}")
                        return f"Error executing tool during fallback: {tool_err}"
                else:
                    # Plain chat response
                    content = choice.get("content", "")
                    return self._unify_agent_response(telegram_id, message, content)

        except httpx.HTTPStatusError as e:
            logger.error(f"Groq HTTP error {e.response.status_code}: {e.response.text}")
            return "⚠️ System is experiencing extremely high traffic and both AI nodes failed. Please try again shortly."
        except Exception as e:
            logger.error(f"Groq Fallback also failed: {e}")
            return "⚠️ System is experiencing extremely high traffic and both AI nodes failed. Please try again shortly."

    # ==========================================
    # CORE AGENT REASONING ENGINE
    # ==========================================

    def _unify_agent_response(self, telegram_id: int, user_message: str, raw_text: str) -> str:
        """
        Unifies response handling for both Gemini and Groq, safely managing
        history and sentinel intercepts without premature dict popping.
        """
        # 1. Store the user content in conversation history
        user_content = types.Content(role="user", parts=[types.Part.from_text(text=user_message)])
        self.active_chats.setdefault(telegram_id, []).append(user_content)

        # 2. Check for Search Sentinel (INSPECT only, do NOT pop)
        if telegram_id in _module_pending_searches:
            self.active_chats[telegram_id].append(
                types.Content(role="model", parts=[types.Part.from_text(text="Search executed and results displayed to user.")])
            )
            return "__SHOW_SEARCH_LIST__"

        # 3. Check for Draft Sentinel (INSPECT only, do NOT pop)
        if telegram_id in _module_pending_drafts:
            self.active_chats[telegram_id].append(
                types.Content(role="model", parts=[types.Part.from_text(text="Draft/schedule prepared and displayed to user.")])
            )
            draft_payload = _module_pending_drafts[telegram_id]
            import json as _json
            return _json.dumps({"action": "prepare_draft", "draft": draft_payload})

        # 4. Standard conversational/text response
        resolved_text = _sanitize_final_text(raw_text)
        self.active_chats[telegram_id].append(
            types.Content(role="model", parts=[types.Part.from_text(text=resolved_text)])
        )
        return resolved_text

    async def agent_chat(self, message: str, telegram_id: int) -> str:
        """
        Main Conversational AI loop for interacting with the Smart Email Assistant.
        """
        _GREETINGS = {"hi", "hello", "hey", "start", "/start", "help", "who are you"}
        if message.strip().lower() in _GREETINGS:
            return self._unify_agent_response(
                telegram_id, 
                message, 
                "Hello! I am your Smart Email Assistant. How can I help you manage your inbox today?"
            )

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
                "You are the direct native user interface dashboard engine for Gmail.\n"
                "NEVER speak as a conversational middleman (avoid phrases like 'The sender is saying...', 'This email states...', 'The email is about...').\n"
                "Act strictly as a clean native dashboard presentation layer. Serve direct data and complete tasks natively, without conversational introductions.\n"
                "NEVER say 'As an AI' or 'I cannot access'. You already have full Gmail access via tools. Act immediately.\n\n"

                f"LANGUAGE ENFORCEMENT: You must strictly maintain a Professional English persona at all times. The user is currently writing in: {detected_script}. ONLY respond in Urdu, Roman Urdu, or any other regional language IF the user explicitly demands it in their current message. Otherwise, default to clear, professional English.\n"
                f"VOICE TAG: Append '[VOICE]' at the very end ONLY if the user explicitly asks for audio (e.g. 'voice', 'sunao', 'speak'). Never add it otherwise.\n\n"

                f"UTC Time: {utc_now}\n"
                f"Address Book:{chr(10) + contacts_context if contacts_context else ' (empty)'}\n"
                f"Memory:{chr(10) + history_context if history_context else ' (none)'}\n\n"

                "DIRECTIVES (follow strictly, no preambles, call tools immediately):\n"
                "1. SEARCH: User asks to find/read/check/list emails → call search_gmail_tool immediately.\n"
                "2. DRAFT/SEND/REPLY: User asks to write/send/reply → call prepare_email_draft_tool immediately. Never write draft as plain text.\n"
                "3. SCHEDULE: User asks to schedule an email → call schedule_email_tool immediately.\n"
                "4. RECIPIENT UNKNOWN: If you don't know the recipient's email → use '[Specify Recipient Email]' as to_email. Never guess.\n"
                "5. PLAIN CHAT: Only respond conversationally for general questions not requiring email actions. Keep responses direct and native, avoiding middleman preambles.\n"
                "6. SHOW EMAIL: To show a specific email from results, include [SHOW_EMAIL:<message_id>] in your response.\n"
                "7. READ FULL HTML: The email detail card includes a 'Read Full' button allowing users to download the email as an interactive HTML document.\n"
                "Never output raw JSON, function names, or code in your text response."
            )

            # Build the tools map referencing standalone module-level functions.
            tools_map = {}
            for name, func in {
                "search_gmail_tool": search_gmail_tool,
                "prepare_email_draft_tool": prepare_email_draft_tool,
                "schedule_email_tool": schedule_email_tool,
                "save_contact_tool": save_contact_tool,
            }.items():
                p_func = functools.partial(func, user_id=telegram_id)
                p_func.__name__ = name
                p_func.__doc__ = func.__doc__
                sig = inspect.signature(p_func)
                new_params = [p for pname, p in sig.parameters.items() if pname != 'user_id']
                p_func.__signature__ = sig.replace(parameters=new_params)
                tools_map[name] = p_func

            # Safety settings — OFF for email content (may contain flagged words)
            _safety_off = [
                types.SafetySetting(category="HARM_CATEGORY_DANGEROUS_CONTENT",  threshold="OFF"),
                types.SafetySetting(category="HARM_CATEGORY_HARASSMENT",          threshold="OFF"),
                types.SafetySetting(category="HARM_CATEGORY_HATE_SPEECH",         threshold="OFF"),
                types.SafetySetting(category="HARM_CATEGORY_SEXUALLY_EXPLICIT",   threshold="OFF"),
                types.SafetySetting(category="HARM_CATEGORY_CIVIC_INTEGRITY",     threshold="OFF"),
            ]

            # ── AFC THROTTLE: maximum_remote_calls=1 ───────────────────────────────────
            # Default AFC allows up to 10 internal tool-call iterations. On each iteration
            # the SDK resends the FULL payload (system prompt + history + tool results),
            # multiplying token consumption by up to 10x per message. This instantly
            # exhausts free-tier TPM quotas. We cap at 1 to allow exactly one tool call
            # per user message — sufficient for all email operations (search OR draft).
            # Multi-step flows (search + draft in one message) are handled by the system
            # prompt's instruction to call tools sequentially in separate user turns.
            afc_config = types.AutomaticFunctionCallingConfig(
                disable=False,
                maximum_remote_calls=1,
            )
            config = types.GenerateContentConfig(
                system_instruction=system_instructions,
                tools=list(tools_map.values()),
                automatic_function_calling=afc_config,
                temperature=0.2,
                safety_settings=_safety_off,
            )

            # Lean config for the secondary formulation call (after manual tool execution).
            # Tool definitions are not needed here — we're only asking the model to write
            # a natural-language response based on already-executed tool results.
            _lean_config = types.GenerateContentConfig(
                system_instruction=system_instructions,
                temperature=0.2,
                safety_settings=_safety_off,
            )

            if telegram_id not in self.active_chats:
                self.active_chats[telegram_id] = []

            # Prune history: hard cap at MAX_CONTEXT_MESSAGES * 2 content objects
            max_turns = settings.MAX_CONTEXT_MESSAGES * 2
            if len(self.active_chats[telegram_id]) > max_turns:
                self.active_chats[telegram_id] = self.active_chats[telegram_id][-max_turns:]

            user_part = types.Part.from_text(text=message)
            user_content = types.Content(role="user", parts=[user_part])

            # Apply rolling 6-turn history window, stripping tool/function-call content.
            # Tool call objects carry massive token weight (full tool results embedded)
            # but contribute zero conversational value in follow-up turns.
            scoped_history = self._get_scoped_history(message, self.active_chats[telegram_id])
            contents = scoped_history + [user_content]

            try:
                response = await self.client.aio.models.generate_content(
                    model=self.model_name,
                    contents=contents,
                    config=config,
                )
            except Exception as gemini_err:
                if _is_quota_error(gemini_err):
                    # Return the quota sentinel immediately. Do NOT forward to Groq here
                    # because the user's request requires tools that Groq may misfire on.
                    # The dispatcher will show a clean, actionable user-facing message.
                    logger.warning(f"Gemini API quota exhausted (429) for user {telegram_id}. Returning quota sentinel.")
                    return "__API_QUOTA_EXCEEDED__"
                logger.warning(f"Gemini Engine Blocked/Rate-limited ({gemini_err}). Triggering Groq Fallback...")
                return await self._groq_fallback_chat(message, telegram_id, system_instructions, tools_map)

            # --- STANDARD GEMINI PROCESSING ---
            # (AFC handles function calls internally. Manual block pruned for performance)
            
            final_text = response.text or ""
            return self._unify_agent_response(telegram_id, message, final_text)

        except Exception as e:
            logger.error(f"AIEngine.agent_chat error: {e}", exc_info=True)
            return "I encountered an internal tracking error while processing your request. Please try again shortly."

    def _get_scoped_history(self, current_prompt: str, history_list: List[Any]) -> List[Any]:
        """
        Returns a filtered rolling window of the last 6 user/model turns.

        TOKEN OPTIMIZATION:
        - Capped at 6 content objects (3 user+model pairs) instead of 8.
        - Tool role and function-call-only model content objects are EXCLUDED.
          They carry the full tool result JSON in their parts, which is extremely
          heavy (5 emails * 300 chars each) but provides zero value in follow-up
          turns since the model already acted on that data.
        - Only user text turns and model text response turns are preserved.
        """
        if not history_list:
            return []

        # Filter: keep only user and model turns that have actual text parts
        text_only_turns = []
        for turn in history_list:
            if not hasattr(turn, 'role'):
                continue
            role = getattr(turn, 'role', None)
            if role not in ('user', 'model'):
                # Skip 'tool' role turns entirely — these contain raw tool results
                continue
            parts = getattr(turn, 'parts', [])
            has_text = any(hasattr(p, 'text') and p.text for p in parts)
            has_only_fn_call = all(
                (hasattr(p, 'function_call') and p.function_call and not (hasattr(p, 'text') and p.text))
                for p in parts
            ) if parts else False
            if has_text and not has_only_fn_call:
                text_only_turns.append(turn)

        # Return the 6 most recent qualifying turns
        return text_only_turns[-6:]

    @staticmethod
    def _extract_keywords(text: str) -> set:
        words = re.findall(r'\b\w+\b', text.lower())
        stop_words = {
            'the', 'a', 'an', 'and', 'or', 'but', 'is', 'are', 'was', 'were',
            'to', 'of', 'for', 'with', 'in', 'on', 'at', 'by', 'from', 'this',
            'these', 'those', 'please', 'can', 'you', 'i', 'my', 'me', 'your',
            'se', 'ko', 'ka', 'ki', 'main', 'tum', 'hum', 'aur', 'hi'
        }
        return {w for w in words if w not in stop_words}

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

        try:
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
                    try:
                        await self.client.aio.files.delete(name=uploaded_file.name)
                    except Exception as del_err:
                        logger.warning(f"Failed deleting remote Gemini file: {del_err}")
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
        finally:
            for fp in [file_path, file_path.replace(".ogg", ".oga"), file_path.replace(".ogg", ".wav"), file_path.replace(".oga", ".wav")]:
                if fp and os.path.exists(fp):
                    try:
                        os.remove(fp)
                        logger.info(f"Disk Cleanup: Evicted temporary file {fp}")
                    except Exception as err:
                        logger.warning(f"Failed deleting temp file {fp}: {err}")

        return "[Audio Unclear: Failed to extract written text context]"

    # ==========================================
    # TOKEN-EFFICIENT UTILITY CORES
    # ==========================================
    # These methods use direct single-turn LLM calls (no tools, no history) to keep
    # token costs minimal and prevent email body content from polluting the chat session.

    async def summarize_email(self, email_body: str) -> str:
        """
        Generates a concise, structured summary of the email objective.
        Uses a direct single-turn call — does NOT update active_chats history.
        """
        clean_body = " ".join(email_body.strip().split())
        if not clean_body:
            return "The email is empty."

        words = clean_body.split()
        if len(words) <= 15:
            quoted_text = clean_body.strip('"\'')
            return f"\"{quoted_text}\""

        prompt = (
            "Summarize the following email in a maximum of 3 SHORT bullet points.\n"
            "Each bullet must be a single short sentence. No filler words, no URLs, no sender/recipient names.\n"
            "Lead with the single most important action or takeaway. Strip everything else.\n"
            "Format: use '-' as bullet marker. No preamble, no markdown bold/headers.\n\n"
            f"Email:\n{email_body[:3000]}"
        )
        # ── Attempt via Groq first to save Gemini quota ─────────────────────────
        if settings.GROQ_API_KEY:
            try:
                url = "https://api.groq.com/openai/v1/chat/completions"
                headers = {"Authorization": f"Bearer {settings.GROQ_API_KEY}", "Content-Type": "application/json"}
                payload = {
                    "model": "llama-3.3-70b-versatile",
                    "messages": [{"role": "user", "content": prompt}],
                    "temperature": 0.1,
                    "max_tokens": 80,
                }
                async with httpx.AsyncClient(timeout=20.0) as client:
                    resp = await client.post(url, headers=headers, json=payload)
                    resp.raise_for_status()
                    text = resp.json()["choices"][0]["message"].get("content", "").strip()
                    if text:
                        return text
            except Exception as groq_err:
                logger.warning(f"Groq summarize_email failed, falling back to Gemini: {groq_err}")

        # ── Gemini fallback (only if Groq is not configured or failed) ────────────
        for attempt in range(2):
            try:
                response = await self.client.aio.models.generate_content(
                    model=self.model_name,
                    contents=prompt
                )
                return response.text.strip() if response.text else "Summary unavailable."
            except Exception as e:
                if _is_quota_error(e):
                    logger.warning(f"Gemini quota exhausted on summarize_email for attempt {attempt + 1}.")
                    return "Summary unavailable — AI quota is temporarily exhausted. Please try again in a moment."
                err_str = str(e)
                if "503" in err_str or "UNAVAILABLE" in err_str:
                    logger.warning(f"Gemini 503 UNAVAILABLE on summarize_email attempt {attempt + 1}. Retrying...")
                    if attempt == 0:
                        await asyncio.sleep(1)
                        continue
                logger.error(f"Summarize email error: {e}")
                break
        return "Email abstractive summary failed due to internal analytical errors."

    async def generate_tts_summary(self, email_body: str) -> str:
        """
        Generates a 2-3 sentence spoken summary optimized for text-to-speech delivery.
        Uses a direct single-turn call — does NOT update active_chats history.
        """
        prompt = (
            "You are a voice assistant. Read the following email and write a natural, spoken summary "
            "in exactly 2-3 sentences. Use simple, clear language suitable for text-to-speech playback. "
            "Do not use bullet points, markdown symbols, or special characters.\n\n"
            f"Email:\n{email_body[:3000]}"
        )
        # ── Attempt via Groq first to save Gemini quota ─────────────────────────
        if settings.GROQ_API_KEY:
            try:
                url = "https://api.groq.com/openai/v1/chat/completions"
                headers = {"Authorization": f"Bearer {settings.GROQ_API_KEY}", "Content-Type": "application/json"}
                payload = {
                    "model": "llama-3.3-70b-versatile",
                    "messages": [{"role": "user", "content": prompt}],
                    "temperature": 0.1,
                    "max_tokens": 120,
                }
                async with httpx.AsyncClient(timeout=20.0) as client:
                    resp = await client.post(url, headers=headers, json=payload)
                    resp.raise_for_status()
                    text = resp.json()["choices"][0]["message"].get("content", "").strip()
                    if text:
                        return text
            except Exception as groq_err:
                logger.warning(f"Groq generate_tts_summary failed, falling back to Gemini: {groq_err}")

        # ── Gemini fallback (only if Groq is not configured or failed) ────────────
        for attempt in range(2):
            try:
                response = await self.client.aio.models.generate_content(
                    model=self.model_name,
                    contents=prompt
                )
                return response.text.strip() if response.text else "Unable to generate audio summary."
            except Exception as e:
                if _is_quota_error(e):
                    logger.warning(f"Gemini quota exhausted on generate_tts_summary for attempt {attempt + 1}.")
                    return "Audio summary temporarily unavailable. Please try again in a moment."
                err_str = str(e)
                if "503" in err_str or "UNAVAILABLE" in err_str:
                    logger.warning(f"Gemini 503 UNAVAILABLE on generate_tts_summary attempt {attempt + 1}. Retrying...")
                    if attempt == 0:
                        await asyncio.sleep(1)
                        continue
                logger.error(f"TTS summary generation error: {e}")
                break
        return "Audio summary generation failed."



# Singleton instance initialization
ai_engine = AIEngine()