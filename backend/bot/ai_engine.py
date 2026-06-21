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
8. Groq Failover Pipeline: Instantly falls back to Llama-3-70b if Gemini hits a rate limit!
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
        roman_urdu_markers = [
            'kya', 'hai', 'rha', 'rhi', 'krna', 'karo', 'mujhe', 'mujh',
            'tumhe', 'aap', 'yeh', 'woh', 'nahi', 'haan', 'bhai', 'yar',
            'bata', 'bhej', 'dekh', 'suna', 'sunao', 'bol', 'batao',
            'kaise', 'kaisa', 'kaisi', 'abhi', 'pehle', 'baad', 'mein',
            'ko', 'ka', 'ki', 'se', 'ho', 'hain', 'tha', 'thi',
            'ga', 'gi', 'ge', 'kar', 'kr', 'hn', 'hu', 'hoon',
            'zaroor', 'shukriya', 'theek', 'acha', 'achha',
            'bhejo', 'likho', 'padho', 'dikhao',
        ]
        words = text.lower().split()
        match_count = sum(1 for w in words if w in roman_urdu_markers)
        if match_count >= 2 or (len(words) <= 5 and match_count >= 1):
            return "Roman Urdu (Urdu written in Latin/English alphabet). Reply in Roman Urdu using Latin letters. Do NOT use Arabic/Nastaliq script."

        return "English. Reply in English."

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
    # GROQ FALLBACK PIPELINE
    # ==========================================

    async def _groq_fallback_chat(self, message: str, telegram_id: int, system_instructions: str, tools_map: dict) -> str:
        """
        Triggered automatically when Gemini hits API rate limits (429).
        Routes the existing context and tools directly to Llama-3-70b on Groq.
        """
        if not settings.GROQ_API_KEY:
            return "⚠️ Gemini LLM limits reached and Groq API Fallback is not configured. Please wait a few seconds."

        # Map Gemini History Schema to Groq (OpenAI) Chat Schema
        messages = [{"role": "system", "content": system_instructions}]
        
        for turn in self.active_chats.get(telegram_id, []):
            role = "user" if turn.role == "user" else "assistant"
            text_content = ""
            for part in getattr(turn, "parts", []):
                if hasattr(part, "text") and part.text:
                    text_content += part.text
            if text_content:
                messages.append({"role": role, "content": text_content})
                
        messages.append({"role": "user", "content": message})

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
            "model": "llama-3.3-70b-versatile",  # Updated from deprecated llama3-70b-8192
            "messages": messages,
            "tools": groq_tools,
            "tool_choice": "auto",
            "temperature": 0.2
        }

        try:
            async with httpx.AsyncClient(timeout=45.0) as client:
                response = await client.post(url, headers=headers, json=payload)
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
                            self.active_chats[telegram_id].append(types.Content(role="user", parts=[types.Part.from_text(text=message)]))
                            self.active_chats[telegram_id].append(types.Content(role="model", parts=[types.Part.from_text(text="Draft/schedule prepared and displayed to user.")]))
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
                        resp2.raise_for_status()
                        final_text = resp2.json()["choices"][0]["message"].get("content", "")
                        
                        self.active_chats[telegram_id].append(types.Content(role="user", parts=[types.Part.from_text(text=message)]))
                        self.active_chats[telegram_id].append(types.Content(role="model", parts=[types.Part.from_text(text=final_text)]))
                        return final_text
                        
                    except Exception as tool_err:
                        logger.error(f"Groq tool error: {tool_err}")
                        return f"Error executing tool during fallback: {tool_err}"
                else:
                    # Plain chat response
                    content = choice.get("content", "")
                    self.active_chats[telegram_id].append(types.Content(role="user", parts=[types.Part.from_text(text=message)]))
                    self.active_chats[telegram_id].append(types.Content(role="model", parts=[types.Part.from_text(text=content)]))
                    return content
                    
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

            tools_map = {
                "search_gmail_tool": self.search_gmail_tool,
                "prepare_email_draft_tool": self.prepare_email_draft_tool,
                "schedule_email_tool": self.schedule_email_tool,
                "save_contact_tool": self.save_contact_tool
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

            max_turns = settings.MAX_CONTEXT_MESSAGES * 2
            if len(self.active_chats[telegram_id]) > max_turns:
                trimmed = self.active_chats[telegram_id][-max_turns:]
                for i in range(len(trimmed)):
                    if getattr(trimmed[i], "role", "") == "user":
                        trimmed = trimmed[i:]
                        break
                self.active_chats[telegram_id] = trimmed

            user_part = types.Part.from_text(text=message)
            user_content = types.Content(role="user", parts=[user_part])
            contents = self.active_chats[telegram_id] + [user_content]

            logger.info(f"Triggering Gemini 2.5 Flash for user: {telegram_id}")
            
            # --- FAILOVER WRAPPER ---
            # NOTE: We use run_in_executor with a lambda closure instead of asyncio.to_thread
            # because asyncio.to_thread passes arguments directly to the thread pool, which
            # triggers pickling of self.client — and the Gemini SDK client contains internal
            # _thread.lock objects that cannot be pickled. A lambda closure captures the
            # client by reference without serialization, bypassing the pickle entirely.
            loop = asyncio.get_event_loop()
            try:
                response = await loop.run_in_executor(
                    None,
                    lambda: self.client.models.generate_content(
                        model=self.model_name,
                        contents=contents,
                        config=config,
                    )
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
                    final_response = await loop.run_in_executor(
                        None,
                        lambda: self.client.models.generate_content(
                            model=self.model_name,
                            contents=_call_contents,
                            config=config,
                        )
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