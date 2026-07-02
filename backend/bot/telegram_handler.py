"""
Telegram Bot Handler — Smart Email Assistant
============================================
Production-ready Presentation Master Core.
Features Implemented:
- Atomic Dynamic Navigation History Stack (Self-correcting Back Buttons).
- Granular Text Beauty Framework (Stops Markdown/HTML string parsing crashes).
- Dynamic Token Interceptor & Login Cleanup (Handles 401/403 gracefully).
- Immediate Dispatch Model (Removed legacy 7-second undo delays).
- Centralized Cleanups & Cron Resiliency Embedded.
- Tag-Based Voice Routing: Intercepts [VOICE] tags for seamless TTS execution.
"""

import logging
import os
import time
import asyncio
import tempfile
import uuid
import re
import dateparser
import pytz
from timezonefinder import TimezoneFinder
from datetime import datetime, timedelta
import json
from datetime import datetime, timezone
from typing import Dict, List, Optional

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.constants import ChatAction
from telegram.ext import (
    ApplicationBuilder, CommandHandler, MessageHandler,
    CallbackQueryHandler, filters, ContextTypes, Application
)

from config import settings
from db.models import db_manager
from db.memory import memory_manager
from bot.ai_engine import ai_engine
from bot.gmail_client import GmailClient
from bot.voice_handler import voice_handler
from db.contacts import contact_manager

logging.basicConfig(level=logging.INFO)
# Hide spammy API logs
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("apscheduler").setLevel(logging.WARNING)
logger = logging.getLogger(__name__)


# ── Callback Helpers & Sanitizers ──────────────────────────────────────────────

def _cb(action: str, *args) -> str:
    """Safely constructs callback data strings under the 64-byte limit."""
    data = ":".join([action] + [str(a) for a in args])
    if len(data) > 64:
        parts = data.split(":")
        if len(parts) >= 2:
            parts[1] = parts[1][:16]
            data = ":".join(parts)
    return data[:64]

def _parse_cb(data: str) -> tuple:
    """Parses callback data back into action and arguments."""
    parts = data.split(":")
    return parts[0], parts[1:]


def _strip_email_footer(body: str) -> str:
    """
    Strips common email footer boilerplate — disclaimers, signatures, forwarding
    headers — before displaying the body in Telegram. This prevents walls of legal
    text from polluting the chat interface.
    """
    # Patterns that mark the start of footers / signatures
    footer_markers = [
        r'^\s*[-_]{2,}\s*$',                          # -- or __ separator lines
        r'^\s*\*?Disclaimer[:\s]',                    # Disclaimer: ...
        r'^\s*This (e-?mail|message) (is |contains )',# This email is confidential
        r'^\s*CONFIDENTIALITY NOTICE',
        r'^\s*LEGAL NOTICE',
        r'^\s*NOTICE:.*confidential',
        r'^\s*The information (in|contained)',
        r'^\s*This communication',
        r'^\s*\*Note:',
        r'^\s*CAUTION:',
        r'^\s*Virus-free\.',
        r'^\s*Sent from (my|iPhone|Samsung|Android)',
        r'^\s*Get Outlook for',
        r'^\s*---------- Forwarded message',
        r'^\s*-{3,} Original Message',
        r'^\s*From:.*Sent:.*To:.*Subject:',            # Outlook reply header block
    ]
    lines = body.splitlines()
    cutoff = len(lines)
    for i, line in enumerate(lines):
        for pattern in footer_markers:
            if re.match(pattern, line, re.IGNORECASE):
                cutoff = i
                break
        if cutoff < len(lines):
            break
    cleaned = "\n".join(lines[:cutoff]).strip()
    return cleaned if cleaned else body


def _safe_md(text: str) -> str:
    """
    Granular Text Beauty Framework:
    Escapes Markdown symbols ONLY for variable data to prevent render crashes,
    without destroying the overall layout aesthetics or adding ugly backslashes.
    """
    if not text: 
        return ""
    escape_chars = r"_*`["
    return "".join(f"\\{c}" if c in escape_chars else c for c in text)

def _esc_html(text: str) -> str:
    """Safely escape HTML entities for Telegram HTML parse_mode."""
    if not text: 
        return ""
    return str(text).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _parse_sender_header(raw_sender: str) -> tuple:
    """Parses a sender header (e.g. 'Name <email>') into (name, email) tuple."""
    if not raw_sender:
        return "Unknown", ""
    
    # Check for name <email> format
    match = re.search(r'^(.*?)\s*<([^>]+)>', raw_sender)
    if match:
        name = match.group(1).strip().strip('"').strip("'").strip()
        email = match.group(2).strip()
        if not name:
            name = email.split("@")[0] if "@" in email else email
        return name, email
    
    raw_sender = raw_sender.strip()
    if "@" in raw_sender:
        name = raw_sender.split("@")[0]
        return name, raw_sender
        
    return raw_sender, ""


def _has_draft_content(state: dict) -> bool:
    """Returns True if the draft state contains user-entered data."""
    if not state:
        return False
    return bool(state.get("to") or state.get("subj") or state.get("body") or state.get("attachments"))


# ── Keyboard Builders ──────────────────────────────────────────────────────────

def kb_main_menu(has_draft: bool = False) -> InlineKeyboardMarkup:
    """Builds the main dashboard keyboard with symmetrical 2x2 grid."""
    rows = []
    if has_draft:
        rows.append([
            InlineKeyboardButton("📝 Resume Draft", callback_data="resume_draft")
        ])
        rows.append([
            InlineKeyboardButton("🗑️ Discard", callback_data="cancel")
        ])
    rows.extend([
        [InlineKeyboardButton("📥 Inbox",         callback_data=_cb("inbox", 0)),
         InlineKeyboardButton("📅 Scheduled",     callback_data="list_sch")],
        [InlineKeyboardButton("✍️ Compose",        callback_data="compose")],
        [InlineKeyboardButton("🔍 Search",         callback_data="search_prompt")],
        [InlineKeyboardButton("⚙️ Settings",       callback_data="settings")],
    ])
    return InlineKeyboardMarkup(rows)

def kb_back_step() -> list:
    """Returns two side-by-side nav buttons: Go Back (history) + Main Menu (shortcut)."""
    return [
        InlineKeyboardButton("🔙 Back", callback_data="history_back"),
        InlineKeyboardButton("🏠 Menu", callback_data="menu_main"),
    ]


def kb_nav_for_ctx(ctx: str) -> list:
    """
    Returns the correct navigation row depending on origin context.
    - 'notif': email was opened from a push notification card — Back must go to Dashboard.
    - 'inbox'/'search': email was opened from a list view — Back replays list.
    """
    if ctx == "notif":
        return [InlineKeyboardButton("🏠 Dashboard", callback_data="menu_main")]
    return kb_back_step()

def kb_cancel() -> InlineKeyboardMarkup:
    """Generic cancel keyboard."""
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("❌ Cancel", callback_data="cancel")]
    ])

def kb_email_list(msgs: list, offset: int, is_search: bool, has_next: bool, limit: int = 2) -> InlineKeyboardMarkup:
    """Builds pagination keyboard for email lists."""
    rows = []
    ctx = "search" if is_search else "inbox"
    
    for i, m in enumerate(msgs):
        rows.append([InlineKeyboardButton(
            f"📖 Email {offset + i + 1}",
            callback_data=_cb("read", m["id"][:16], ctx, offset)
        )])
        
    nav = []
    if offset > 0:
        cb = _cb("srpage", max(0, offset - limit)) if is_search else _cb("inbox", max(0, offset - limit))
        nav.append(InlineKeyboardButton("⬅️ Prev", callback_data=cb))
    if has_next:
        cb = _cb("srpage", offset + limit) if is_search else _cb("inbox", offset + limit)
        nav.append(InlineKeyboardButton("Next ➡️", callback_data=cb))
        
    if nav:
        rows.append(nav)
        
    rows.append(kb_back_step())
    return InlineKeyboardMarkup(rows)

def kb_email_view(msg_id: str, ctx: str, offset: int, has_att: bool) -> InlineKeyboardMarkup:
    """Builds inline actions for full email viewing. Nav row is ctx-aware."""
    mid = msg_id[:16]
    rows = [
        [InlineKeyboardButton("📖 Read Full", callback_data=_cb("read_html", mid, ctx, offset)),
         InlineKeyboardButton("📝 Summarize", callback_data=_cb("sum",   mid, ctx, offset))],
        [InlineKeyboardButton("✉️ Reply", callback_data=_cb("reply", mid, ctx, offset)),
         InlineKeyboardButton("🗑️ Trash", callback_data=_cb("del",   mid, ctx, offset))],
    ]
    if has_att:
        rows.append([InlineKeyboardButton("📥 Attachments", callback_data=_cb("att", mid, ctx, offset))])
        
    rows.append(kb_nav_for_ctx(ctx))
    return InlineKeyboardMarkup(rows)

def kb_summary(msg_id: str, ctx: str, offset: int, has_att: bool) -> InlineKeyboardMarkup:
    """Summary view — Core actions only. Nav row is ctx-aware."""
    mid = msg_id[:16]
    rows = [
        [InlineKeyboardButton("📖 Read Full", callback_data=_cb("read", mid, ctx, offset)),
         InlineKeyboardButton("🔊 Listen", callback_data=_cb("tts",  mid, ctx, offset))],
        [InlineKeyboardButton("↩️ Reply", callback_data=_cb("reply", mid, ctx, offset))]
    ]
    if has_att:
        rows.insert(1, [InlineKeyboardButton("📥 Attachments", callback_data=_cb("att", mid, ctx, offset))])
        
    rows.append(kb_nav_for_ctx(ctx))
    return InlineKeyboardMarkup(rows)

def kb_notification(msg_id: str, has_att: bool) -> InlineKeyboardMarkup:
    """Push notification card — uses 'notif' context so Back always returns to Dashboard."""
    mid = msg_id[:16]
    # Use 'notif' as the ctx tag so history_back recognises notification-origin cards
    # and falls back to menu_main instead of attempting to re-render a nonexistent list.
    rows = [
        [
            InlineKeyboardButton("📖 Read Email",   callback_data=_cb("read", mid, "notif", 0)),
            InlineKeyboardButton("🤖 AI Summary",   callback_data=_cb("sum",  mid, "notif", 0))
        ],
        [
            InlineKeyboardButton("🔊 Listen",        callback_data=_cb("tts",  mid, "notif", 0))
        ]
    ]
    if has_att:
        rows[1].append(InlineKeyboardButton("📥 Attachments", callback_data=_cb("att", mid, "notif", 0)))
    rows.append([InlineKeyboardButton("🏠 Dashboard", callback_data="menu_main")])
    return InlineKeyboardMarkup(rows)

def kb_draft(has_files: bool = False) -> InlineKeyboardMarkup:
    """Enhanced Draft UI with Dynamic Edit capabilities."""
    rows = [
        [InlineKeyboardButton("🚀 Send",       callback_data="send_draft"),
         InlineKeyboardButton("📅 Schedule",   callback_data="schedule_draft_manual")],
        [InlineKeyboardButton("✏️ Edit",       callback_data="edit_draft_hub"),
         InlineKeyboardButton("📎 Attach",     callback_data="attach_hint")],
        [InlineKeyboardButton("❌ Cancel",      callback_data="cancel")]
    ]
    if has_files:
        rows.insert(2, [InlineKeyboardButton("🗑️ Clear Files", callback_data="clear_att")])
        
    return InlineKeyboardMarkup(rows)

def kb_settings(ai_on: bool, voice: str, auto_on: bool, pag_limit: int = 2, draft_style: str = "Detailed") -> InlineKeyboardMarkup:
    """User preferences keyboard."""
    v_map = {"text": "📝 Text Only", "voice": "🎙️ Voice Only", "smart": "🧠 Smart Routing"}
    pag_label = "📄 View: Compact (2/pg)" if pag_limit == 2 else "📄 View: Standard (5/pg)"
    draft_label = "✍️ Draft: Detailed" if draft_style == "Detailed" else "✍️ Draft: Concise"
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(f"{'✅' if ai_on   else '❌'} AI Mode",          callback_data="toggle_ai")],
        [InlineKeyboardButton(v_map.get(voice, "📝 Text Only"),                callback_data="cycle_voice")],
        [InlineKeyboardButton(f"{'✅' if auto_on else '❌'} Auto Check", callback_data="toggle_auto")],
        [InlineKeyboardButton(pag_label,                                       callback_data="cycle_pagination")],
        [InlineKeyboardButton(draft_label,                                     callback_data="cycle_draft")],
        [InlineKeyboardButton("🌍 Set Timezone",                               callback_data="set_timezone")],
        [InlineKeyboardButton("🚪 Logout",                             callback_data="logout")],
        kb_back_step(),
    ])

def _draft_text(state: dict) -> str:
    """Formats the current staging draft template."""
    files   = state.get("attachments", [])
    att_ln  = f"\n📎 *{len(files)} attachment(s) staged*" if files else ""
    return (
        f"📄 *Draft Preview*\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"👤 *To:* `{_safe_md(state.get('to', '[Specify Recipient Email]'))}`\n"
        f"📝 *Subject:* `{_safe_md(state.get('subj', '—'))}`\n"
        f"✉️ *Body:*\n_{_safe_md(state.get('body', '—'))}_\n"
        f"{att_ln}\n\n"
        f"Review your draft. Tap *Send Now* or *Edit Fields* to modify.\n\n"
        f"💡 Tip: If you want to attach a file to this email, simply upload/send the document directly in this chat. The bot will automatically stage it in this draft."
    )


# ── Bot Manager ────────────────────────────────────────────────────────────────

class TelegramBotManager:
    def __init__(self):
        self.application: Application | None = None
        self.ai_engine       = ai_engine
        self.db              = db_manager
        self.memory          = memory_manager
        self.gmail           = GmailClient()
        self.voice           = voice_handler
        self.contacts        = contact_manager

        self.compose_states:    dict = {}   # uid -> {step, to, subj, body, attachments}
        self.search_states:     dict = {}   # uid -> 'AWAIT_QUERY'
        self.settings_states:   dict = {}   # uid -> 'AWAIT_TIMEZONE'
        self.current_queries:   dict = {}   # uid -> last search query string
        self._mid_cache:        dict = {}   # short_id[:16] -> full Gmail message ID
        self.notified_emails:    set = set()
        self.active_voice_tasks: set = set()
        self.ram_semaphore = asyncio.BoundedSemaphore(value=3)
        
        # Stores the last user text/voice query per user to power the Retry button UX.
        # When any AI call crashes, the user gets a [🔄 Retry] button that re-submits this.
        self.last_user_queries: Dict[int, Dict[str, str]] = {}
        
        # Cold start safety parameter
        self.startup_time = datetime.now(timezone.utc).timestamp()
        
        # TRUE NAVIGATION STACK: Captures user movement across dynamic states
        self.navigation_history: Dict[int, List[str]] = {}

    # ── Internals ──────────────────────────────────────────────────────────────

    def _full_mid(self, short: str) -> str:
        """Retrieves the full message ID from the cache using its short 16-char prefix."""
        return self._mid_cache.get(short, short)

    def _store_mid(self, full_id: str):
        """Stores the full message ID in cache, keyed by its 16-char prefix."""
        self._mid_cache[full_id[:16]] = full_id

    def _bg(self, coro):
        """Dispatches a coroutine to run in the background."""
        asyncio.create_task(coro)

    async def _prefs(self, uid: int) -> dict:
        """Fetch preferences with fallback to avoid empty cache lockups."""
        try:
            prefs = await self.db.get_user_preferences(uid)
            if prefs:
                # Ensure all settings fields have safe defaults
                if prefs.get("pagination_limit") is None:
                    prefs["pagination_limit"] = 2
                if prefs.get("voice_preference") is None:
                    prefs["voice_preference"] = "text"
                if prefs.get("auto_check_enabled") is None:
                    prefs["auto_check_enabled"] = True
                return prefs
        except Exception as e:
            logger.debug(f"Preference fetch fallback error: {e}")
            pass
        return {"ai_mode_enabled": True, "voice_preference": "text", "auto_check_enabled": True, "pagination_limit": 2, "timezone": "UTC"}

    async def _db_push_nav_stack(self, uid: int, state_str: str) -> None:
        """Pushes a UI state (like 'menu_main' or 'inbox:0') to the user's DB nav stack."""
        try:
            user = await self.db.get_user(uid)
            stack = user.get("ui_nav_stack") if user and isinstance(user.get("ui_nav_stack"), list) else []
            if stack and stack[-1] == state_str: return # Avoid duplicate adjacent states
            stack.append(state_str)
            # Keep stack size manageable
            if len(stack) > 15: stack = stack[-15:]
            await self.db.db.run(lambda: self.db.db.client.table("users").update({"ui_nav_stack": stack}).eq("telegram_id", uid).execute())
        except Exception as e:
            logger.error(f"Error pushing nav stack: {e}")

    async def _db_pop_nav_stack(self, uid: int) -> str:
        """Pops and returns the previous UI state. Defaults to 'menu_main' if empty."""
        try:
            user = await self.db.get_user(uid)
            stack = user.get("ui_nav_stack") if user and isinstance(user.get("ui_nav_stack"), list) else []
            if len(stack) > 1:
                stack.pop() # Remove current state
                prev_state = stack[-1] # Peak at previous
                await self.db.db.run(lambda: self.db.db.client.table("users").update({"ui_nav_stack": stack}).eq("telegram_id", uid).execute())
                return prev_state
            return "menu_main"
        except Exception as e:
            logger.error(f"Error popping nav stack: {e}")
            return "menu_main"

    async def _send(self, update: Update, text: str,
                    markup: InlineKeyboardMarkup | None = None,
                    parse_mode: str = "Markdown"):
        """Sends a completely new message or edits existing based on update context."""
        try:
            if update.callback_query:
                await update.callback_query.edit_message_text( 
                    text, parse_mode=parse_mode, reply_markup=markup,
                    disable_web_page_preview=True)
            elif update.message:
                await update.message.reply_text(
                    text, parse_mode=parse_mode, reply_markup=markup,
                    disable_web_page_preview=True)
        except Exception as e:
            if "Message is not modified" in str(e):
                pass
            else:
                logger.debug(f"_send error execution: {e}")

    async def _edit(self, obj, text: str,
                    markup: InlineKeyboardMarkup | None = None,
                    parse_mode: str = "Markdown"):
        """Edits an explicit message object or callback query."""
        try:
            if hasattr(obj, "edit_message_text"):
                await obj.edit_message_text(text, parse_mode=parse_mode, reply_markup=markup, disable_web_page_preview=True)
            elif hasattr(obj, "edit_text"):
                await obj.edit_text(text, parse_mode=parse_mode, reply_markup=markup, disable_web_page_preview=True)
            else:
                msg = getattr(obj, "message", obj)
                if hasattr(msg, "edit_text"):
                    await msg.edit_text(text, parse_mode=parse_mode, reply_markup=markup, disable_web_page_preview=True)
                else:
                    await obj.reply_text(text, parse_mode=parse_mode, reply_markup=markup, disable_web_page_preview=True)
        except Exception as e:
            if "Message is not modified" in str(e):
                pass
            else:
                logger.debug(f"_edit error execution: {e}")

    # ── True Dynamic Navigation Stack ──────────────────────────────────────────

    def _push_history(self, uid: int, state: str):
        """Pushes current screen interaction payload mapping securely onto the stack."""
        if uid not in self.navigation_history:
            self.navigation_history[uid] = []
        if not self.navigation_history[uid] or self.navigation_history[uid][-1] != state:
            self.navigation_history[uid].append(state)

    def _pop_history(self, uid: int) -> Optional[str]:
        """Pops the current screen and returns the previous screen state.
        
        Bug fix: After popping, we push the target state back so it is tracked
        as the new active screen. Without this, a second 'Go Back' tap finds an
        empty stack and returns the user to Main Menu instead of the next screen.
        """
        if uid in self.navigation_history and len(self.navigation_history[uid]) > 1:
            self.navigation_history[uid].pop()  # Discard current (the screen we are leaving)
            target = self.navigation_history[uid].pop()  # Retrieve target screen
            # Re-push the target so it becomes the tracked active screen
            self.navigation_history[uid].append(target)
            return target
        return None

    def _clear_history(self, uid: int):
        self.navigation_history[uid] = []

    # ── Auth Redirection Lifecycle & Sentinel ──────────────────────────────────

    async def _prompt_reauth(self, msg_obj, uid: int):
        state = await self.db.create_auth_session(uid)
        url   = f"{settings.APP_URL}/api/auth/telegram_login?state={state}&telegram_id={uid}"
        text  = "⚠️ Your Google session has expired or been revoked. Please use reconnect through button. "
        markup = InlineKeyboardMarkup([[InlineKeyboardButton("🔗 Reconnect", url=url)]])
        await self._edit(msg_obj, text, markup)

    async def _send_reauth_direct(self, context, uid: int):
        await self.db.update_user_preferences(uid, {"auto_check_enabled": False})
        state = await self.db.create_auth_session(uid)
        url   = f"{settings.APP_URL}/api/auth/telegram_login?state={state}&telegram_id={uid}"
        text  = "⚠️ Your Google session has expired or been revoked. Please use reconnect through button. "
        markup = InlineKeyboardMarkup([[InlineKeyboardButton("🔗 Reconnect", url=url)]])
        try:
            await context.bot.send_message(chat_id=uid, text=text, parse_mode="Markdown", reply_markup=markup)
        except Exception:
            pass

    async def notify_login_success(self, uid: int):
        """Triggered on successful Google Workspace OAuth authentication."""
        # 1. Clear stale conversational and historical context limits immediately
        self.ai_engine.clear_chat_session(uid)
        self._clear_history(uid)
        
        # 2. Retrieve verified address details
        user = await self.db.get_user(uid)
        email_display = user.get("email") if user else "user@gmail.com"
        
        # 3. Clean routing dispatch
        text = f"✅ *Successfully Logged In!*\n\nAuthenticated successfully as `{_safe_md(email_display)}`.\nSelect an action below to manage your inbox:"
        try:
            await self.application.bot.send_message(
                chat_id=uid,
                text=text,
                parse_mode="Markdown",
                reply_markup=kb_main_menu()
            )
        except Exception as e:
            logger.error(f"Failed delivering authentications telemetry notifier: {e}")

    # ── Access Guard ──────────────────────────────────────────────────────────

    async def _check_access(self, uid: int, fname: str, uname: str) -> dict:
        if await self.db.is_blocked("telegram", str(uid)):
            return {"status": "blocked"}
            
        user = await self.db.get_user(uid)
        
        if not user:
            await self.db.create_user(uid, email=None, first_name=fname, username=uname)
            return {"status": "pending"}
            
        if not user.get("is_verified"):
            return {"status": "pending"}
            
        if not user.get("auth_token"):
            return {"status": "unauthenticated"}
            
        return {"status": "ok", "user": user}

    async def _gate(self, update: Update, uid: int, status: str) -> bool:
        if status == "blocked":
            await self._send(update, "🚫 *Access Revoked*\nYour account has been restricted by the administrator.")
            return True
            
        if status == "pending":
            await self._send(update,
                "⏳ *Pending Approval*\nYour account is awaiting admin verification.\n"
                "You will be notified once approved.")
            return True
            
        if status == "unauthenticated":
            state = await self.db.create_auth_session(uid)
            url   = (f"{settings.APP_URL}/api/auth/telegram_login"
                     f"?state={state}&telegram_id={uid}")
            await self._send(update,
                "⚠️ *Gmail Not Connected*\nLink your Google account to start:",
                InlineKeyboardMarkup([[InlineKeyboardButton("🔗 Connect", url=url)]]))
            return True
            
        return False

    # ── Setup ──────────────────────────────────────────────────────────────────

    async def error_handler(self, update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
        """
        Global error handler — logs all exceptions and notifies users ONLY for genuine
        application-level errors. Benign Telegram API errors (MessageNotModified,
        QueryIdInvalid, etc.) are logged quietly without spamming users.
        """
        err = context.error
        err_str = str(err)

        # These are routine/expected Telegram API exceptions — do NOT alert the user
        benign_patterns = [
            "Message is not modified",
            "Query is too old",
            "MESSAGE_ID_INVALID",
            "Bad Request: message is not modified",
            "Conflict: terminated by other getUpdates",
            "NetworkError",
            "TimedOut",
        ]
        is_benign = any(p.lower() in err_str.lower() for p in benign_patterns)

        if is_benign:
            logger.debug(f"[Benign Telegram error suppressed]: {err}")
            return

        logger.error(f"Unhandled exception in update handler: {err}", exc_info=err)

        if isinstance(update, Update) and update.effective_chat:
            try:
                if update.callback_query:
                    try: await update.callback_query.answer()
                    except Exception: pass
                await context.bot.send_message(
                    chat_id=update.effective_chat.id,
                    text="⚠️ *An unexpected error occurred.* Please try again or restart with /start.",
                    parse_mode="Markdown"
                )
            except Exception as send_err:
                logger.error(f"Failed to send error notification: {send_err}")

    async def setup_bot(self):
        """Initializes application core routines and binds webhook mappings."""
        self.application = ApplicationBuilder().token(settings.BOT_TOKEN).build()
        self.application.add_error_handler(self.error_handler)
        self.application.add_handler(CommandHandler("start", self.cmd_start))
        self.application.add_handler(CommandHandler("clear", self.cmd_clear))
        self.application.add_handler(CommandHandler("menu",  self.cmd_menu))
        self.application.add_handler(CallbackQueryHandler(self.handle_button))
        self.application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, self.handle_text))
        self.application.add_handler(MessageHandler(filters.VOICE, self.handle_voice))
        self.application.add_handler(MessageHandler(filters.Document.ALL | filters.PHOTO | filters.AUDIO | filters.VIDEO, self.handle_attachment))
        self.application.add_handler(MessageHandler(filters.LOCATION, self.handle_location))
            
        await self.application.initialize()
        
        if self.application.job_queue:
            self.application.job_queue.run_repeating(self.job_emails,    interval=60,  first=15)
            self.application.job_queue.run_repeating(self.job_scheduled, interval=60,  first=30)
            self.application.job_queue.run_repeating(self.job_ping,      interval=840, first=60)
            
        base_url = settings.WEBHOOK_URL or settings.APP_URL
        webhook_url = ""
        if base_url:
            base_url = base_url.rstrip('/')
            if not base_url.endswith("/api/webhook/telegram") and not base_url.endswith("/webhook/telegram"):
                webhook_url = f"{base_url}/api/webhook/telegram"
            elif base_url.endswith("/webhook/telegram"):
                webhook_url = base_url.replace("/webhook/telegram", "/api/webhook/telegram")
            else:
                webhook_url = base_url
            
        if webhook_url and not webhook_url.startswith("http://localhost"):
            import asyncio
            retries = 3
            backoff = 2
            for attempt in range(1, retries + 1):
                try:
                    await self.application.bot.set_webhook(url=webhook_url)
                    logger.info(f"✅ Bot webhook bound successfully to: {webhook_url}")
                    break
                except Exception as e:
                    if attempt == retries:
                        logger.error(f"❌ Failed to bind webhook after {retries} attempts: {e}")
                    else:
                        logger.warning(f"⚠️ Webhook bind failed (attempt {attempt}/{retries}), retrying in {backoff}s...")
                        await asyncio.sleep(backoff)
                        backoff *= 2
        else:
            logger.info("⚠️ Local development cluster context detected.")
            
        await self.application.start()

    async def process_webhook(self, data: dict):
        if self.application:
            update = Update.de_json(data, self.application.bot)
            await self.application.process_update(update)

    # ── Command & UI Handlers ──────────────────────────────────────────────────

    async def cmd_start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        u   = update.effective_user


        acc = await self._check_access(u.id, u.first_name or "", u.username or "")
        if await self._gate(update, u.id, acc["status"]):
            return
            
        self._clear_history(u.id)
        email_display = acc["user"].get("email") or "User"
        
        has_draft = u.id in self.compose_states
        if has_draft:
            state = self.compose_states[u.id]
            if "step" in state and state["step"] != "PAUSED":
                state["paused_step"] = state["step"]
                state["step"] = "PAUSED"
                
        await self._send(update,
            f"✅ *Authenticated as {email_display}*\n\n"
            "🎛️ *Smart Email Assistant Dashboard*\n"
            "Select an action below to manage your inbox:",
            kb_main_menu(has_draft))

    async def cmd_clear(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        u = update.effective_user
        self.ai.clear_chat_session(u.id)
        self._clear_history(u.id)
        _module_pending_drafts.pop(u.id, None)
        _module_pending_searches.pop(u.id, None)
        await self._send(update, "🧹 Session history and memory have been fully cleared.")

    async def cmd_menu(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        u   = update.effective_user


        acc = await self._check_access(u.id, u.first_name or "", u.username or "")
        if await self._gate(update, u.id, acc["status"]):
            return
            
        self._clear_history(u.id)
        
        has_draft = u.id in self.compose_states
        if has_draft:
            state = self.compose_states[u.id]
            if "step" in state and state["step"] != "PAUSED":
                state["paused_step"] = state["step"]
                state["step"] = "PAUSED"
                
        await self._send(update, "🎛️ *Main Dashboard*\n\nSelect an action:", kb_main_menu(has_draft))

    # ── Email list ─────────────────────────────────────────────────────────────

    async def _show_list(self, msg_obj, uid: int, offset: int, is_search: bool):
        query = self.current_queries.get(uid, "is:unread") if is_search else "label:INBOX"
        prefs = await self._prefs(uid)
        limit = prefs.get("pagination_limit", 2)
        try:
            messages = await self.gmail.get_emails(uid, query=query, max_results=offset + limit + 1)
            if messages == "TOKEN_EXPIRED_REAUTH_REQUIRED":
                return await self._prompt_reauth(msg_obj, uid)
        except Exception:
            messages = []

        if not messages and offset == 0:
            lbl = f"📭 No results for: `{_safe_md(query)}`" if is_search else "📭 Your inbox is empty."
            await self._edit(msg_obj, lbl, InlineKeyboardMarkup([kb_back_step()]))
            return

        display  = messages[offset:offset + limit]
        has_next = len(messages) > offset + limit
        header   = f"🔍 *Results:* `{_safe_md(query)}`\n\n" if is_search else "📥 *Your Inbox*\n\n"
        lines    = [header]

        for i, m in enumerate(display):
            self._store_mid(m["id"])
            meta = await self.gmail.get_email_metadata(uid, m["id"])
            if meta == "TOKEN_EXPIRED_REAUTH_REQUIRED":
                return await self._prompt_reauth(msg_obj, uid)
            if not meta or "error" in meta:
                continue
                
            raw_sender = meta.get("sender", "Unknown")
            name, email = _parse_sender_header(raw_sender)
            if email:
                sender_formatted = f"👤 *{_safe_md(name)}* `({_safe_md(email)})`"
            else:
                sender_formatted = f"👤 *{_safe_md(name)}*"
            subject = _safe_md(meta.get("subject", "No Subject"))
            lines.append(f"*{offset + i + 1}.* {sender_formatted}\n   📝 *Subject:* _{subject}_\n")

        await self._edit(msg_obj, "\n".join(lines),
                         kb_email_list(display, offset, is_search, has_next, limit))

    # ── Full email render ──────────────────────────────────────────────────────

    async def _show_email(self, msg_or_query, mid_short: str, ctx: str, offset: int, uid: int):
        """Renders the full email detail card. Accepts both Message objects and CallbackQuery objects."""
        # Unified loading indicator — works with both object types
        try:
            await self._edit(msg_or_query, "⏳ Loading email...", parse_mode="HTML")
        except Exception:
            pass

        full_mid = self._full_mid(mid_short)
        
        details = await self.gmail.get_email_details(uid, full_mid)
        if details == "TOKEN_EXPIRED_REAUTH_REQUIRED":
            msg_target = getattr(msg_or_query, 'message', msg_or_query)
            return await self._prompt_reauth(msg_target, uid)
            
        meta = await self.gmail.get_email_metadata(uid, full_mid)
        if meta == "TOKEN_EXPIRED_REAUTH_REQUIRED":
            msg_target = getattr(msg_or_query, 'message', msg_or_query)
            return await self._prompt_reauth(msg_target, uid)

        if not details or not meta or (isinstance(meta, dict) and "error" in meta):
            await self._edit(msg_or_query, "❌ *Email not found.* It may have been deleted.", markup=InlineKeyboardMarkup([kb_back_step()]))
            return
            
        self._store_mid(meta.get("id", full_mid))

        body         = details.get("body", "") if details else ""
        # Strip email footers (disclaimers, signatures) before display
        body         = _strip_email_footer(body)
        safe_body    = _esc_html(body[:3500] + ("\n\n<i>[… Truncated — tap Read Full Email for complete text]</i>" if len(body) > 3500 else ""))
        raw_sender   = meta.get("sender", "Unknown")
        name, email  = _parse_sender_header(raw_sender)
        safe_name    = _esc_html(name)
        safe_email   = _esc_html(email)
        safe_subject = _esc_html(meta.get("subject", "No Subject"))

        safe_body = re.sub(r'(https?://[^\s<>"]+)',
                           r'<a href="\1">🔗 Link</a>', safe_body)

        att_list = meta.get("attachments", [])
        att_line = f"\n📎 <b>{len(att_list)} Attachment(s)</b>" if att_list else ""

        from_line = f"📧 <b>From:</b> 👤 <b>{safe_name}</b> <code>({safe_email})</code>" if email else f"📧 <b>From:</b> 👤 <b>{safe_name}</b>"

        text = (f"{from_line}\n"
                f"📝 <b>Subject:</b> {safe_subject}{att_line}\n"
                f"{'━' * 20}\n\n{safe_body}")

        # Use the appropriate edit method based on object type
        try:
            await self._edit(msg_or_query, text, markup=kb_email_view(full_mid, ctx, offset, bool(att_list)), parse_mode="HTML")
        except Exception as edit_err:
            logger.warning(f"_show_email edit failed: {edit_err}")
                                        
        self._bg(self._save_contact(uid, meta.get("sender", "")))

    async def _save_contact(self, uid: int, raw_sender: str):
        try:
            m     = re.search(r'<(.+?)>', raw_sender)
            email = m.group(1) if m else raw_sender.strip()
            if "@" not in email:
                return
                
            name  = email.split("@")[0]
            await self.db.db.run(lambda: self.db.db.client.table("contacts").upsert(
                {"telegram_id": uid, "contact_alias": name,
                 "email_address": email, "contact_name": name},
                on_conflict="telegram_id,email_address").execute())
        except Exception:
            pass

    # ── Text handler ───────────────────────────────────────────────────────────

    async def handle_text(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        u   = update.effective_user


        try:
            acc = await self._check_access(u.id, u.first_name or "", u.username or "")
            
            uid  = u.id
            text = update.message.text

            # ── Active Hotfix Token Interceptor ──
            text_lower = text.lower()
            if any(k in text_lower for k in ["login", "re-authenticate", "reauthenticate", "expired token", "reconnect", "auth link", "authentication"]):
                await self._prompt_reauth(update.message, uid)
                return

            # Fast-track bypass for menu commands
            if text_lower.strip() in ["/menu", "/start", "menu", "dashboard"]:
                await self.cmd_menu(update, context)
                return

            if await self._gate(update, u.id, acc["status"]):
                return

            if uid in self.compose_states and self.compose_states[uid].get("step") != "PAUSED":
                handled = await self._compose_step(update, uid, text)
                if handled is not False:
                    return

            
            if uid in self.compose_states and self.compose_states[uid].get("step") == "AWAIT_SCHEDULE_TIME":
                prefs = await self._prefs(uid)
                user_tz_str = prefs.get("timezone", "UTC")
                try:
                    user_tz = pytz.timezone(user_tz_str)
                except Exception:
                    user_tz = pytz.utc
                
                parsed = dateparser.parse(text, settings={'PREFER_DATES_FROM': 'future', 'TIMEZONE': user_tz_str, 'RETURN_AS_TIMEZONE_AWARE': True})
                if not parsed:
                    await update.message.reply_text("I couldn't understand that time format. Please try again (e.g., 'tomorrow at 3pm').")
                    return
                
                # Convert to UTC for database storage
                parsed_utc = parsed.astimezone(pytz.utc)
                    
                state = self.compose_states[uid]
                try:
                    await self.db.db.run(lambda: self.db.db.client.table("scheduled_emails").insert({
                        "telegram_id": uid,
                        "to_email": state["to"],
                        "subject": state.get("subj", "No Subject"),
                        "body": state.get("body", ""),
                        "scheduled_time": parsed_utc.strftime("%Y-%m-%d %H:%M:%S")
                    }).execute())
                    self.compose_states.pop(uid, None)
                    await update.message.reply_text("✅ *Email Scheduled Successfully!*", parse_mode="Markdown", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🏠 Menu", callback_data="menu_main")]]))
                except Exception as e:
                    logger.error(f"Manual schedule error: {e}")
                    await update.message.reply_text("❌ Failed to schedule.")
                return

            if self.search_states.get(uid) == "AWAIT_QUERY":
                self.search_states.pop(uid)
                self.current_queries[uid] = text
                wait = await update.message.reply_text(f"🔍 Searching `{_safe_md(text)}`...")
                found = await self.contacts.find_contacts_by_name(uid, text)
                if found:
                    extra = " OR ".join(f"from:{c['email_address']}" for c in found)
                    self.current_queries[uid] = f"({extra}) OR {text}"
                    
            if self.settings_states.get(uid) == "AWAIT_TIMEZONE":
                # Fallback text parsing for timezone
                tz_str = await self.ai_engine.parse_timezone_with_groq(text)
                if not tz_str:
                    query_clean = text.lower().strip().replace(" ", "_")
                    for tz in pytz.all_timezones:
                        if query_clean in tz.lower():
                            tz_str = tz
                            break
                if tz_str:
                    await self.db.update_user_preferences(uid, {"timezone": tz_str})
                    self.settings_states.pop(uid, None)
                    await update.message.reply_text(f"🌍 *Timezone set to {tz_str} successfully!*", parse_mode="Markdown", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back to Settings", callback_data="settings")]]))
                else:
                    await update.message.reply_text("❌ *Could not find that timezone.* Please try typing a major city (e.g. 'London', 'Karachi', 'New York') or send a Location pin.", parse_mode="Markdown")
                return
                    
                await self._show_list(wait, uid, offset=0, is_search=True)
                return

            if not acc["user"].get("ai_allowed", True):
                await update.message.reply_text("🚫 *AI access restricted* for your account.",
                                                 parse_mode="Markdown")
                return

            
            # --- AI Strict Manual Fallback Guard ---
            prefs = await self._prefs(uid)
            if not prefs.get("ai_mode_enabled", True) and uid not in self.compose_states and not self.search_states.get(uid):
                await update.message.reply_text("🤖 *AI Mode is currently OFF.*\\n\\nPlease use the /menu buttons to navigate manually, or turn on AI Mode in Settings to chat naturally.", parse_mode="Markdown")
                return

            msg = await update.message.reply_text("✨ *Thinking...*", parse_mode="Markdown")
            await context.bot.send_chat_action(chat_id=uid, action=ChatAction.TYPING)

            # Cache query so the [🔄 Retry] button can re-submit it after a failure
            self.last_user_queries[uid] = {"type": "text", "content": text}

            raw = await self.ai_engine.agent_chat(text, uid)
            await self._dispatch_ai(update, context, msg, raw, uid, await self._prefs(uid))
            # Log conversation asynchronously in the background — does NOT block the response
            self._bg(self.memory.log_conversation(
                telegram_id=uid,
                user_message=text[:500],
                bot_response=raw[:500] if raw else "",
                interaction_type="chat",
            ))
        except Exception as e:
            logger.error(f"Unhandled error in handle_text for user {u.id}: {e}", exc_info=True)
            if update.message:
                await update.message.reply_text(
                    "⚠️ *System temporarily unavailable.*\n"
                    "An unexpected error occurred. Please try again later.",
                    parse_mode="Markdown"
                )

    async def _compose_step(self, update: Update, uid: int, text: str):
        state = self.compose_states[uid]
        step  = state.get("step")

        if step == "AWAIT_TO":
            email_regex = r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$"
            clean_text = text.strip()
            
            # Graceful Intent Exit: If the text is conversational (>3 words) and not an email
            if len(clean_text.split()) > 3 and not re.match(email_regex, clean_text):
                self.compose_states.pop(uid, None)
                return False

            if not re.match(email_regex, clean_text):
                # Search contacts for potential name matches
                found = await self.contacts.find_contacts_by_name(uid, clean_text)
                if not found:
                    state["to"] = clean_text
                    await update.message.reply_text(
                        "⚠️ *Validation Warning:* The email address format seems unusual or invalid.\n\n"
                        "Do you want to proceed anyway or type a new one?",
                        parse_mode="Markdown",
                        reply_markup=InlineKeyboardMarkup([
                            [InlineKeyboardButton("✅ Proceed", callback_data="force_to_email")],
                            [InlineKeyboardButton("❌ Cancel", callback_data="cancel")]
                        ])
                    )
                    return
                elif len(found) == 1:
                    state["to"] = found[0]["email_address"]
                    if state.get("body") and state.get("subj"):
                        state["step"] = "AWAIT_ATT"
                        await update.message.reply_text(
                            _draft_text(state), parse_mode="Markdown",
                            reply_markup=kb_draft(bool(state.get("attachments"))))
                    else:
                        state["step"] = "AWAIT_SUBJ"
                        await update.message.reply_text(
                            f"✅ *To:* `{_safe_md(state['to'])}`\n\n📝 *Enter Subject:*",
                            parse_mode="Markdown", reply_markup=kb_cancel())
                    return
                else:
                    # Multiple matches found: present ambiguity selection inline keyboard
                    rows = []
                    for c in found:
                        lbl = f"{c.get('contact_name')} ({c.get('email_address')})"
                        rows.append([InlineKeyboardButton(lbl, callback_data=f"select_contact:{c.get('email_address')}")])
                    rows.append([InlineKeyboardButton("❌ Cancel", callback_data="cancel")])
                    
                    await update.message.reply_text(
                        "🔍 *Multiple Contacts Found:*\nSelect the correct recipient:",
                        parse_mode="Markdown",
                        reply_markup=InlineKeyboardMarkup(rows)
                    )
                    return

            state["to"] = clean_text
            if state.get("body") and state.get("subj"):
                state["step"] = "AWAIT_ATT"
                await update.message.reply_text(
                    _draft_text(state), parse_mode="Markdown",
                    reply_markup=kb_draft(bool(state.get("attachments"))))
            else:
                state["step"] = "AWAIT_SUBJ"
                await update.message.reply_text(
                    f"✅ *To:* `{_safe_md(state['to'])}`\n\n📝 *Enter Subject:*",
                    parse_mode="Markdown", reply_markup=kb_cancel())

        elif step == "AWAIT_SUBJ":
            state["subj"] = text
            state["step"] = "AWAIT_BODY"
            await update.message.reply_text(
                "✍️ *Enter message body:*\n_(or send a voice note)_",
                parse_mode="Markdown", reply_markup=kb_cancel())

        elif step == "AWAIT_BODY":
            state["body"] = text
            state["step"] = "AWAIT_ATT"
            await update.message.reply_text(
                _draft_text(state), parse_mode="Markdown",
                reply_markup=kb_draft(bool(state.get("attachments"))))

        elif step == "AWAIT_ATT":
            await update.message.reply_text(
                "📎 Upload files to attach, then tap *Send Now*.",
                parse_mode="Markdown",
                reply_markup=kb_draft(bool(state.get("attachments"))))

    # ── Voice handler ──────────────────────────────────────────────────────────

    async def handle_voice(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        u   = update.effective_user


        acc = await self._check_access(u.id, u.first_name or "", u.username or "")
        if await self._gate(update, u.id, acc["status"]):
            return
            
        if not acc["user"].get("voice_allowed", True):
            await update.message.reply_text("🚫 *Voice access restricted.*", parse_mode="Markdown")
            return

        
        # --- AI Strict Manual Fallback Guard ---
        prefs = await self._prefs(uid)
        if not prefs.get("ai_mode_enabled", True) and uid not in self.compose_states:
            await update.message.reply_text("🤖 *AI Mode is currently OFF.*\\n\\nPlease use the /menu buttons to navigate manually, or turn on AI Mode in Settings to chat naturally.", parse_mode="Markdown")
            return

        msg = await update.message.reply_text("🎙️ *Processing voice note...*", parse_mode="Markdown")
        fp  = os.path.join(tempfile.gettempdir(), f"voice_{uuid.uuid4().hex}.ogg")
        
        try:
            vf = await context.bot.get_file(update.message.voice.file_id)
            await vf.download_to_drive(fp)
            transcribed = await self.ai_engine.transcribe_audio(fp, u.id)
        finally:
            if os.path.exists(fp):
                try:
                    os.remove(fp)
                except Exception:
                    pass

        if "[Audio Unclear]" in transcribed or transcribed.startswith("System Error"):
            await msg.edit_text("❌ *Audio unclear.* Please try again.", parse_mode="Markdown")
            return

        uid = u.id

        if uid in self.compose_states and self.compose_states[uid].get("step") == "AWAIT_BODY":
            self.compose_states[uid]["body"] = transcribed
            self.compose_states[uid]["step"] = "AWAIT_ATT"
            await msg.edit_text(
                _draft_text(self.compose_states[uid]),
                parse_mode="Markdown",
                reply_markup=kb_draft(bool(self.compose_states[uid].get("attachments"))))
            return

        task_id = str(int(time.time() * 1000))
        self.active_voice_tasks.add(task_id)
        
        await msg.edit_text(
            f"🗣️ *Heard:* _{_safe_md(transcribed)}_\n\n✨ *Processing...*",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("❌ Cancel", callback_data=f"cancel_voice:{task_id}")
            ]]))

        # Cache transcribed query so the [🔄 Retry] button can re-submit it after a failure
        self.last_user_queries[uid] = {"type": "text", "content": transcribed}

        try:
            raw = await self.ai_engine.agent_chat(transcribed, uid)

            if task_id not in self.active_voice_tasks:
                return

            self.active_voice_tasks.discard(task_id)
            await self._dispatch_ai(update, context, msg, raw, uid, await self._prefs(uid))
            # Log voice interaction asynchronously in the background
            self._bg(self.memory.log_conversation(
                telegram_id=uid,
                user_message=transcribed[:500],
                bot_response=raw[:500] if raw else "",
                interaction_type="voice",
            ))
            # Extract contacts asynchronously based on the transcript
            # DISABLED (CRITICAL): self._bg(self.contacts.extract_and_save_contacts(uid, transcribed))
        except Exception as e:
            logger.error(f"Unhandled error in handle_voice for user {uid}: {e}", exc_info=True)
            if task_id in self.active_voice_tasks:
                self.active_voice_tasks.discard(task_id)
            await self._edit(msg,
                "⚠️ *System temporarily unavailable.*\n"
                "An unexpected error occurred. Please try again or tap Retry.",
                InlineKeyboardMarkup([[InlineKeyboardButton("🔄 Retry", callback_data="retry_last_query")]]))

    # ── Attachment handler ─────────────────────────────────────────────────────

    async def handle_attachment(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        u   = update.effective_user


        acc = await self._check_access(u.id, u.first_name or "", u.username or "")
        if await self._gate(update, u.id, acc["status"]):
            return

        att = (update.message.document
               or (update.message.photo[-1] if update.message.photo else None)
               or update.message.audio or update.message.video)
               
        if not att:
            return

        if getattr(att, "file_size", 0) > 20971520:
            await update.message.reply_text("❌ *File too large.* The Telegram Bot API restricts bot downloads to a maximum of 20 MB per file.", parse_mode="Markdown")
            return

        uid   = u.id
        ext   = (getattr(att, "file_name", "file") or "file").rsplit(".", 1)[-1]
        fname = getattr(att, "file_name", f"file_{uuid.uuid4().hex[:6]}.{ext}")
        fpath = os.path.join(tempfile.gettempdir(), f"att_{uuid.uuid4().hex}.{ext}")
        msg   = await update.message.reply_text("📥 *Downloading...*", parse_mode="Markdown")

        try:
            fo = await context.bot.get_file(att.file_id)
            await fo.download_to_drive(fpath)
        except Exception as e:
            logger.error(f"Telegram file download failed: {e}")
            await msg.edit_text("❌ *Download failed.* Could not fetch the attachment from Telegram servers.", parse_mode="Markdown")
            return

        if uid in self.compose_states and self.compose_states[uid].get("step") != "PAUSED":
            state = self.compose_states[uid]
            state.setdefault("attachments", []).append(fpath)
            state["step"] = "AWAIT_ATT"
            await msg.edit_text(
                _draft_text(state), parse_mode="Markdown",
                reply_markup=kb_draft(True))
            return

        self.gmail.add_user_attachment(uid, fpath, fname)
        caption = update.message.caption or ""
        if caption:
            raw = await self.ai_engine.agent_chat(f"[Uploaded: {fname}] {caption}", uid)
            await self._dispatch_ai(update, context, msg, raw, uid, await self._prefs(uid))
        else:
            await msg.edit_text(
                f"✅ *Saved:* `{_safe_md(fname)}`\nTell me what to do with it or compose an email.",
                parse_mode="Markdown",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("✍️ Compose", callback_data="compose")],
                    kb_back_step(),
                ]))

    # ── AI response dispatcher ─────────────────────────────────────────────────

    async def _dispatch_ai(self, update, context, msg_obj, raw: str, uid: int, prefs: dict):
        # AI Engine Bubble-Up Interceptor
        if raw == "TOKEN_EXPIRED_REAUTH_REQUIRED" or "TOKEN_EXPIRED_REAUTH_REQUIRED" in raw:
            return await self._prompt_reauth(msg_obj, uid)

        if raw == "__GROQ_QUOTA_ERROR__":
            await self._edit(
                msg_obj,
                "⚠️ *Groq STT/Routing Limit Reached*\n\n"
                "Please wait a moment."
            )
            return

        # ── QUOTA EXCEEDED INTERCEPTOR ───────────────────────────────────────────────
        # Returned by ai_engine when Gemini raises HTTP 429 / ResourceExhausted.
        if raw == "__API_QUOTA_EXCEEDED__":
            await self._edit(
                msg_obj,
                "⚠️ *Gemini API Quota Exhausted*\n\n"
                "Please wait 1 minute."
            )
            return

        # AFC path: ai_engine returns the sentinel string "__SHOW_SEARCH_LIST__" when
        # AFC resolved search_gmail_tool internally and the UI needs to be rendered.
        if raw == "__SHOW_SEARCH_LIST__":
            search_data = self.ai_engine.pending_searches.pop(uid, {})
            query_str = search_data.get("query", self.current_queries.get(uid, "label:INBOX"))
            self.current_queries[uid] = query_str
            await self._show_list(msg_obj, uid, offset=0, is_search=True)
            return
            
        # If it was a natural text query that happened to use search in the background, clear the queue without UI interruption.
        if uid in self.ai_engine.pending_searches:
            self.ai_engine.pending_searches.pop(uid, None)

    async def handle_location(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        u = update.effective_user
        uid = u.id
        if self.settings_states.get(uid) == "AWAIT_TIMEZONE" and update.message.location:
            lat = update.message.location.latitude
            lng = update.message.location.longitude
            tf = TimezoneFinder()
            tz_str = tf.timezone_at(lng=lng, lat=lat)
            if tz_str:
                await self.db.update_user_preferences(uid, {"timezone": tz_str})
                self.settings_states.pop(uid, None)
                await update.message.reply_text(f"🌍 *Timezone set to {tz_str} successfully!*", parse_mode="Markdown", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back to Settings", callback_data="settings")]]))
            else:
                await update.message.reply_text("❌ *Could not determine timezone.* Please try typing your City/Country.", parse_mode="Markdown")
            return

        text_content = raw.replace("__SHOW_SEARCH_LIST__", "").strip()
        draft_data   = None

        # ── 1. TAG INTERCEPTOR: Detect and Clean [VOICE] ──
        is_voice_type = False
        if "[VOICE]" in text_content:
            is_voice_type = True
            text_content = text_content.replace("[VOICE]", "").strip()

        # ── 1b. SHOW_EMAIL INTERCEPTOR: Detect [SHOW_EMAIL:<id>] and render card ──
        show_email_match = re.search(r'\[SHOW_EMAIL:([^\]]+)\]', text_content)
        if show_email_match:
            detected_mid = show_email_match.group(1).strip()
            text_content = re.sub(r'\[SHOW_EMAIL:[^\]]+\]', '', text_content).strip()
            self._store_mid(detected_mid)
            # Show the email card UI — pass msg_obj which _show_email now handles
            try:
                await self._show_email(msg_obj, detected_mid[:16], "inbox", 0, uid)
            except Exception as e:
                logger.warning(f"SHOW_EMAIL card render failed: {e}. Falling back to text.")
                fallback_txt = text_content if text_content else "I was unable to display the email card. Please try again."
                await self._edit(msg_obj, fallback_txt)
            return


        # 🚀 2. SCHEDULE INTERCEPTOR 🚀

        if uid in self.ai_engine.pending_schedules:
            schedule_data = self.ai_engine.pending_schedules.pop(uid)
            sch_id = schedule_data.get("schedule_id", "UNKNOWN")
            to_field = _safe_md(schedule_data.get("to_email", "Unknown"))
            subj_field = _safe_md(schedule_data.get("subject", "No Subject"))
            time_field = _safe_md(schedule_data.get("scheduled_time", "Unknown"))
            
            kb = InlineKeyboardMarkup([
                [InlineKeyboardButton("✅ Confirm Schedule", callback_data=f"confirm_sch:{sch_id}")],
                [InlineKeyboardButton("⏳ Edit Time", callback_data=f"edit_sch_time:{sch_id}"),
                 InlineKeyboardButton("✍️ Edit Draft/Subject", callback_data=f"edit_sch_draft:{sch_id}")],
                [InlineKeyboardButton("❌ Cancel Schedule", callback_data=f"cancel_sch:{sch_id}")]
            ])
            await self._edit(msg_obj,
                f"🕒 *Email Scheduled Successfully!*\n"
                f"──────────────────\n"
                f"✉️ *To:* `{to_field}`\n"
                f"📝 *Subject:* `{subj_field}`\n"
                f"⏳ *Time:* `{time_field}`\n",
                kb)
            return

        # 🚀 3. DRAFT INTERCEPTOR 🚀

        if uid in self.ai_engine.pending_drafts:
            draft_data = self.ai_engine.pending_drafts.pop(uid)

        # ── Handle Draft UI Structure ──
        if draft_data:
            to_field = (draft_data.get("to") or "").strip()
            if not to_field or "[Specify Recipient" in to_field:
                self.compose_states[uid] = {
                    "step": "AWAIT_TO",
                    "subj": draft_data.get("subject", ""),
                    "body": draft_data.get("body", ""),
                    "attachments": [],
                }
                await self._edit(msg_obj,
                    f"📝 *Draft Ready — Recipient Needed*\n"
                    f"━━━━━━━━━━━━━━━━━━\n"
                    f"📝 *Subject:* `{_safe_md(draft_data.get('subject', '—'))}`\n\n"
                    f"⚠️ Please type the *recipient's email address:*",
                    kb_cancel())
            else:
                self.compose_states[uid] = {
                    "step":        "AWAIT_ATT",
                    "to":          draft_data.get("to", ""),
                    "subj":        draft_data.get("subject", ""),
                    "body":        draft_data.get("body", ""),
                    "attachments": [],
                }
                await self._edit(msg_obj, _draft_text(self.compose_states[uid]), kb_draft(bool(self.compose_states[uid].get("attachments"))))
            return

        # ── 3. VOICE / TEXT ROUTING ──
        # Strict logic based on user testing:
        voice_pref = prefs.get("voice_preference", "text")
        
        trigger_voice = False
        if voice_pref == "voice":
            trigger_voice = True
        elif voice_pref == "smart" and is_voice_type:
            trigger_voice = True
            
        # Hard text block
        if voice_pref == "text":
            trigger_voice = False

        if trigger_voice:
            await context.bot.send_chat_action(chat_id=uid, action=ChatAction.RECORD_VOICE)
            # Remove markdown symbols to prevent TTS engine from reading punctuation aloud
            clean_tts = re.sub(r'[*_#`]', '', text_content)
            audio = None
            try:
                try:
                    audio = await self.voice.synthesize(
                        clean_tts, telegram_id=uid,
                        preferred_method=prefs.get("preferred_tts_method", "google"))
                except Exception as tts_err:
                    logger.warning(f"TTS synthesis exception for user {uid}: {tts_err}")
                    audio = None
                    
                if audio and os.path.exists(audio):
                    with open(audio, "rb") as f:
                        try:
                            if is_voice_type:
                                # When AI explicitly wanted voice (Smart Routing), it acts like voice only.
                                await context.bot.send_voice(chat_id=uid, voice=f)
                            else:
                                await context.bot.send_voice(chat_id=uid, voice=f)
                                try:
                                    if hasattr(msg_obj, 'delete'): await msg_obj.delete()
                                    elif hasattr(msg_obj, 'message_id'): await context.bot.delete_message(chat_id=uid, message_id=msg_obj.message_id)
                                except Exception:
                                    await self._edit(msg_obj, "🎙️")
                        except Exception as e:
                            logger.warning(f"send_voice failed: {e}. Falling back to send_audio.")
                            f.seek(0)
                            if voice_pref == "both":
                                await context.bot.send_audio(chat_id=uid, audio=f, filename="voice.mp3")
                            else:
                                await context.bot.send_audio(chat_id=uid, audio=f, filename="voice.mp3")
                                try:
                                    if hasattr(msg_obj, 'delete'): await msg_obj.delete()
                                    elif hasattr(msg_obj, 'message_id'): await context.bot.delete_message(chat_id=uid, message_id=msg_obj.message_id)
                                except Exception:
                                    await self._edit(msg_obj, "🎙️")
                    return
                else:
                    logger.warning(f"TTS audio generation failed for user {uid}, falling back to text.")
            finally:
                if audio and os.path.exists(audio):
                    try:
                        os.remove(audio)
                    except Exception:
                        pass

        fallback_msg = text_content if text_content else None
        if fallback_msg:
            # Check if this is a contact save/query response
            email_match = re.search(r'[\w\.-]+@[\w\.-]+\.\w+', fallback_msg)
            is_contact_related = any(k in fallback_msg.lower() for k in ["contact", "saved", "email is", "address is", "successfully saved"])
            
            # Suppress intermediate/filler phrases if the LLM leaked them while running natural text background tools
            if fallback_msg.lower().strip() in ["okay, main check kar raha hoon", "checking...", "i am checking", "wait", "working on it"]:
                fallback_msg = "✅ Processing complete."
            
            if is_contact_related and email_match:
                email = email_match.group(0)
                markup = InlineKeyboardMarkup([[InlineKeyboardButton("✉️ Compose", callback_data=f"compose_to:{email}")]])
                clean_msg = fallback_msg.strip()
                if "saved successfully" in clean_msg.lower() and not clean_msg.startswith("✅"):
                    clean_msg = f"✅ {clean_msg}"
                await self._edit(msg_obj, clean_msg, markup=markup)
            else:
                await self._edit(msg_obj, fallback_msg)
        # If text_content is empty (e.g. tool completed silently), don't show any message.

    # ── Button handler ─────────────────────────────────────────────────────────

    async def handle_button(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        query = update.callback_query
        uid = query.from_user.id
        data = query.data
        
        try:
            await query.answer()
        except Exception:
            pass

        _NO_HISTORY_ACTIONS = {"cancel", "menu_main", "logout", "retry_last_query",
                                "attach_hint", "clear_att", "send_draft", "force_send_draft", "set_timezone"}
        pushed = False
        if not data.startswith("history_back") and data not in _NO_HISTORY_ACTIONS:
            await self._db_push_nav_stack(uid, data)
            pushed = True
            
        try:
            await self._handle_button_internal(update, context, data, uid)
        except Exception as e:
            logger.error(f"Error handling button '{data}' for user {uid}: {e}", exc_info=True)
            if pushed:
                await self._db_pop_nav_stack(uid) # Rollback the corrupted state
            try:
                await query.answer("⚠️ An error occurred. Please try again.", show_alert=True)
            except Exception:
                pass
            raise e

    async def _handle_button_internal(self, update: Update, context: ContextTypes.DEFAULT_TYPE, data: str, uid: int):
        query = update.callback_query

        action, args = _parse_cb(data)

        if action == "history_back":
            prev_state = await self._db_pop_nav_stack(uid)
            if not prev_state or prev_state == "menu_main":
                # History empty or expired — safe fallback to Dashboard.
                return await self.cmd_menu(update, context)

            # NOTIFICATION ORIGIN GUARD: If the previous state used the 'notif' context
            # tag (push notification card), Back should always go to Dashboard, not
            # attempt to re-render a list that doesn't exist in this session.
            _prev_action, _prev_args = _parse_cb(prev_state)
            _prev_ctx = _prev_args[1] if len(_prev_args) > 1 else ""
            if _prev_ctx == "notif":
                return await self.cmd_menu(update, context)

            # Replay the previous screen state via the normal routing below.
            data = prev_state
            action, args = _parse_cb(data)

        if action == "discard_then":
            for fp in (self.compose_states.pop(uid, {}) or {}).get("attachments", []):
                try:
                    os.remove(fp)
                except Exception:
                    pass
            self.compose_states.pop(uid, None)
            data = ":".join(args)
            action, args = _parse_cb(data)

        if action == "menu_main":
            self.search_states.pop(uid, None)
            self._clear_history(uid)
            
            has_draft = uid in self.compose_states
            if has_draft:
                state = self.compose_states[uid]
                if "step" in state and state["step"] != "PAUSED":
                    state["paused_step"] = state["step"]
                    state["step"] = "PAUSED"
                    
            await self._send(update, "🎛️ *Main Dashboard*\n\nSelect an action:", kb_main_menu(has_draft))
            return

        if action == "resume_draft":
            state = self.compose_states.get(uid)
            if not state:
                try:
                    await query.answer("❌ No active draft found.", show_alert=True)
                except Exception:
                    pass
                return
            
            # Restore paused step
            step = state.pop("paused_step", "AWAIT_ATT")
            state["step"] = step
            
            if step == "AWAIT_TO":
                await self._edit(query, 
                    "✉️ *Compose Email*\n\nEnter the *recipient's email address:*",
                    parse_mode="Markdown", reply_markup=kb_cancel())
            elif step == "AWAIT_SUBJ":
                await self._edit(query, 
                    f"✅ *To:* `{_safe_md(state['to'])}`\n\n📝 *Enter Subject:*",
                    parse_mode="Markdown", reply_markup=kb_cancel())
            elif step == "AWAIT_BODY":
                await self._edit(query, 
                    "✍️ *Enter message body:*\n_(or send a voice note)_",
                    parse_mode="Markdown", reply_markup=kb_cancel())
            elif step == "AWAIT_ATT":
                await self._edit(query, 
                    _draft_text(state), parse_mode="Markdown",
                    reply_markup=kb_draft(bool(state.get("attachments"))))
            return

        # ── Retry Last Query ─────────────────────────────────────────────────────
        if action == "retry_last_query":
            last_query = self.last_user_queries.get(uid)
            if not last_query:
                try:
                    await query.answer("❌ No previous query found to retry.", show_alert=True)
                except Exception:
                    pass
                return
            
            try:
                msg = await self._edit(query, "✨ *Retrying your last request...*", parse_mode="Markdown")
            except Exception:
                msg = await context.bot.send_message(chat_id=uid, text="✨ *Retrying your last request...*", parse_mode="Markdown")
            
            await context.bot.send_chat_action(chat_id=uid, action=ChatAction.TYPING)
            try:
                raw = await self.ai_engine.agent_chat(last_query["content"], uid)
                await self._dispatch_ai(update, context, msg, raw, uid, await self._prefs(uid))
            except Exception as e:
                logger.error(f"Error in retry_last_query for user {uid}: {e}", exc_info=True)
                await self._edit(msg,
                    "⚠️ *System temporarily unavailable.*\n"
                    "The server is still overloaded. Please wait a moment and try again.",
                    InlineKeyboardMarkup([[InlineKeyboardButton("🔄 Retry", callback_data="retry_last_query")]]))
            return

        if action == "inbox":
            try:
                offset = int(args[0]) if args else 0
            except (ValueError, IndexError):
                offset = 0
            await self._show_list(query.message, uid, offset, is_search=False)
            return

        if action == "srpage":
            try:
                offset = int(args[0]) if args else 0
            except (ValueError, IndexError):
                offset = 0
            if uid not in self.current_queries:
                # No active search context — fall back to inbox list
                await self._show_list(query.message, uid, offset, is_search=False)
                return
            await self._show_list(query.message, uid, offset, is_search=True)
            return

        if action == "search_prompt":
            self.search_states[uid] = "AWAIT_QUERY"
            await self._edit(query, 
                "🔍 *Search Emails*\n\n"
                "Type your Gmail query below:\n"
                "_(e.g. `from:john`, `invoice`, `is:unread`, `subject:meeting`)_",
                parse_mode="Markdown",
                reply_markup=InlineKeyboardMarkup([kb_back_step()]))
            return

        if action == "compose":
            if uid in self.compose_states and _has_draft_content(self.compose_states[uid]):
                await self._edit(query, 
                    "⚠️ *Active Draft Detected*\n\nYou have an unsaved draft in progress. Starting a new email will discard your current draft.",
                    parse_mode="Markdown",
                    reply_markup=InlineKeyboardMarkup([
                        [InlineKeyboardButton("📝 Resume Existing Draft", callback_data="resume_draft")],
                        [InlineKeyboardButton("🗑️ Discard & Start New", callback_data="discard_then:compose")]
                    ])
                )
                return
            self.compose_states[uid] = {"step": "AWAIT_TO", "attachments": []}
            await self._edit(query, 
                "✉️ *Compose Email*\n\nEnter the *recipient's email address:*",
                parse_mode="Markdown", reply_markup=kb_cancel())
            return

        if action == "cancel":
            for fp in (self.compose_states.pop(uid, {}) or {}).get("attachments", []):
                try:
                    os.remove(fp)
                except Exception:
                    pass
            self.compose_states.pop(uid, None)
            self.search_states.pop(uid, None)
            self._clear_history(uid)
            await self._edit(query, 
                "🚫 *Canceled.*\n\nReturning to dashboard.",
                parse_mode="Markdown",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Menu", callback_data="menu_main")]]))
            return


        if action == "list_sch":
            try:
                res = await self.db.db.run(
                    lambda: self.db.db.client.table("scheduled_emails")
                            .select("*").eq("telegram_id", uid).eq("status", "pending")
                            .order("scheduled_time", desc=False).execute())
                
                tasks = getattr(res, "data", []) or []
                if not tasks:
                    await self._edit(query, 
                        "📭 *No Scheduled Emails*\n\nYou have no pending scheduled emails.",
                        parse_mode="Markdown",
                        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Menu", callback_data="menu_main")]])
                    )
                    return
                
                text = "📅 *Your Scheduled Emails:*\n\n"
                kb_rows = []
                for idx, task in enumerate(tasks, 1):
                    # Convert to user timezone for display
                    try:
                        t_utc = datetime.strptime(task.get('scheduled_time', '1970-01-01 00:00:00'), "%Y-%m-%d %H:%M:%S").replace(tzinfo=pytz.utc)
                        prefs = await self._prefs(uid)
                        user_tz = pytz.timezone(prefs.get("timezone", "UTC"))
                        t_local = t_utc.astimezone(user_tz).strftime("%Y-%m-%d %I:%M %p")
                    except Exception:
                        t_local = task.get('scheduled_time', 'Unknown')

                    t_sub = task.get('subject', 'No Subject')
                    text += f"*{idx}.* `{t_local}`\n    _Sub:_ {t_sub}\n\n"
                
                kb_rows.append([InlineKeyboardButton("✏️ Edit Scheduled Email", callback_data="select_sch_edit")])
                kb_rows.append([InlineKeyboardButton("🔙 Menu", callback_data="menu_main")])
                await self._edit(query, text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(kb_rows))
            except Exception as e:
                logger.error(f"Failed to list scheduled emails: {e}")
                await query.answer("❌ Failed to retrieve scheduled emails.", show_alert=True)
            return
            
        if action == "select_sch_edit":
            try:
                res = await self.db.db.run(lambda: self.db.db.client.table("scheduled_emails").select("id, subject").eq("telegram_id", uid).eq("status", "pending").order("scheduled_time", desc=False).execute())
                tasks = getattr(res, "data", []) or []
                if not tasks:
                    await query.answer("No pending emails to edit.", show_alert=True)
                    return
                kb_rows = []
                for idx, task in enumerate(tasks, 1):
                    kb_rows.append([InlineKeyboardButton(f"Email {idx}: {task.get('subject', 'No Subject')[:15]}...", callback_data=f"manage_sch:{task['id']}")])
                kb_rows.append([InlineKeyboardButton("🔙 Back", callback_data="list_sch")])
                await self._edit(query, "✏️ *Which email do you want to modify?*", parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(kb_rows))
            except Exception as e:
                logger.error(f"Failed to select sch edit: {e}")
                await query.answer("❌ Failed to fetch emails.", show_alert=True)
            return

        if action == "manage_sch":
            sch_id = args[0] if args else ""
            if not sch_id: return
            try:
                res = await self.db.db.run(lambda: self.db.db.client.table("scheduled_emails").select("*").eq("id", sch_id).execute())
                tasks = getattr(res, "data", []) or []
                if not tasks:
                    await query.answer("Email not found.", show_alert=True)
                    return
                task = tasks[0]
                to_field = _safe_md(task.get("to_email", "Unknown"))
                subj_field = _safe_md(task.get("subject", "No Subject"))
                time_field = _safe_md(task.get("scheduled_time", "Unknown"))
                
                kb = InlineKeyboardMarkup([
                    [InlineKeyboardButton("✅ Confirm Schedule", callback_data=f"confirm_sch:{sch_id}")],
                    [InlineKeyboardButton("⏳ Edit Time", callback_data=f"edit_sch_time:{sch_id}"),
                     InlineKeyboardButton("✏️ Edit Draft/Subject", callback_data=f"edit_sch_draft:{sch_id}")],
                    [InlineKeyboardButton("❌ Cancel Schedule", callback_data=f"cancel_sch:{sch_id}")]
                ])
                await self._edit(query,
                    f"📅 *Manage Scheduled Email*\n"
                    f"━━━━━━━━━━━━━━━━━━\n"
                    f"👤 *To:* `{to_field}`\n"
                    f"📝 *Subject:* `{subj_field}`\n"
                    f"⏳ *UTC Time:* `{time_field}`\n",
                    parse_mode="Markdown",
                    reply_markup=kb)
            except Exception as e:
                logger.error(f"Failed to manage sch {sch_id}: {e}")
                await query.answer("❌ Failed to load schedule.", show_alert=True)
            return

        if action == "confirm_sch":
            await query.edit_message_reply_markup(InlineKeyboardMarkup([[InlineKeyboardButton("🏠 Menu", callback_data="menu_main")]]))
            await query.answer("✅ Schedule Confirmed!", show_alert=False)
            return

        if action == "edit_sch_time":
            await query.answer("🎙️ To edit the time, simply send a voice note or text saying 'Reschedule it to tomorrow at 5 PM'.", show_alert=True)
            return

        if action == "edit_sch_draft":
            await query.answer("🎙️ To edit the draft, just tell me 'Change the subject of my scheduled email to X'.", show_alert=True)
            return

        if action == "cancel_sch":
            sch_id = args[0] if args else ""
            if sch_id:
                try:
                    await self.db.db.run(lambda: self.db.db.client.table("scheduled_emails").delete().eq("id", sch_id).execute())
                    await self._edit(query, 
                        "🚫 *Scheduled Email Canceled.*\n\nThe email will not be sent.",
                        parse_mode="Markdown",
                        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🏠 Menu", callback_data="menu_main")]]))
                except Exception as e:
                    logger.error(f"Failed to cancel schedule {sch_id}: {e}")
                    await query.answer("❌ Failed to cancel schedule.", show_alert=True)
            return

        # ── Edit Draft Hub Integration ──
        if action == "edit_draft_hub":
            await self._edit(query, 
                "✏️ *Modify Draft Structure Parameters*\nSelect the attribute component boundary grid to update directly:",
                parse_mode="Markdown",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("👤 Recipient", callback_data="edit_field_to")],
                    [InlineKeyboardButton("📝 Subject",     callback_data="edit_field_subj")],
                    [InlineKeyboardButton("✉️ Body",        callback_data="edit_field_body")],
                    [InlineKeyboardButton("🔙 Back",        callback_data="restore_draft_view")]
                ])
            )
            return

        if action.startswith("edit_field_"):
            # Guard: compose state must exist and be active before mutating
            if uid not in self.compose_states or not self.compose_states.get(uid):
                await self._edit(query, 
                    "⚠️ *Draft expired.* Please start a new email.",
                    parse_mode="Markdown",
                    reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("✍️ Compose", callback_data="compose")]])
                )
                return
            target_field = action.replace("edit_field_", "")
            self.compose_states[uid]["step"] = f"AWAIT_{target_field.upper()}"
            await self._edit(query, 
                f"📝 Input new specifications for *{target_field.upper()}* parameters:",
                parse_mode="Markdown", reply_markup=kb_cancel()
            )
            return

        if action == "restore_draft_view":
            state = self.compose_states.get(uid)
            if not state:
                await self._edit(query, 
                    "⚠️ *Draft expired.* Please start a new email.",
                    parse_mode="Markdown",
                    reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("✍️ Compose", callback_data="compose")]])
                )
                return
            await self._edit(query, 
                _draft_text(state),
                parse_mode="Markdown",
                reply_markup=kb_draft(bool(state.get("attachments")))
            )
            return

        if action == "cancel_voice":
            self.active_voice_tasks.discard(args[0] if args else "")
            await self._edit(query, 
                "🚫 *Voice command canceled.*", parse_mode="Markdown",
                reply_markup=InlineKeyboardMarkup([kb_back_step()]))
            return

        if action == "attach_hint":
            await query.answer("📎 Upload any file in this chat to attach it!", show_alert=True)
            return

        if action == "clear_att":
            # Must access the ACTUAL dict in compose_states, not a default-copy
            state = self.compose_states.get(uid)
            if not state:
                # State expired; go back to menu
                await self._edit(query, 
                    "⚠️ *Draft expired.* Returning to dashboard.",
                    parse_mode="Markdown",
                    reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🏠 Menu", callback_data="menu_main")]])
                )
                return
            for fp in state.get("attachments", []):
                try:
                    os.remove(fp)
                except Exception:
                    pass
            state["attachments"] = []
            await self._edit(query, 
                _draft_text(state), parse_mode="Markdown",
                reply_markup=kb_draft(False))
            return


        if action == "schedule_draft_manual":
            self.compose_states[uid]["step"] = "AWAIT_SCHEDULE_TIME"
            kb = InlineKeyboardMarkup([
                [InlineKeyboardButton("🔙 Back to Draft", callback_data="restore_draft_view")]
            ])
            await self._edit(query, 
                "📅 *Schedule Email*\n\n"
                "When would you like to send this? Type a time using natural language:\n"
                "(e.g., 'tomorrow at 3pm', 'next monday morning', 'in 2 hours')\n\n"
                "The bot will use your configured timezone to accurately schedule this.",
                parse_mode="Markdown", reply_markup=kb)
            return

        if action == "send_draft":
            await self._do_send_draft(query, uid, context)
            return

        if action == "force_send_draft":
            state = self.compose_states.get(uid)
            if state:
                state["skip_validation"] = True
            await self._do_send_draft(query, uid, context)
            return

        if action == "force_to_email":
            state = self.compose_states.get(uid)
            if not state or state.get("step") != "AWAIT_TO":
                return
            
            if state.get("body") and state.get("subj"):
                state["step"] = "AWAIT_ATT"
                await self._edit(query, 
                    _draft_text(state), parse_mode="Markdown",
                    reply_markup=kb_draft(bool(state.get("attachments"))))
            else:
                state["step"] = "AWAIT_SUBJ"
                await self._edit(query, 
                    f"✅ *To:* `{_safe_md(state['to'])}`\n\n📝 *Enter Subject:*",
                    parse_mode="Markdown", reply_markup=kb_cancel())
            return

        if action == "select_contact":
            email = args[0] if args else ""
            state = self.compose_states.get(uid)
            if state and state.get("step") == "PAUSED" and _has_draft_content(state):
                await self._edit(query, 
                    "⚠️ *Active Draft Detected*\n\nYou have an unsaved draft in progress. Starting a new email will discard your current draft.",
                    parse_mode="Markdown",
                    reply_markup=InlineKeyboardMarkup([
                        [InlineKeyboardButton("📝 Resume Existing Draft", callback_data="resume_draft")],
                        [InlineKeyboardButton("🗑️ Discard & Start New", callback_data=f"discard_then:select_contact:{':'.join(args)}")]
                    ])
                )
                return

            if not state:
                self.compose_states[uid] = {
                    "step": "AWAIT_SUBJ",
                    "to": email,
                    "subj": "",
                    "body": "",
                    "attachments": []
                }
                state = self.compose_states[uid]
            else:
                state["to"] = email
                
            self._bg(self.memory.log_conversation(
                telegram_id=uid,
                user_message=f"[System UI Action] User disambiguated and explicitly selected recipient.",
                bot_response=f"Recipient strictly locked to: {email}",
                interaction_type="chat"
            ))
                
            if state.get("body") and state.get("subj"):
                state["step"] = "AWAIT_ATT"
                await self._edit(query, 
                    _draft_text(state), parse_mode="Markdown",
                    reply_markup=kb_draft(bool(state.get("attachments"))))
            else:
                state["step"] = "AWAIT_SUBJ"
                await self._edit(query, 
                    f"✅ *To:* `{_safe_md(state['to'])}`\n\n📝 *Enter Subject:*",
                    parse_mode="Markdown", reply_markup=kb_cancel()
                )
            return

        if action == "compose_to":
            email = args[0] if args else ""
            if uid in self.compose_states and _has_draft_content(self.compose_states[uid]):
                await self._edit(query, 
                    "⚠️ *Active Draft Detected*\n\nYou have an unsaved draft in progress. Starting a new email will discard your current draft.",
                    parse_mode="Markdown",
                    reply_markup=InlineKeyboardMarkup([
                        [InlineKeyboardButton("📝 Resume Existing Draft", callback_data="resume_draft")],
                        [InlineKeyboardButton("🗑️ Discard & Start New", callback_data=f"discard_then:compose_to:{':'.join(args)}")]
                    ])
                )
                return
            self.compose_states[uid] = {
                "step": "AWAIT_SUBJ",
                "to": email,
                "subj": "",
                "body": "",
                "attachments": []
            }
            await self._edit(query, 
                f"✅ *To:* `{_safe_md(email)}`\n\n📝 *Enter Subject:*",
                parse_mode="Markdown", reply_markup=kb_cancel()
            )
            return

        if action == "settings":
            prefs = await self._prefs(uid)
            await self._edit(query, 
                "⚙️ *Settings*\n\nConfigure your assistant preferences:",
                parse_mode="Markdown",
                reply_markup=kb_settings(
                    prefs.get("ai_mode_enabled", True),
                    prefs.get("voice_preference", "text"),
                    prefs.get("auto_check_enabled", True),
                    prefs.get("pagination_limit", 2),
                    prefs.get("draft_style", "Detailed")))
            return

        if action in ["toggle_ai", "cycle_voice", "toggle_auto", "cycle_pagination", "cycle_draft"]:
            prefs   = await self._prefs(uid)
            if action == "toggle_ai":
                await self.db.update_user_preferences(uid, {"ai_mode_enabled": not prefs.get("ai_mode_enabled", True)})
            elif action == "toggle_auto":
                await self.db.update_user_preferences(uid, {"auto_check_enabled": not prefs.get("auto_check_enabled", True)})
            elif action == "cycle_voice":
                cycle   = {"text": "voice", "voice": "smart", "smart": "text"}
                await self.db.update_user_preferences(uid, {"voice_preference": cycle.get(prefs.get("voice_preference", "text"), "text")})
            elif action == "cycle_pagination":
                current_limit = prefs.get("pagination_limit", 2)
                new_limit = 5 if current_limit == 2 else 2
                await self.db.update_user_preferences(uid, {"pagination_limit": new_limit})
            elif action == "cycle_draft":
                current_style = prefs.get("draft_style", "Detailed")
                new_style = "Concise" if current_style == "Detailed" else "Detailed"
                await self.db.update_user_preferences(uid, {"draft_style": new_style})
            elif action == "set_timezone":
                self.settings_states[uid] = "AWAIT_TIMEZONE"
                await self._edit(query, 
                    "🌍 *Set Your Timezone*\n\n"
                    "You can update your timezone using either of these methods:\n\n"
                    "1️⃣ *Type your City/Country* (e.g. 'London', 'Pakistan', 'New York')\n"
                    "2️⃣ *Send a Location Pin* (📎 Attachment -> Location)\n\n"
                    "The bot will use this to accurately display times for your scheduled emails.",
                    parse_mode="Markdown",
                    reply_markup=InlineKeyboardMarkup([kb_back_step()]))
                return
            
            prefs = await self._prefs(uid)
            await self._edit(query, 
                "⚙️ *Settings*\n\nConfigure your assistant preferences:", parse_mode="Markdown", 
                reply_markup=kb_settings(
                    prefs.get("ai_mode_enabled", True), 
                    prefs.get("voice_preference", "text"), 
                    prefs.get("auto_check_enabled", True),
                    prefs.get("pagination_limit", 2),
                    prefs.get("draft_style", "Detailed")))
            return

        if action == "logout":
            await self.db.db.run(lambda: self.db.db.client.table("users")
                                  .update({"auth_token": None})
                                  .eq("telegram_id", uid).execute())
            self.gmail.clear_cache(uid)
            self.gmail.clear_user_attachments(uid)
            self.compose_states.pop(uid, None)
            await self._edit(query, 
                "✅ *Logged out.*\nSend /start to reconnect your Google account.",
                parse_mode="Markdown")
            return

        # ── Parameterized email actions ────────────────────────────────────────

        if len(args) < 3:
            # Malformed callback — silently return to avoid crashes
            logger.debug(f"handle_button: malformed callback '{data}' for user {uid} — insufficient args")
            return

        mid_s = args[0]
        ctx   = args[1]
        try:
            offset = int(args[2])
        except (ValueError, IndexError):
            offset = 0

        if action == "read":
            await self._show_email(query, mid_s, ctx, offset, uid)
            return

        if action == "read_html":
            await self._do_read_html(query, context, mid_s, ctx, offset, uid)
            return

        if action == "sum":
            await self._do_summary(query, context, mid_s, ctx, offset, uid)
            return

        if action == "tts":
            await self._do_tts(query, context, mid_s, ctx, offset, uid)
            return

        if action == "att":
            await self._do_attachments(query, context, mid_s, ctx, offset, uid)
            return

        if action == "del":
            full_mid = self._full_mid(mid_s)
            res = await self.gmail.delete_email(uid, full_mid)
            if res == "TOKEN_EXPIRED_REAUTH_REQUIRED":
                return await self._prompt_reauth(query.message, uid)
            if res:
                await self._edit(query, 
                    "🗑️ *Email moved to Trash.*",
                    parse_mode="Markdown",
                    reply_markup=InlineKeyboardMarkup([
                        [InlineKeyboardButton("↩️ Undo", callback_data=_cb("untrash", mid_s, ctx, offset))],
                        kb_back_step()
                    ]))
            return

        if action == "untrash":
            res = await self.gmail.untrash_email(uid, self._full_mid(mid_s))
            if res == "TOKEN_EXPIRED_REAUTH_REQUIRED":
                return await self._prompt_reauth(query.message, uid)
            if res:
                await self._show_email(query, mid_s, ctx, offset, uid)
            return

        if action == "reply":
            if uid in self.compose_states and _has_draft_content(self.compose_states[uid]):
                await self._edit(query, 
                    "⚠️ *Active Draft Detected*\n\nYou have an unsaved draft in progress. Replying to this email will discard your current draft.",
                    parse_mode="Markdown",
                    reply_markup=InlineKeyboardMarkup([
                        [InlineKeyboardButton("📝 Resume Existing Draft", callback_data="resume_draft")],
                        [InlineKeyboardButton("🗑️ Discard & Reply", callback_data=f"discard_then:reply:{':'.join(args)}")]
                    ])
                )
                return

            full_mid = self._full_mid(mid_s)
            meta     = await self.gmail.get_email_metadata(uid, full_mid)
            if meta == "TOKEN_EXPIRED_REAUTH_REQUIRED":
                return await self._prompt_reauth(query.message, uid)
                
            sender   = meta.get("sender", "")
            m        = re.search(r'<(.+?)>', sender)
            email    = m.group(1) if m else sender.strip()
            subj     = meta.get("subject", "")
            
            self.compose_states[uid] = {
                "step":  "AWAIT_BODY",
                "to":    email,
                "subj":  f"Re: {subj}" if not subj.startswith("Re:") else subj,
                "attachments": [],
            }
            await self._edit(query, 
                f"↩️ *Reply to:* `{_safe_md(email)}`\n\n✍️ Type your reply:",
                parse_mode="Markdown", reply_markup=kb_cancel())
            return

        # ── Unrecognised action — safe fallback ─────────────────────────────────
        # If we reach here, no handler matched the callback data. Log it and
        # return the user to the Dashboard rather than hanging silently.
        logger.debug(f"handle_button: unrecognised action '{action}' (data='{data}') for user {uid}")
        try:
            await self._edit(query, 
                "🎛️ *Main Dashboard*\n\nSelect an action:",
                parse_mode="Markdown",
                reply_markup=kb_main_menu(uid in self.compose_states)
            )
        except Exception:
            pass

    async def _do_send_draft(self, query, uid: int, context):
        """Immediately dispatches payload configuration. Removed legacy 7-second undo limits."""
        state = self.compose_states.get(uid)
        if not state:
            return

        to_email = state.get("to", "").strip()
        skip_validation = state.get("skip_validation", False)
        email_regex = r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$"

        if not skip_validation and (not to_email or "[Specify" in to_email or not re.match(email_regex, to_email)):
            await self._edit(query, 
                "⚠️ *Validation Error:* Cannot process outbound data streams. Recipient address is invalid.", 
                parse_mode="Markdown", 
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("✅ Proceed", callback_data="force_send_draft")],
                    [InlineKeyboardButton("🔙 Fix Parameters", callback_data="compose")]
                ])
            )
            return

        self.compose_states.pop(uid, None)

        msg = await self._edit(query, "⏳ *Sending Email...*", parse_mode="Markdown")

        async def _send_immediately():
            try:
                result = await self.gmail.send_email(
                    uid, state["to"], state.get("subj", "No Subject"), state.get("body", ""),
                    state.get("attachments", [])
                )
                
                if result == "TOKEN_EXPIRED_REAUTH_REQUIRED":
                    return await self._prompt_reauth(msg, uid)
                    
                self._bg(self._save_contact(uid, state["to"]))
                await msg.edit_text(
                    f"✅ *Email Dispatched Successfully!*", 
                    parse_mode="Markdown", 
                    reply_markup=InlineKeyboardMarkup([kb_back_step()])
                )
            except Exception as e:
                error_msg = str(e)
                user_friendly_alert = "❌ *Transmission Error:* Form validation checks failed."
                if "Invalid To header" in error_msg:
                    user_friendly_alert = "⚠️ *Invalid Destination:* The recipient email format is invalid."
                
                await msg.edit_text(
                    user_friendly_alert, 
                    parse_mode="Markdown", 
                    reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Fix Parameters", callback_data="compose")]])
                )
            finally:
                for fp in state.get("attachments", []):
                    if os.path.exists(fp):
                        try:
                            os.remove(fp)
                        except Exception as e:
                            logger.error(f"Failed cleaning up attachment {fp}: {e}")

        asyncio.create_task(_send_immediately())

    async def _do_read_html(self, query, context, mid_short: str, ctx: str, offset: int, uid: int):
        await self._edit(query, "⏳ *Retrieving full HTML layout...*", parse_mode="Markdown")
        full_mid = self._full_mid(mid_short)

        html_body = await self.gmail.get_email_html(uid, full_mid)
        if html_body == "TOKEN_EXPIRED_REAUTH_REQUIRED":
            return await self._prompt_reauth(query.message, uid)

        if not html_body:
            await self._edit(query, "❌ *Failed to fetch full email HTML.*", parse_mode="Markdown", reply_markup=InlineKeyboardMarkup([kb_back_step()]))
            return

        meta = await self.gmail.get_email_metadata(uid, full_mid)
        subject = meta.get("subject", "email") if isinstance(meta, dict) else "email"

        # Sanitize filename
        safe_filename = re.sub(r'[\\/*?:"<>|]', "", subject).strip()
        if not safe_filename:
            safe_filename = "email"

        import io
        html_bytes = io.BytesIO(html_body.encode('utf-8'))
        html_bytes.name = f"{safe_filename}.html"

        back_markup = InlineKeyboardMarkup([
            [InlineKeyboardButton("🔙 Back to Email", callback_data=_cb("read", mid_short, ctx, offset))]
        ])

        try:
            await context.bot.send_document(
                chat_id=uid,
                document=html_bytes,
                filename=f"{safe_filename}.html",
                caption=(
                    "📄 *Interactive Email Document*\n\n"
                    "Open this file in your browser to view the original email with full styles, layouts, and images intact."
                ),
                parse_mode="Markdown",
                reply_markup=back_markup
            )
            # Delete the loading message to keep the chat clean
            try:
                await getattr(query, "message", query).delete()
            except Exception:
                pass
        except Exception as e:
            logger.error(f"Failed sending HTML fallback document: {e}")
            await self._edit(query, "❌ *Failed to transmit HTML document.*", parse_mode="Markdown", reply_markup=back_markup)

    async def _do_summary(self, query, context, mid_short: str, ctx: str, offset: int, uid: int):
        # The message that triggered this callback may be a voice/audio message
        # (sent from the TTS view). Editing a voice message for text raises BadRequest.
        # We try to edit; if that fails we send a new loader message instead.
        loading_msg = None
        try:
            await self._edit(query, "⏳ *Generating AI Summary...*", parse_mode="Markdown")
            loading_msg = query.message
        except Exception:
            try:
                loading_msg = await context.bot.send_message(
                    chat_id=uid, text="⏳ *Generating AI Summary...*", parse_mode="Markdown"
                )
            except Exception:
                loading_msg = None

        full_mid = self._full_mid(mid_short)

        details = await self.gmail.get_email_details(uid, full_mid)
        if details == "TOKEN_EXPIRED_REAUTH_REQUIRED":
            return await self._prompt_reauth(query.message, uid)

        meta = await self.gmail.get_email_metadata(uid, full_mid)
        if meta == "TOKEN_EXPIRED_REAUTH_REQUIRED":
            return await self._prompt_reauth(query.message, uid)

        if not details or not meta or (isinstance(meta, dict) and "error" in meta):
            err_text = "❌ *Email not found.* It may have been deleted."
            if loading_msg:
                try:
                    await loading_msg.edit_text(err_text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup([kb_back_step()]))
                except Exception:
                    await context.bot.send_message(chat_id=uid, text=err_text, parse_mode="Markdown")
            return

        body = details.get("body", "") if details else ""
        # Use the token-efficient direct summarize call
        sum_text = await self.ai_engine.summarize_email(body)

        raw_sender = meta.get("sender", "Unknown")
        name, email = _parse_sender_header(raw_sender)
        if email:
            sender_formatted = f"👤 *From:* *{_safe_md(name)}* `({_safe_md(email)})`"
        else:
            sender_formatted = f"👤 *From:* *{_safe_md(name)}*"
        subject = _safe_md(meta.get("subject", "No Subject"))
        att_ct  = len(meta.get("attachments", []))

        text = (
            f"📩 *Email Summary*\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"{sender_formatted}\n"
            f"📝 *Subject:* _{subject}_\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"🤖 *AI Summary:*\n"
            f"{sum_text}"
        )

        kb = kb_summary(full_mid, ctx, offset, bool(att_ct))
        if loading_msg:
            try:
                await loading_msg.edit_text(text, parse_mode="Markdown", reply_markup=kb)
            except Exception:
                await context.bot.send_message(chat_id=uid, text=text, parse_mode="Markdown", reply_markup=kb)
        else:
            await context.bot.send_message(chat_id=uid, text=text, parse_mode="Markdown", reply_markup=kb)

    async def _do_tts(self, query, context, mid_short: str, ctx: str, offset: int, uid: int):
        await self._edit(query, "🔊 *Generating audio summary...*", parse_mode="Markdown")
        await context.bot.send_chat_action(chat_id=uid, action=ChatAction.RECORD_VOICE)

        full_mid = self._full_mid(mid_short)
        details = await self.gmail.get_email_details(uid, full_mid)
        if details == "TOKEN_EXPIRED_REAUTH_REQUIRED":
            return await self._prompt_reauth(query.message, uid)
            
        meta = await self.gmail.get_email_metadata(uid, full_mid)
        if meta == "TOKEN_EXPIRED_REAUTH_REQUIRED":
            return await self._prompt_reauth(query.message, uid)

        if not details or not meta or (isinstance(meta, dict) and "error" in meta):
            await self._edit(query, "❌ *Email not found.* It may have been deleted.", parse_mode="Markdown", reply_markup=InlineKeyboardMarkup([kb_back_step()]))
            return

        body = details.get("body", "") if details else ""
        # Use the token-efficient TTS summary call — avoids polluting chat history
        # and skips tool-setup tokens. Returns clean text ready for TTS with no markdown.
        clean_tts = await self.ai_engine.summarize_email(body)

        prefs = await self._prefs(uid)
        audio = None
        try:
            try:
                audio = await self.voice.synthesize(
                    clean_tts, telegram_id=uid,
                    preferred_method=prefs.get("preferred_tts_method", "google"))
            except Exception as e:
                logger.error(f"TTS synthesis failed in _do_tts: {e}")
                audio = None

            raw_sender = meta.get("sender", "Unknown")
            name, email = _parse_sender_header(raw_sender)
            if email:
                sender_formatted = f"👤 *From:* *{_safe_md(name)}* `({_safe_md(email)})`"
            else:
                sender_formatted = f"👤 *From:* *{_safe_md(name)}*"
            subject = _safe_md(meta.get("subject", ""))
            att_ct  = len(meta.get("attachments", []))

            rows = [[InlineKeyboardButton("📖 Read Full", callback_data=_cb("read", full_mid[:16], ctx, offset))]]
            if att_ct: rows.append([InlineKeyboardButton("📥 Attachments", callback_data=_cb("att", full_mid[:16], ctx, offset))])
            rows.append(kb_nav_for_ctx(ctx))
            kb = InlineKeyboardMarkup(rows)

            caption = f"🔊 *Audio Summary*\n{sender_formatted}\n📝 *Subject:* _{subject}_"

            if audio and os.path.exists(audio):
                with open(audio, "rb") as f:
                    try:
                        await context.bot.send_voice(chat_id=uid, voice=f, caption=caption, parse_mode="Markdown", reply_markup=kb)
                    except Exception as e:
                        logger.warning(f"send_voice failed in _do_tts: {e}. Falling back to send_audio.")
                        f.seek(0)
                        await context.bot.send_audio(chat_id=uid, audio=f, caption=caption, parse_mode="Markdown", reply_markup=kb, filename="voice.mp3")
                try:
                    await getattr(query, "message", query).delete()
                except Exception: pass
            else:
                await self._edit(query, "❌ *Audio generation failed.*", markup=kb)
        finally:
            if audio and os.path.exists(audio):
                try:
                    os.remove(audio)
                except Exception:
                    pass

    async def _do_attachments(self, query, context, mid_short: str, ctx: str, offset: int, uid: int):
        await self._edit(query, "⏳ *Fetching attachments...*", parse_mode="Markdown")
        full_mid = self._full_mid(mid_short)
        back_kb  = InlineKeyboardMarkup([kb_nav_for_ctx(ctx)])

        try:
            meta = await self.gmail.get_email_metadata(uid, full_mid)
            if meta == "TOKEN_EXPIRED_REAUTH_REQUIRED":
                return await self._prompt_reauth(query.message, uid)
            if len(meta.get("attachments", [])) > 10:
                await self._edit(query, "⚠️ *Download Blocked:* Max 10 files allowed.", parse_mode="Markdown", reply_markup=back_kb)
                return
        except Exception:
            pass

        paths = await self.gmail.get_attachments(uid, full_mid)
        if paths == "TOKEN_EXPIRED_REAUTH_REQUIRED":
            return await self._prompt_reauth(query.message, uid)

        if not paths:
            await self._edit(query, "📭 *No downloadable attachments found.*", parse_mode="Markdown", reply_markup=back_kb)
            return

        await self._edit(query, f"📤 *Sending {len(paths)} attachment(s)...*", parse_mode="Markdown")

        sent = 0
        for att_info in paths:
            try:
                if isinstance(att_info, dict):
                    fp = att_info["path"]
                    orig_name = att_info["original_filename"]
                else:
                    fp = att_info
                    orig_name = None
                
                with open(fp, "rb") as f:
                    if orig_name:
                        await context.bot.send_document(chat_id=uid, document=f, filename=orig_name)
                    else:
                        await context.bot.send_document(chat_id=uid, document=f)
                sent += 1
            except Exception as e:
                logger.error(f"Attachment send error: {e}")
            finally:
                try:
                    if isinstance(att_info, dict):
                        os.remove(att_info["path"])
                    else:
                        os.remove(att_info)
                except Exception:
                    pass

        await self._edit(query, f"✅ *{sent}/{len(paths)} file(s) sent.*", parse_mode="Markdown", reply_markup=back_kb)

    # ── Background Jobs ────────────────────────────────────────────────────────

    async def job_ping(self, context: ContextTypes.DEFAULT_TYPE):
        import httpx
        try:
            async with httpx.AsyncClient(timeout=10) as c:
                await c.get(f"{settings.APP_URL}/health")
        except Exception:
            pass

    async def job_emails(self, context: ContextTypes.DEFAULT_TYPE):
        async with self.ram_semaphore:
            max_retries = 3
            for attempt in range(max_retries):
                try:
                    users = await self.db.get_active_auto_check_users()
                    for user in users:
                        uid = user["telegram_id"]
                        emails = await self.gmail.get_unread_emails(uid, limit=10)
                        
                        if emails == "TOKEN_EXPIRED_REAUTH_REQUIRED":
                            await self._send_reauth_direct(context, uid)
                            continue
                            
                        if not isinstance(emails, list):
                            continue

                        for email_item in emails:
                            mid = email_item["id"]
                            if mid in self.notified_emails:
                                continue
                            self.notified_emails.add(mid)
                            self._store_mid(mid)

                            meta = await self.gmail.get_email_metadata(uid, mid)
                            if not meta or meta == "TOKEN_EXPIRED_REAUTH_REQUIRED" or "error" in meta:
                                continue

                            raw_sender = meta.get("sender", "Unknown")
                            name, email = _parse_sender_header(raw_sender)
                            if email:
                                sender_formatted = f"👤 *From:* *{_safe_md(name)}* `({_safe_md(email)})`"
                            else:
                                sender_formatted = f"👤 *From:* *{_safe_md(name)}*"
                            subject = _safe_md(meta.get("subject", "No Subject"))
                            att_ct  = len(meta.get("attachments", []))
                            att_line = f"\n📎 *{att_ct} Attachment(s) Found*" if att_ct else ""

                            text = (
                                f"📩 *New Email Received*\n"
                                f"━━━━━━━━━━━━━━━━━━\n"
                                f"{sender_formatted}\n"
                                f"📝 *Subject:* _{subject}_"
                                f"{att_line}"
                            )

                            try:
                                await self.db.db.run(
                                    lambda u=uid, m=mid, s=meta.get("sender", ""), sub=meta.get("subject", ""):
                                    self.db.db.client.table("email_cache").upsert(
                                        {"telegram_id": u, "gmail_message_id": m,
                                         "sender": s, "subject": sub, "preview": "new"},
                                        on_conflict="telegram_id,gmail_message_id"
                                    ).execute()
                                )
                            except Exception:
                                pass

                            await context.bot.send_message(
                                chat_id=uid, text=text, parse_mode="Markdown",
                                reply_markup=kb_notification(mid, bool(att_ct)))
                    
                    # Explicit memory purge
                    try:
                        del emails
                    except NameError:
                        pass
                    try:
                        del meta
                    except NameError:
                        pass
                    try:
                        del users
                    except NameError:
                        pass
                    import gc
                    gc.collect()
                    
                    break 
                except Exception as e:
                    logger.error(f"job_emails connection error (attempt {attempt + 1}/{max_retries}): {e}")
                    if attempt < max_retries - 1:
                        await asyncio.sleep(3 ** attempt)


    async def job_scheduled(self, context: ContextTypes.DEFAULT_TYPE):
        async with self.ram_semaphore:
            max_retries = 3
            for attempt in range(max_retries):
                try:
                    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
                    res = await self.db.db.run(
                        lambda: self.db.db.client.table("scheduled_emails")
                                .select("*").eq("status", "pending")
                                .lte("scheduled_time", now).execute())
                    
                    for task in (getattr(res, "data", []) or []):
                        uid   = task["telegram_id"]
                        paths = []
                        try:
                            for att in (task.get("attachments") or []):
                                if isinstance(att, dict) and "file_id" in att:
                                    try:
                                        fo   = await context.bot.get_file(att["file_id"])
                                        path = os.path.join(
                                            tempfile.gettempdir(),
                                            att.get("file_name", f"att_{uuid.uuid4().hex[:6]}"))
                                        await fo.download_to_drive(path)
                                        paths.append(path)
                                    except Exception:
                                        pass

                            result = await self.gmail.send_email(uid, task["to_email"], task["subject"], task["body"], paths)
                                
                            if result == "TOKEN_EXPIRED_REAUTH_REQUIRED":
                                await self._send_reauth_direct(context, uid)
                                await self.db.db.run(
                                    lambda t=task: self.db.db.client.table("scheduled_emails")
                                    .update({"status": "failed"}).eq("id", t["id"]).execute())
                                continue
                                
                            status = "sent" if "successfully" in result.lower() else "failed"

                            await self.db.db.run(
                                lambda t=task, s=status: self.db.db.client.table("scheduled_emails")
                                .update({"status": s}).eq("id", t["id"]).execute())

                            note = (f"✅ Your scheduled email to {_safe_md(task['to_email'])} regarding {_safe_md(task.get('subject', ''))} has been successfully sent just now."
                                    if status == "sent"
                                    else f"❌ *Scheduled Email Failed*\n{_safe_md(result)}")
                            await context.bot.send_message(chat_id=uid, text=note, parse_mode="Markdown")
                        finally:
                            for fp in paths:
                                if os.path.exists(fp):
                                    try:
                                        os.remove(fp)
                                    except Exception as e:
                                        logger.error(f"Failed cleaning up scheduled attachment {fp}: {e}")
                    
                    # Explicit memory purge
                    try:
                        del res
                    except NameError:
                        pass
                    import gc
                    gc.collect()
                    
                    break 
                except Exception as e:
                    logger.error(f"job_scheduled connection error (attempt {attempt + 1}/{max_retries}): {e}")
                    if attempt < max_retries - 1:
                        await asyncio.sleep(3 ** attempt) 

# ── Singleton ──────────────────────────────────────────────────────────────────
telegram_handler = TelegramBotManager()