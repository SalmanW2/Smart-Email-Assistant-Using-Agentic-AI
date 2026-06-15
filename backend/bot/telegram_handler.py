"""
Telegram Bot Handler — Smart Email Assistant
============================================
Production-ready Presentation Master Core.
Features Implemented:
- Atomic Dynamic Navigation History Stack (Self-correcting Back Buttons).
- Cold Start Startup Filtering (Prevents lagging loops & crashes on boot).
- MIME String Sanitization (Blocks Markdown parse entity crashes).
- Dynamic Token Interceptor & Login Cleanup (Handles 401/403 gracefully).
- Absolute 20MB File Limits & Safe Dispatch Pipelines.
"""

import logging
import os
import time
import asyncio
import tempfile
import uuid
import re
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
from bot.contact_manager import contact_manager

logging.basicConfig(level=logging.INFO)
# Hide spammy API logs to maintain clean terminal telemetry
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("apscheduler").setLevel(logging.WARNING)
logger = logging.getLogger(__name__)


# ── Callback Helpers & Sanitizers ──────────────────────────────────────────────

def _cb(action: str, *args) -> str:
    """Safely constructs callback data strings enforcing the Telegram 64-byte limit."""
    data = ":".join([action] + [str(a) for a in args])
    if len(data) > 64:
        parts = data.split(":")
        if len(parts) >= 2:
            parts[1] = parts[1][:16]
            data = ":".join(parts)
    return data[:64]

def _parse_cb(data: str) -> tuple:
    """Parses callback payload into routing action and argument arrays."""
    parts = data.split(":")
    return parts[0], parts[1:]

def _clean_ai_text(raw: str) -> str:
    """Extracts clean presentation text from AI response, avoiding JSON leakage."""
    if not raw:
        return ""
    cleaned = re.sub(r'```json|```', '', raw).strip()
    
    m = re.search(r'\{.*\}', cleaned, re.DOTALL)
    if m:
        try:
            parsed = json.loads(m.group(0))
            text = parsed.get("text", "")
            if text:
                return str(text).strip()
        except Exception:
            pass
            
    if cleaned.startswith("{") and "text" in cleaned:
        t = re.search(r'"text"\s*:\s*"(.*?)"(?:,|\})', cleaned, re.DOTALL)
        if t:
            return t.group(1).replace("\\n", "\n").strip()
            
    return raw.strip()

def _safe_md(text: str) -> str:
    """Strict Markdown escape sequence to prevent 'Bad Request: parse entities' crashes."""
    if not text: 
        return ""
    escape_chars = r"_*[]()~`>#+-=|{}.!"
    return "".join(f"\\{c}" if c in escape_chars else c for c in text)

def _esc_html(text: str) -> str:
    """Strict HTML escape sequence for robust payload rendering."""
    if not text: 
        return ""
    return str(text).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


# ── UI Keyboard Layouts ────────────────────────────────────────────────────────

def kb_main_menu() -> InlineKeyboardMarkup:
    """Builds the primary dashboard interface."""
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📥 Inbox",         callback_data=_cb("inbox", 0)),
         InlineKeyboardButton("✍️ Compose",        callback_data="compose")],
        [InlineKeyboardButton("🔍 Search Emails", callback_data="search_prompt"),
         InlineKeyboardButton("⚙️ Settings",       callback_data="settings")],
    ])

def kb_back_step() -> list:
    """Returns the dynamic history back button component."""
    return [InlineKeyboardButton("🔙 Go Back", callback_data="history_back")]

def kb_cancel() -> InlineKeyboardMarkup:
    """Generic operation cancel keyboard."""
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("❌ Cancel", callback_data="cancel")]
    ])

def kb_email_list(msgs: list, offset: int, is_search: bool, has_next: bool) -> InlineKeyboardMarkup:
    """Builds smart pagination keyboard for email lists."""
    rows = []
    ctx = "search" if is_search else "inbox"
    
    for i, m in enumerate(msgs):
        rows.append([InlineKeyboardButton(
            f"📖 Open Email {offset + i + 1}",
            callback_data=_cb("read", m["id"][:16], ctx, offset)
        )])
        
    nav = []
    if offset > 0:
        cb = _cb("srpage", offset - 2) if is_search else _cb("inbox", offset - 2)
        nav.append(InlineKeyboardButton("⬅️ Previous", callback_data=cb))
    if has_next:
        cb = _cb("srpage", offset + 2) if is_search else _cb("inbox", offset + 2)
        nav.append(InlineKeyboardButton("Next ➡️", callback_data=cb))
        
    if nav:
        rows.append(nav)
        
    rows.append(kb_back_step())
    return InlineKeyboardMarkup(rows)

def kb_email_view(msg_id: str, ctx: str, offset: int, has_att: bool) -> InlineKeyboardMarkup:
    """Action keyboard for a fully opened email."""
    mid = msg_id[:16]
    rows = [
        [InlineKeyboardButton("↩️ Reply",      callback_data=_cb("reply", mid, ctx, offset)),
         InlineKeyboardButton("🗑️ Trash",       callback_data=_cb("del",   mid, ctx, offset))],
        [InlineKeyboardButton("🤖 AI Summary", callback_data=_cb("sum",   mid, ctx, offset)),
         InlineKeyboardButton("🔊 Listen",      callback_data=_cb("tts",   mid, ctx, offset))],
    ]
    if has_att:
        rows.append([InlineKeyboardButton("📥 Get Attachments", callback_data=_cb("att", mid, ctx, offset))])
        
    rows.append(kb_back_step())
    return InlineKeyboardMarkup(rows)

def kb_summary(msg_id: str, ctx: str, offset: int, has_att: bool) -> InlineKeyboardMarkup:
    """Action keyboard tailored for AI summaries."""
    mid = msg_id[:16]
    rows = [
        [InlineKeyboardButton("📖 Read Full Email", callback_data=_cb("read", mid, ctx, offset)),
         InlineKeyboardButton("🔊 Listen",           callback_data=_cb("tts",  mid, ctx, offset))],
        [InlineKeyboardButton("↩️ Reply to Email", callback_data=_cb("reply", mid, ctx, offset))]
    ]
    if has_att:
        rows.insert(1, [InlineKeyboardButton("📥 Get Attachments", callback_data=_cb("att", mid, ctx, offset))])
        
    rows.append(kb_back_step())
    return InlineKeyboardMarkup(rows)

def kb_notification(msg_id: str, has_att: bool) -> InlineKeyboardMarkup:
    """Push notification interaction keyboard."""
    mid = msg_id[:16]
    rows = [
        [InlineKeyboardButton("📖 Read Email",   callback_data=_cb("read", mid, "inbox", 0))],
        [InlineKeyboardButton("🤖 AI Summary",   callback_data=_cb("sum",  mid, "inbox", 0)),
         InlineKeyboardButton("🔊 Listen",        callback_data=_cb("tts",  mid, "inbox", 0))],
    ]
    if has_att:
        rows.append([InlineKeyboardButton("📥 Get Attachments", callback_data=_cb("att", mid, "inbox", 0))])
        
    return InlineKeyboardMarkup(rows)

def kb_draft(has_files: bool = False) -> InlineKeyboardMarkup:
    """Dynamic Drafting and Edit Hub controls."""
    rows = [
        [InlineKeyboardButton("🚀 Send Now",       callback_data="send_draft"),
         InlineKeyboardButton("✏️ Edit Fields",    callback_data="edit_draft_hub")],
        [InlineKeyboardButton("📎 Add Attachment", callback_data="attach_hint"),
         InlineKeyboardButton("❌ Cancel",          callback_data="cancel")]
    ]
    if has_files:
        rows.insert(2, [InlineKeyboardButton("🗑️ Clear Attachments", callback_data="clear_att")])
        
    return InlineKeyboardMarkup(rows)

def kb_settings(ai_on: bool, voice: str, auto_on: bool) -> InlineKeyboardMarkup:
    """System preferences keyboard."""
    v_map = {"text": "📝 Text Only", "voice": "🔊 Voice Only", "both": "📝+🔊 Both"}
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(f"{'✅' if ai_on   else '❌'} AI Mode",          callback_data="toggle_ai")],
        [InlineKeyboardButton(v_map.get(voice, "📝 Text Only"),                callback_data="cycle_voice")],
        [InlineKeyboardButton(f"{'✅' if auto_on else '❌'} Auto Email Check", callback_data="toggle_auto")],
        [InlineKeyboardButton("🚪 Logout Account",                             callback_data="logout")],
        kb_back_step(),
    ])

def _draft_text(state: dict) -> str:
    """Generates draft preview formatting with sanitized attachment filenames."""
    files = state.get("attachments", [])
    # Safely sanitize filenames to prevent markdown parse errors
    att_names = [os.path.basename(f).replace('_', '-').replace('*', '') for f in files]
    att_ln = f"\n📎 *{len(files)} attachment(s) staged:*\n" + "\n".join([f"- `{n}`" for n in att_names]) if files else ""
    return (
        f"📄 *Draft Preview*\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"👤 *To:* `{state.get('to', '[Specify Recipient Email]')}`\n"
        f"📝 *Subject:* `{state.get('subj', '—')}`\n"
        f"✉️ *Body:*\n_{state.get('body', '—')}_\n"
        f"{att_ln}\n\n"
        f"Review your draft. Tap *Send Now* or *Edit Fields* to modify."
    )


# ── Telegram Master Controller ────────────────────────────────────────────────

class TelegramBotManager:
    def __init__(self):
        self.application: Application | None = None
        self.ai_engine       = ai_engine
        self.db              = db_manager
        self.memory          = memory_manager
        self.gmail           = GmailClient()
        self.voice           = voice_handler
        self.contacts        = contact_manager

        # Stateful Process Trackers
        self.compose_states:    dict = {}   
        self.search_states:     dict = {}   
        self.current_queries:   dict = {}   
        self._mid_cache:        dict = {}   
        self.notified_emails:    set = set()
        self.active_voice_tasks: set = set()
        self.email_lock = asyncio.Lock()

        # [CRITICAL FEATURE] Cold Start Filter: Prevents lagging loops & crashes on boot
        self.startup_time = datetime.now(timezone.utc).timestamp()

        # [CRITICAL FEATURE] Atomic Navigation Stack: Ensures back buttons don't hit dead ends
        self.navigation_history: Dict[int, List[str]] = {}

    # ── Internal Core ──────────────────────────────────────────────────────────

    def _full_mid(self, short: str) -> str:
        return self._mid_cache.get(short, short)

    def _store_mid(self, full_id: str):
        self._mid_cache[full_id[:16]] = full_id

    def _bg(self, coro):
        asyncio.create_task(coro)

    async def _prefs(self, uid: int) -> dict:
        try:
            prefs = await self.db.get_user_preferences(uid)
            if prefs: return prefs
        except Exception as e:
            logger.debug(f"Preference fetch fallback error: {e}")
        return {"ai_mode_enabled": True, "voice_preference": "text", "auto_check_enabled": True}

    async def _send(self, update: Update, text: str, markup: InlineKeyboardMarkup | None = None, parse_mode: str = "Markdown"):
        try:
            if update.callback_query:
                await update.callback_query.edit_message_text(text, parse_mode=parse_mode, reply_markup=markup, disable_web_page_preview=True)
            elif update.message:
                await update.message.reply_text(text, parse_mode=parse_mode, reply_markup=markup, disable_web_page_preview=True)
        except Exception as e:
            logger.debug(f"_send error execution: {e}")

    async def _edit(self, obj, text: str, markup: InlineKeyboardMarkup | None = None, parse_mode: str = "Markdown"):
        try:
            if hasattr(obj, "edit_text"):
                await obj.edit_text(text, parse_mode=parse_mode, reply_markup=markup, disable_web_page_preview=True)
            else:
                await obj.reply_text(text, parse_mode=parse_mode, reply_markup=markup, disable_web_page_preview=True)
        except Exception as e:
            logger.debug(f"_edit error execution: {e}")

    # ── Dynamic Back Navigation History Tracker ────────────────────────────────

    def _push_history(self, uid: int, state: str):
        """Pushes current screen state to stack for accurate back navigation."""
        if uid not in self.navigation_history:
            self.navigation_history[uid] = []
        if not self.navigation_history[uid] or self.navigation_history[uid][-1] != state:
            self.navigation_history[uid].append(state)

    def _pop_history(self, uid: int) -> Optional[str]:
        """Pops current state and retrieves previous state mapping."""
        if uid in self.navigation_history and len(self.navigation_history[uid]) > 1:
            self.navigation_history[uid].pop() # Remove current
            return self.navigation_history[uid].pop() # Extract previous
        return None

    def _clear_history(self, uid: int):
        self.navigation_history[uid] = []

    # ── Auth Redirection Lifecycle & Sentinel ──────────────────────────────────

    async def _prompt_reauth(self, msg_obj, uid: int):
        """Generates dynamic block message requesting re-authentication for active user clicks."""
        state = await self.db.create_auth_session(uid)
        url   = f"{settings.RENDER_WEB_SERVICE_URL}/api/auth/telegram_login?state={state}&telegram_id={uid}"
        text  = "⚠️ *Connection Broken:*\nYour Google Workspace token has expired or was revoked.\nPlease reconnect your account to continue."
        markup = InlineKeyboardMarkup([[InlineKeyboardButton("🔗 Reconnect Google Workspace", url=url)]])
        await self._edit(msg_obj, text, markup)

    async def _send_reauth_direct(self, context, uid: int):
        """Generates dynamic block message for background cron loops to prevent spam."""
        await self.db.update_user_preferences(uid, {"auto_check_enabled": False})
        state = await self.db.create_auth_session(uid)
        url   = f"{settings.RENDER_WEB_SERVICE_URL}/api/auth/telegram_login?state={state}&telegram_id={uid}"
        text  = ("⚠️ *Connection Broken:*\n"
                 "Your Google Workspace token has expired or been revoked.\n\n"
                 "Please reconnect your account to restore inbox syncing.\n"
                 "_(Background polling has been temporarily paused to prevent spam)._")
        markup = InlineKeyboardMarkup([[InlineKeyboardButton("🔗 Reconnect Google Workspace", url=url)]])
        try:
            await context.bot.send_message(chat_id=uid, text=text, parse_mode="Markdown", reply_markup=markup)
        except Exception:
            pass

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
            url   = (f"{settings.RENDER_WEB_SERVICE_URL}/api/auth/telegram_login"
                     f"?state={state}&telegram_id={uid}")
            await self._send(update,
                "⚠️ *Gmail Not Connected*\nLink your Google account to start:",
                InlineKeyboardMarkup([[InlineKeyboardButton("🔗 Connect Google Workspace", url=url)]]))
            return True
            
        return False

    # ── Setup ──────────────────────────────────────────────────────────────────

    async def setup_bot(self):
        """Initializes application core routines and binds webhook mappings."""
        self.application = ApplicationBuilder().token(settings.BOT_TOKEN).build()
        self.application.add_handler(CommandHandler("start", self.cmd_start))
        self.application.add_handler(CommandHandler("menu",  self.cmd_menu))
        self.application.add_handler(CallbackQueryHandler(self.handle_button))
        self.application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, self.handle_text))
        self.application.add_handler(MessageHandler(filters.VOICE, self.handle_voice))
        self.application.add_handler(MessageHandler(filters.Document.ALL | filters.PHOTO | filters.AUDIO | filters.VIDEO, self.handle_attachment))
            
        await self.application.initialize()
        
        if self.application.job_queue:
            self.application.job_queue.run_repeating(self.job_emails,    interval=60,  first=15)
            self.application.job_queue.run_repeating(self.job_scheduled, interval=60,  first=30)
            self.application.job_queue.run_repeating(self.job_ping,      interval=840, first=60)
            
        if settings.RENDER_WEB_SERVICE_URL and not settings.RENDER_WEB_SERVICE_URL.startswith("http://localhost"):
            await self.application.bot.set_webhook(url=f"{settings.RENDER_WEB_SERVICE_URL}/webhook/telegram")
            logger.info("✅ Bot production webhook live.")
        else:
            logger.info("⚠️ Local development cluster context detected. Skipping global webhook binding.")
            
        await self.application.start()

    async def process_webhook(self, data: dict):
        if self.application:
            update = Update.de_json(data, self.application.bot)
            await self.application.process_update(update)

    # ── Command & UI Handlers ──────────────────────────────────────────────────

    async def cmd_start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        u = update.effective_user
        
        # Cold Start Safety - Ignores obsolete queued commands
        if update.message and update.message.date.timestamp() < self.startup_time: 
            return

        acc = await self._check_access(u.id, u.first_name or "", u.username or "")
        if await self._gate(update, u.id, acc["status"]):
            return
            
        self._clear_history(u.id)
        await self._send(update,
            f"👋 *Welcome, {u.first_name}!*\n\n"
            "I'm your AI Email Assistant. Use the buttons below to manage your Gmail "
            "with text or voice commands.",
            kb_main_menu())

    async def cmd_menu(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        u = update.effective_user
        if update.message and update.message.date.timestamp() < self.startup_time: 
            return

        acc = await self._check_access(u.id, u.first_name or "", u.username or "")
        if await self._gate(update, u.id, acc["status"]):
            return
            
        self._clear_history(u.id)
        await self._send(update, "🎛️ *Main Dashboard*\n\nSelect an action:", kb_main_menu())

    # ── Email list ─────────────────────────────────────────────────────────────

    async def _show_list(self, msg_obj, uid: int, offset: int, is_search: bool):
        query = self.current_queries.get(uid, "is:unread") if is_search else "label:INBOX"
        try:
            messages = await self.gmail.get_emails(uid, query=query, max_results=offset + 3)
            # Sentinel Integrity Interceptor
            if messages == "TOKEN_EXPIRED_REAUTH_REQUIRED":
                return await self._prompt_reauth(msg_obj, uid)
        except Exception:
            messages = []

        if not messages and offset == 0:
            lbl = f"📭 No results for: `{query}`" if is_search else "📭 Your inbox is empty."
            await self._edit(msg_obj, lbl, InlineKeyboardMarkup([kb_back_step()]))
            return

        display  = messages[offset:offset + 2]
        has_next = len(messages) > offset + 2
        header   = f"🔍 *Results:* `{query}`\n\n" if is_search else "📥 *Your Inbox*\n\n"
        lines    = [header]

        for i, m in enumerate(display):
            self._store_mid(m["id"])
            meta = await self.gmail.get_email_metadata(uid, m["id"])
            if meta == "TOKEN_EXPIRED_REAUTH_REQUIRED":
                return await self._prompt_reauth(msg_obj, uid)
            if "error" in meta:
                continue
                
            sender  = _safe_md(meta.get("sender",  "Unknown"))
            subject = _safe_md(meta.get("subject", "No Subject"))
            lines.append(f"*{offset + i + 1}.* {sender}\n   _{subject}_\n")

        await self._edit(msg_obj, "\n".join(lines), kb_email_list(display, offset, is_search, has_next))

    # ── Full email render ──────────────────────────────────────────────────────

    async def _show_email(self, query, mid_short: str, ctx: str, offset: int, uid: int):
        await query.edit_message_text("⏳ Loading email...")
        full_mid = self._full_mid(mid_short)
        
        details = await self.gmail.get_email_details(uid, full_mid)
        if details == "TOKEN_EXPIRED_REAUTH_REQUIRED":
            return await self._prompt_reauth(query.message, uid)
            
        meta = await self.gmail.get_email_metadata(uid, full_mid)
        if meta == "TOKEN_EXPIRED_REAUTH_REQUIRED":
            return await self._prompt_reauth(query.message, uid)
            
        self._store_mid(meta.get("id", full_mid))

        body         = details.get("body", "") if details else ""
        safe_body    = _esc_html(body[:4000] + ("\n\n[… Truncated]" if len(body) > 4000 else ""))
        safe_sender  = _esc_html(meta.get("sender",  "Unknown"))
        safe_subject = _esc_html(meta.get("subject", "No Subject"))

        safe_body = re.sub(r'(https?://[^\s<>"]+)', r'<a href="\1">🔗 Link</a>', safe_body)

        att_list = meta.get("attachments", [])
        # MIME Stripping implementation
        att_names = [att.get("filename", "file").replace("_", "-").replace("*", "") for att in att_list]
        att_line = f"\n📎 <b>{len(att_list)} Attachment(s):</b> {', '.join(att_names)}" if att_list else ""

        text = (f"📧 <b>From:</b> {safe_sender}\n"
                f"📝 <b>Subject:</b> {safe_subject}{att_line}\n"
                f"{'━' * 20}\n\n{safe_body}")

        await query.edit_message_text(text, parse_mode="HTML",
                                       reply_markup=kb_email_view(full_mid, ctx, offset, bool(att_list)),
                                       disable_web_page_preview=True)
                                       
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

    # ── Text & Form Sequence Handlers ──────────────────────────────────────────

    async def handle_text(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        u = update.effective_user
        if update.message and update.message.date.timestamp() < self.startup_time: return

        acc = await self._check_access(u.id, u.first_name or "", u.username or "")
        if await self._gate(update, u.id, acc["status"]): return
            
        uid  = u.id
        text = update.message.text

        if uid in self.compose_states:
            return await self._compose_step(update, uid, text)

        if self.search_states.get(uid) == "AWAIT_QUERY":
            self.search_states.pop(uid)
            self.current_queries[uid] = text
            wait = await update.message.reply_text(f"🔍 Searching `{text}`...")
            found = await self.contacts.find_contacts_by_name(uid, text)
            if found:
                extra = " OR ".join(f"from:{c['email_address']}" for c in found)
                self.current_queries[uid] = f"({extra}) OR {text}"
                
            return await self._show_list(wait, uid, offset=0, is_search=True)

        if not acc["user"].get("ai_allowed", True):
            return await update.message.reply_text("🚫 *AI access restricted* for your account.", parse_mode="Markdown")

        msg = await update.message.reply_text("✨ *Thinking...*", parse_mode="Markdown")
        await context.bot.send_chat_action(chat_id=uid, action=ChatAction.TYPING)
        
        raw = await self.ai_engine.agent_chat(text, uid)
        await self._dispatch_ai(update, context, msg, raw, uid, await self._prefs(uid))

    async def _compose_step(self, update: Update, uid: int, text: str):
        state = self.compose_states[uid]
        step  = state.get("step")

        if step == "AWAIT_TO":
            state["to"] = text
            if state.get("body") and state.get("subj"):
                state["step"] = "AWAIT_ATT"
                await update.message.reply_text(_draft_text(state), parse_mode="Markdown", reply_markup=kb_draft(bool(state.get("attachments"))))
            else:
                state["step"] = "AWAIT_SUBJ"
                await update.message.reply_text(f"✅ *To:* `{text}`\n\n📝 *Enter Subject:*", parse_mode="Markdown", reply_markup=kb_cancel())

        elif step == "AWAIT_SUBJ":
            state["subj"] = text
            state["step"] = "AWAIT_BODY"
            await update.message.reply_text("✍️ *Enter message body:*\n_(or send a voice note)_", parse_mode="Markdown", reply_markup=kb_cancel())

        elif step == "AWAIT_BODY":
            state["body"] = text
            state["step"] = "AWAIT_ATT"
            await update.message.reply_text(_draft_text(state), parse_mode="Markdown", reply_markup=kb_draft(bool(state.get("attachments"))))

        elif step == "AWAIT_ATT":
            await update.message.reply_text("📎 Upload files to attach, then tap *Send Now*.", parse_mode="Markdown", reply_markup=kb_draft(bool(state.get("attachments"))))

    # ── Voice Processing Handler ───────────────────────────────────────────────

    async def handle_voice(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        u = update.effective_user
        if update.message and update.message.date.timestamp() < self.startup_time: return

        acc = await self._check_access(u.id, u.first_name or "", u.username or "")
        if await self._gate(update, u.id, acc["status"]): return
            
        if not acc["user"].get("voice_allowed", True):
            return await update.message.reply_text("🚫 *Voice access restricted.*", parse_mode="Markdown")

        msg = await update.message.reply_text("🎙️ *Processing voice note...*", parse_mode="Markdown")
        fp  = os.path.join(tempfile.gettempdir(), f"voice_{uuid.uuid4().hex}.ogg")
        
        try:
            vf = await context.bot.get_file(update.message.voice.file_id)
            await vf.download_to_drive(fp)
            transcribed = await self.ai_engine.transcribe_audio(fp, u.id)
        finally:
            if os.path.exists(fp):
                try: os.remove(fp)
                except Exception: pass

        if "[Audio Unclear]" in transcribed or transcribed.startswith("System Error"):
            return await msg.edit_text("❌ *Audio unclear.* Please try again.", parse_mode="Markdown")

        uid = u.id

        if uid in self.compose_states and self.compose_states[uid].get("step") == "AWAIT_BODY":
            self.compose_states[uid]["body"] = transcribed
            self.compose_states[uid]["step"] = "AWAIT_ATT"
            return await msg.edit_text(_draft_text(self.compose_states[uid]), parse_mode="Markdown", reply_markup=kb_draft(bool(self.compose_states[uid].get("attachments"))))

        task_id = str(int(time.time() * 1000))
        self.active_voice_tasks.add(task_id)
        
        await msg.edit_text(f"🗣️ *Heard:* _{_safe_md(transcribed)}_\n\n✨ *Processing...*", parse_mode="Markdown", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ Cancel", callback_data=f"cancel_voice:{task_id}")]]))

        raw = await self.ai_engine.agent_chat(transcribed, uid)
        
        if task_id not in self.active_voice_tasks: return
        self.active_voice_tasks.discard(task_id)
        await self._dispatch_ai(update, context, msg, raw, uid, await self._prefs(uid))

    # ── Strict Validation Attachment Handlers ──────────────────────────────────

    async def handle_attachment(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        u = update.effective_user
        if update.message and update.message.date.timestamp() < self.startup_time: return

        acc = await self._check_access(u.id, u.first_name or "", u.username or "")
        if await self._gate(update, u.id, acc["status"]): return

        att = (update.message.document or (update.message.photo[-1] if update.message.photo else None) or update.message.audio or update.message.video)
        if not att: return

        # 20MB Max Validation Guardrail
        if getattr(att, "file_size", 0) > 20971520:
            return await update.message.reply_text("❌ *File is too large for Telegram API (Max 20MB).* \nPlease use Google Drive links for massive files.", parse_mode="Markdown")

        uid   = u.id
        ext   = (getattr(att, "file_name", "file") or "file").rsplit(".", 1)[-1]
        fname = getattr(att, "file_name", f"file_{uuid.uuid4().hex[:6]}.{ext}")
        
        # Absolute string sanitization to prevent Markdown parser failures
        safe_fname = fname.replace('_', '-').replace('*', '')
        fpath = os.path.join(tempfile.gettempdir(), f"att_{uuid.uuid4().hex}.{ext}")
        msg   = await update.message.reply_text("📥 *Downloading...*", parse_mode="Markdown")

        try:
            fo = await context.bot.get_file(att.file_id)
            await fo.download_to_drive(fpath)
        except Exception as e:
            logger.error(f"Telegram file download failed: {e}")
            return await msg.edit_text("❌ *Download failed.* Could not fetch the attachment from Telegram servers.", parse_mode="Markdown")

        if uid in self.compose_states:
            state = self.compose_states[uid]
            state.setdefault("attachments", []).append(fpath)
            state["step"] = "AWAIT_ATT"
            return await msg.edit_text(_draft_text(state), parse_mode="Markdown", reply_markup=kb_draft(True))

        self.gmail.add_user_attachment(uid, fpath, safe_fname)
        caption = update.message.caption or ""
        if caption:
            raw = await self.ai_engine.agent_chat(f"[Uploaded: {safe_fname}] {caption}", uid)
            await self._dispatch_ai(update, context, msg, raw, uid, await self._prefs(uid))
        else:
            await msg.edit_text(
                f"✅ *Saved:* `{safe_fname}`\nTell me what to do with it or compose an email.",
                parse_mode="Markdown",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("✉️ Compose Email", callback_data="compose")],
                    kb_back_step()
                ]))

    # ── AI Context Dispatcher ──────────────────────────────────────────────────

    async def _dispatch_ai(self, update, context, msg_obj, raw: str, uid: int, prefs: dict):
        text_content = _clean_ai_text(raw)
        draft_data   = None

        if "198306a5" in text_content or "email id is" in text_content.lower() or "here is the email" in text_content.lower():
            mid_match = re.search(r'([a-f0-9]{16})', text_content.lower())
            if mid_match:
                detected_mid = mid_match.group(1)
                self._store_mid(detected_mid)
                return await self._show_email(msg_obj if update.callback_query else update.message, detected_mid, "inbox", 0, uid)

        try:
            cleaned = re.sub(r'```json|```', '', raw).strip()
            m       = re.search(r'\{.*\}', cleaned, re.DOTALL)
            if m:
                parsed       = json.loads(m.group(0))
                text_content = _clean_ai_text(raw)
                draft_data   = parsed.get("draft")
        except Exception: pass

        if uid in self.ai_engine.pending_drafts:
            draft_data = self.ai_engine.pending_drafts.pop(uid)

        if draft_data:
            to_field = (draft_data.get("to") or "").strip()
            if not to_field or "[Specify Recipient" in to_field:
                self.compose_states[uid] = {
                    "step": "AWAIT_TO",
                    "subj": draft_data.get("subject", ""),
                    "body": draft_data.get("body", ""),
                    "attachments": [],
                }
                return await self._edit(msg_obj,
                    f"📝 *Draft Ready — Recipient Needed*\n"
                    f"━━━━━━━━━━━━━━━━━━\n"
                    f"📝 *Subject:* `{draft_data.get('subject', '—')}`\n\n"
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
                return await self._edit(msg_obj, _draft_text(self.compose_states[uid]), kb_draft(bool(self.compose_states[uid].get("attachments"))))

        voice_pref = prefs.get("voice_preference", "text")
        try:
            parsed_full = json.loads(re.sub(r'```json|```', '', raw).strip())
            is_voice_type = parsed_full.get("response_type") == "voice"
        except Exception:
            is_voice_type = False

        if is_voice_type and voice_pref in ("voice", "both"):
            await context.bot.send_chat_action(chat_id=uid, action=ChatAction.RECORD_VOICE)
            clean_tts = re.sub(r'[*_#`]', '', text_content)
            audio     = await self.voice.synthesize(clean_tts, telegram_id=uid, preferred_method=prefs.get("preferred_tts_method", "google"))
                
            if audio and os.path.exists(audio):
                with open(audio, "rb") as f:
                    if voice_pref == "both":
                        await self._edit(msg_obj, f"🤖 {_safe_md(text_content)}", InlineKeyboardMarkup([kb_back_step()]))
                        await context.bot.send_voice(chat_id=uid, voice=f, reply_markup=InlineKeyboardMarkup([kb_back_step()]))
                    else:
                        await context.bot.send_voice(chat_id=uid, voice=f, caption="🔊 AI Response", reply_markup=InlineKeyboardMarkup([kb_back_step()]))
                        try: await msg_obj.delete()
                        except Exception: pass
                try: os.remove(audio)
                except Exception: pass
                return

        await self._edit(msg_obj, f"🤖 {_safe_md(text_content)}", InlineKeyboardMarkup([kb_back_step()]))

    # ── Master Button Router ───────────────────────────────────────────────────

    async def handle_button(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        query  = update.callback_query
        uid    = query.from_user.id
        data   = query.data
        try: await query.answer()
        except Exception: pass

        if not data.startswith("history_back") and data not in ["cancel", "menu_main"]:
            self._push_history(uid, data)

        action, args = _parse_cb(data)

        if action == "history_back":
            prev_state = self._pop_history(uid)
            if prev_state:
                query.data = prev_state
                return await self.handle_button(update, context)
            else:
                return await self.cmd_menu(update, context)

        if action == "menu_main":
            self.compose_states.pop(uid, None)
            self.search_states.pop(uid, None)
            self._clear_history(uid)
            return await self._send(update, "🎛️ *Main Dashboard*\n\nSelect an action:", kb_main_menu())

        if action == "inbox":
            offset = int(args[0]) if args else 0
            return await self._show_list(query.message, uid, offset, is_search=False)

        if action == "srpage":
            offset = int(args[0]) if args else 0
            return await self._show_list(query.message, uid, offset, is_search=True)

        if action == "search_prompt":
            self.search_states[uid] = "AWAIT_QUERY"
            return await query.edit_message_text(
                "🔍 *Search Emails*\n\n"
                "Type your Gmail query below:\n"
                "_(e.g. `from:john`, `invoice`, `is:unread`, `subject:meeting`)_",
                parse_mode="Markdown",
                reply_markup=InlineKeyboardMarkup([kb_back_step()]))

        if action == "compose":
            self.compose_states[uid] = {"step": "AWAIT_TO", "attachments": []}
            return await query.edit_message_text("✉️ *Compose Email*\n\nEnter the *recipient's email address:*", parse_mode="Markdown", reply_markup=kb_cancel())

        if action == "cancel":
            for fp in (self.compose_states.pop(uid, {}) or {}).get("attachments", []):
                try: os.remove(fp)
                except Exception: pass
            self.compose_states.pop(uid, None)
            self.search_states.pop(uid, None)
            self._clear_history(uid)
            return await query.edit_message_text("🚫 *Canceled.*\n\nReturning to dashboard.", parse_mode="Markdown", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Main Dashboard", callback_data="menu_main")]]))

        if action == "edit_draft_hub":
            return await query.edit_message_text(
                "✏️ *Modify Draft Structure Parameters*\nSelect the attribute component boundary grid to update directly:",
                parse_mode="Markdown",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("👤 Recipient Email Address", callback_data="edit_field_to")],
                    [InlineKeyboardButton("📝 Subject Header Text",     callback_data="edit_field_subj")],
                    [InlineKeyboardButton("✉️ Message Body Content",     callback_data="edit_field_body")],
                    [InlineKeyboardButton("🔙 Back to Draft Preview",   callback_data="restore_draft_view")]
                ])
            )

        if action.startswith("edit_field_"):
            target_field = action.replace("edit_field_", "")
            self.compose_states[uid]["step"] = f"AWAIT_{target_field.upper()}"
            return await query.edit_message_text(f"📝 Input new specifications for *{target_field.upper()}* parameters:", parse_mode="Markdown", reply_markup=kb_cancel())

        if action == "restore_draft_view":
            return await query.edit_message_text(_draft_text(self.compose_states[uid]), parse_mode="Markdown", reply_markup=kb_draft(bool(self.compose_states[uid].get("attachments"))))

        if action == "cancel_voice":
            self.active_voice_tasks.discard(args[0] if args else "")
            return await query.edit_message_text("🚫 *Voice command canceled.*", parse_mode="Markdown", reply_markup=InlineKeyboardMarkup([kb_back_step()]))

        if action == "attach_hint":
            return await query.answer("📎 Upload any file in this chat to attach it!", show_alert=True)

        if action == "clear_att":
            state = self.compose_states.get(uid, {})
            for fp in state.get("attachments", []):
                try: os.remove(fp)
                except Exception: pass
            state["attachments"] = []
            return await query.edit_message_text(_draft_text(state), parse_mode="Markdown", reply_markup=kb_draft(False))

        if action == "send_draft":
            return await self._do_send_draft(query, uid, context)

        if action == "settings":
            prefs = await self._prefs(uid)
            return await query.edit_message_text(
                "⚙️ *Settings*\n\nConfigure your assistant preferences:",
                parse_mode="Markdown",
                reply_markup=kb_settings(
                    prefs.get("ai_mode_enabled", True),
                    prefs.get("voice_preference", "text"),
                    prefs.get("auto_check_enabled", True)))

        if action in ["toggle_ai", "cycle_voice", "toggle_auto"]:
            prefs = await self._prefs(uid)
            if action == "toggle_ai": await self.db.update_user_preferences(uid, {"ai_mode_enabled": not prefs.get("ai_mode_enabled", True)})
            elif action == "toggle_auto": await self.db.update_user_preferences(uid, {"auto_check_enabled": not prefs.get("auto_check_enabled", True)})
            elif action == "cycle_voice":
                cycle = {"text": "voice", "voice": "both", "both": "text"}
                await self.db.update_user_preferences(uid, {"voice_preference": cycle.get(prefs.get("voice_preference", "text"), "text")})
            
            prefs = await self._prefs(uid)
            return await query.edit_message_text(
                "⚙️ *Settings*", parse_mode="Markdown", 
                reply_markup=kb_settings(prefs.get("ai_mode_enabled", True), prefs.get("voice_preference", "text"), prefs.get("auto_check_enabled", True)))

        if action == "logout":
            await self.db.db.run(lambda: self.db.db.client.table("users").update({"auth_token": None}).eq("telegram_id", uid).execute())
            self.gmail.clear_user_attachments(uid)
            self.compose_states.pop(uid, None)
            return await query.edit_message_text("✅ *Logged out.*\nSend /start to reconnect your Google account.", parse_mode="Markdown")

        if len(args) < 3: return
            
        mid_s, ctx, offset = args[0], args[1], int(args[2])

        if action == "read": return await self._show_email(query, mid_s, ctx, offset, uid)
        if action == "sum": return await self._do_summary(query, mid_s, ctx, offset, uid)
        if action == "tts": return await self._do_tts(query, context, mid_s, ctx, offset, uid)
        if action == "att": return await self._do_attachments(query, context, mid_s, ctx, offset, uid)

        if action == "del":
            full_mid = self._full_mid(mid_s)
            res = await self.gmail.delete_email(uid, full_mid)
            if res == "TOKEN_EXPIRED_REAUTH_REQUIRED": return await self._prompt_reauth(query.message, uid)
            if res:
                return await query.edit_message_text(
                    "🗑️ *Email moved to Trash.*",
                    parse_mode="Markdown",
                    reply_markup=InlineKeyboardMarkup([kb_back_step()])
                )

        if action == "untrash":
            res = await self.gmail.untrash_email(uid, self._full_mid(mid_s))
            if res == "TOKEN_EXPIRED_REAUTH_REQUIRED": return await self._prompt_reauth(query.message, uid)
            if res: return await self._show_email(query, mid_s, ctx, offset, uid)

        if action == "reply":
            full_mid = self._full_mid(mid_s)
            meta     = await self.gmail.get_email_metadata(uid, full_mid)
            if meta == "TOKEN_EXPIRED_REAUTH_REQUIRED": return await self._prompt_reauth(query.message, uid)
                
            sender = meta.get("sender", "")
            m      = re.search(r'<(.+?)>', sender)
            email  = m.group(1) if m else sender.strip()
            subj   = meta.get("subject", "")
            
            self.compose_states[uid] = {
                "step":  "AWAIT_BODY",
                "to":    email,
                "subj":  f"Re: {subj}" if not subj.startswith("Re:") else subj,
                "attachments": [],
            }
            return await query.edit_message_text(f"↩️ *Reply to:* `{_safe_md(email)}`\n\n✍️ Type your reply:", parse_mode="Markdown", reply_markup=kb_cancel())

    # ── Isolated Execution Operations ──────────────────────────────────────────

    async def _do_send_draft(self, query, uid: int, context):
        """Immediately dispatches payload. Legacy 7-second undo limits removed for absolute performance."""
        state = self.compose_states.pop(uid, None)
        if not state or not state.get("to") or "[Specify Recipient Email]" in state.get("to", ""):
            return await query.edit_message_text(
                "⚠️ *Validation Error:* Cannot process outbound data streams. Recipient address is invalid.", 
                parse_mode="Markdown", 
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("✉️ Re-evaluate", callback_data="compose")]])
            )

        msg = await query.edit_message_text("⏳ *Sending Email...*", parse_mode="Markdown")

        async def _send_immediately():
            try:
                result = await self.gmail.send_email(
                    uid, state["to"], state.get("subj", "No Subject"), state.get("body", ""),
                    state.get("attachments", [])
                )
                
                if result == "TOKEN_EXPIRED_REAUTH_REQUIRED": return await self._prompt_reauth(msg, uid)
                    
                self._bg(self._save_contact(uid, state["to"]))
                await msg.edit_text(f"✅ *Email Dispatched Successfully!*", parse_mode="Markdown", reply_markup=InlineKeyboardMarkup([kb_back_step()]))
            except Exception as e:
                error_msg = str(e)
                user_friendly_alert = "❌ *Transmission Error:* Form validation checks failed."
                if "Invalid To header" in error_msg: 
                    user_friendly_alert = "⚠️ *Invalid Destination:* The recipient email boundary configuration does not match standard RFC parameters."
                await msg.edit_text(user_friendly_alert, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Fix Parameters", callback_data="compose")]]))
            finally:
                for fp in state.get("attachments", []):
                    if os.path.exists(fp):
                        try: os.remove(fp)
                        except Exception: pass

        asyncio.create_task(_send_immediately())

    async def _do_summary(self, query, mid_short: str, ctx: str, offset: int, uid: int):
        await query.edit_message_text("⏳ *Generating AI Summary...*", parse_mode="Markdown")
        full_mid = self._full_mid(mid_short)
        
        details = await self.gmail.get_email_details(uid, full_mid)
        if details == "TOKEN_EXPIRED_REAUTH_REQUIRED": return await self._prompt_reauth(query.message, uid)
            
        meta = await self.gmail.get_email_metadata(uid, full_mid)
        if meta == "TOKEN_EXPIRED_REAUTH_REQUIRED": return await self._prompt_reauth(query.message, uid)

        body = details.get("body", "") if details else ""
        raw_sum = await self.ai_engine.agent_chat("Summarize this email professionally in 3-4 concise bullet points:\n\n" + body[:3000], uid)

        sum_text = _clean_ai_text(raw_sum)
        if not any(c in sum_text for c in ["•", "-", "*", "1."]):
            lines = [l.strip() for l in sum_text.split("\n") if l.strip()]
            sum_text = "\n".join(f"• {l}" for l in lines[:4])

        sender  = _safe_md(meta.get("sender",  "Unknown"))
        subject = _safe_md(meta.get("subject", "No Subject"))
        att_ct  = len(meta.get("attachments", []))

        text = (
            f"📩 *New Email Summary*\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"👤 *From:* {sender}\n"
            f"📝 *Subject:* {subject}\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"🤖 *AI Summary:*\n\n"
            f"{_safe_md(sum_text)}"
        )
        await query.edit_message_text(text, parse_mode="Markdown", reply_markup=kb_summary(full_mid, ctx, offset, bool(att_ct)))

    async def _do_tts(self, query, context, mid_short: str, ctx: str, offset: int, uid: int):
        await query.edit_message_text("🔊 *Generating audio summary...*", parse_mode="Markdown")
        await context.bot.send_chat_action(chat_id=uid, action=ChatAction.RECORD_VOICE)

        full_mid = self._full_mid(mid_short)
        details = await self.gmail.get_email_details(uid, full_mid)
        if details == "TOKEN_EXPIRED_REAUTH_REQUIRED": return await self._prompt_reauth(query.message, uid)
            
        meta = await self.gmail.get_email_metadata(uid, full_mid)
        if meta == "TOKEN_EXPIRED_REAUTH_REQUIRED": return await self._prompt_reauth(query.message, uid)

        body = details.get("body", "") if details else ""
        raw = await self.ai_engine.agent_chat("In exactly 2-3 sentences, give a spoken summary for text-to-speech:\n\n" + body[:3000], uid)
            
        clean_tts = re.sub(r'[*_#`•]', '', _clean_ai_text(raw))
        prefs = await self._prefs(uid)
        audio = await self.voice.synthesize(clean_tts, telegram_id=uid, preferred_method=prefs.get("preferred_tts_method", "google"))

        sender  = _safe_md(meta.get("sender",  ""))
        subject = _safe_md(meta.get("subject", ""))
        att_ct  = len(meta.get("attachments", []))

        rows = [[InlineKeyboardButton("📖 Read Full Email", callback_data=_cb("read", full_mid[:16], ctx, offset))]]
        if att_ct: rows.append([InlineKeyboardButton("📥 Get Attachments", callback_data=_cb("att", full_mid[:16], ctx, offset))])
        rows.append(kb_back_step())
        
        if audio and os.path.exists(audio):
            with open(audio, "rb") as f:
                await context.bot.send_voice(
                    chat_id=uid, voice=f, 
                    caption=f"🔊 *Audio Summary*\n📧 *From:* {sender}\n📝 *Subject:* {subject}", 
                    parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(rows)
                )
            try:
                os.remove(audio)
                await query.message.delete()
            except Exception: pass
        else:
            await query.edit_message_text("❌ *Audio generation failed.*", parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(rows))

    async def _do_attachments(self, query, context, mid_short: str, ctx: str, offset: int, uid: int):
        await query.edit_message_text("⏳ *Fetching attachments...*", parse_mode="Markdown")
        full_mid = self._full_mid(mid_short)
        back_kb  = InlineKeyboardMarkup([kb_back_step()])

        try:
            meta = await self.gmail.get_email_metadata(uid, full_mid)
            if meta == "TOKEN_EXPIRED_REAUTH_REQUIRED": return await self._prompt_reauth(query.message, uid)
            if len(meta.get("attachments", [])) > 10:
                return await query.edit_message_text("⚠️ *Download Blocked:* Max 10 files allowed.", parse_mode="Markdown", reply_markup=back_kb)
        except Exception: pass

        paths = await self.gmail.get_attachments(uid, full_mid)
        if paths == "TOKEN_EXPIRED_REAUTH_REQUIRED": return await self._prompt_reauth(query.message, uid)

        if not paths: 
            return await query.edit_message_text("📭 *No downloadable attachments found.*", parse_mode="Markdown", reply_markup=back_kb)

        await query.edit_message_text(f"📤 *Sending {len(paths)} attachment(s)...*", parse_mode="Markdown")
        sent = 0
        for fp in paths:
            try:
                with open(fp, "rb") as f:
                    await context.bot.send_document(chat_id=uid, document=f)
                sent += 1
            except Exception as e: logger.error(f"Attachment send error: {e}")
            finally:
                try: os.remove(fp)
                except Exception: pass

        await query.edit_message_text(f"✅ *{sent}/{len(paths)} file(s) sent.*", parse_mode="Markdown", reply_markup=back_kb)

    # ── Advanced Background Crons ──────────────────────────────────────────────

    async def job_ping(self, context: ContextTypes.DEFAULT_TYPE):
        import httpx
        try:
            async with httpx.AsyncClient(timeout=10) as c: await c.get(f"{settings.RENDER_WEB_SERVICE_URL}/health")
        except Exception: pass

    async def job_emails(self, context: ContextTypes.DEFAULT_TYPE):
        """Scans unread streams checking startup temporal states. Implements minimal load loops."""
        async with self.email_lock:
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
                            
                        if not isinstance(emails, list): continue

                        for email_item in emails:
                            mid = email_item["id"]
                            
                            # COLD START FILTER: Skip any email received before bot initialization
                            internal_dt = email_item.get("internal_date", 0)
                            if (internal_dt / 1000) < self.startup_time:
                                continue

                            if mid in self.notified_emails: continue
                            self.notified_emails.add(mid)
                            self._store_mid(mid)

                            meta = await self.gmail.get_email_metadata(uid, mid)
                            if meta == "TOKEN_EXPIRED_REAUTH_REQUIRED" or "error" in meta: continue

                            sender   = _safe_md(meta.get("sender",  "Unknown"))
                            subject  = _safe_md(meta.get("subject", "No Subject"))
                            att_ct   = len(meta.get("attachments", []))
                            att_line = f"\n📎 *{att_ct} Attachment(s) Found*" if att_ct else ""

                            text = (
                                f"📩 *New Email Received*\n"
                                f"━━━━━━━━━━━━━━━━━━\n"
                                f"👤 *From:* {sender}\n"
                                f"📝 *Subject:* {subject}{att_line}"
                            )

                            try:
                                await self.db.db.run(lambda u=uid, m=mid, s=meta.get("sender", ""), sub=meta.get("subject", ""): self.db.db.client.table("email_cache").upsert({"telegram_id": u, "gmail_message_id": m, "sender": s, "subject": sub, "preview": "new"}, on_conflict="telegram_id,gmail_message_id").execute())
                            except Exception: pass

                            await context.bot.send_message(chat_id=uid, text=text, parse_mode="Markdown", reply_markup=kb_notification(mid, bool(att_ct)))
                    break 
                except Exception as e:
                    logger.error(f"job_emails connection error (attempt {attempt + 1}/{max_retries}): {e}")
                    if attempt < max_retries - 1: await asyncio.sleep(3 ** attempt)

    async def job_scheduled(self, context: ContextTypes.DEFAULT_TYPE):
        max_retries = 3
        for attempt in range(max_retries):
            try:
                now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
                res = await self.db.db.run(lambda: self.db.db.client.table("scheduled_emails").select("*").eq("status", "pending").lte("scheduled_time", now).execute())
                
                for task in (getattr(res, "data", []) or []):
                    uid   = task["telegram_id"]
                    paths = []
                    try:
                        for att in (task.get("attachments") or []):
                            if isinstance(att, dict) and "file_id" in att:
                                try:
                                    fo   = await context.bot.get_file(att["file_id"])
                                    path = os.path.join(tempfile.gettempdir(), att.get("file_name", f"att_{uuid.uuid4().hex[:6]}"))
                                    await fo.download_to_drive(path)
                                    paths.append(path)
                                except Exception: pass

                        result = await self.gmail.send_email(uid, task["to_email"], task["subject"], task["body"], paths)
                            
                        if result == "TOKEN_EXPIRED_REAUTH_REQUIRED":
                            await self._send_reauth_direct(context, uid)
                            await self.db.db.run(lambda t=task: self.db.db.client.table("scheduled_emails").update({"status": "failed"}).eq("id", t["id"]).execute())
                            continue
                            
                        status = "sent" if "successfully" in result.lower() else "failed"
                        await self.db.db.run(lambda t=task, s=status: self.db.db.client.table("scheduled_emails").update({"status": s}).eq("id", t["id"]).execute())

                        note = (f"✅ *Scheduled Email Sent!*\n*To:* `{_safe_md(task['to_email'])}`" if status == "sent" else f"❌ *Scheduled Email Failed*\n{_safe_md(result)}")
                        await context.bot.send_message(chat_id=uid, text=note, parse_mode="Markdown")
                    finally:
                        for fp in paths:
                            if os.path.exists(fp):
                                try: os.remove(fp)
                                except Exception as e: logger.error(f"Failed cleaning up scheduled attachment {fp}: {e}")
                break 
            except Exception as e:
                logger.error(f"job_scheduled connection error (attempt {attempt + 1}/{max_retries}): {e}")
                if attempt < max_retries - 1: await asyncio.sleep(3 ** attempt) 

# ── Singleton ──────────────────────────────────────────────────────────────────
telegram_handler = TelegramBotManager()