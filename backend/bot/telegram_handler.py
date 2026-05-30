"""
Telegram Bot Handler — Smart Email Assistant
============================================
Production-ready. All known bugs fixed:
- run_lambda crash removed → uses await self.db.db.run()
- Smart replies completely purged from all handlers
- Premium structured notification format
- AI response JSON never leaks raw to user
- Clean overlay deletion on TTS completion
- Multi-attachment staging with clear-attachments
- Full sender/subject everywhere, no truncation
- HITL draft loop: [Specify Recipient] placeholder catches missing address
- No orphaned sr: callback actions
- Attachment button conditional in all views
- Back from notification goes inbox:0
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

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.constants import ChatAction
from telegram.ext import (
    ApplicationBuilder, CommandHandler, MessageHandler,
    CallbackQueryHandler, filters, ContextTypes, Application
)

from config import settings
from db.models import db_manager
from db.memory import memory_manager
from bot.ai_engine import AIEngine
from bot.gmail_client import GmailClient
from bot.voice_handler import voice_handler
from bot.contact_manager import contact_manager

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


# ── Callback helpers ───────────────────────────────────────────────────────────
def _cb(action: str, *args) -> str:
    data = ":".join([action] + [str(a) for a in args])
    if len(data) > 64:
        parts = data.split(":")
        if len(parts) >= 2:
            parts[1] = parts[1][:16]
            data = ":".join(parts)
    return data[:64]

def _parse_cb(data: str) -> tuple:
    parts = data.split(":")
    return parts[0], parts[1:]

def _clean_ai_text(raw: str) -> str:
    """Extract clean text from AI response — never leaks raw JSON to user."""
    if not raw:
        return ""
    cleaned = re.sub(r'```json|```', '', raw).strip()
    # Try JSON parse first
    m = re.search(r'\{.*\}', cleaned, re.DOTALL)
    if m:
        try:
            parsed = json.loads(m.group(0))
            text = parsed.get("text", "")
            if text:
                return str(text).strip()
        except Exception:
            pass
    # If it looks like JSON but unparseable, strip the braces/quotes
    if cleaned.startswith("{") and "text" in cleaned:
        t = re.search(r'"text"\s*:\s*"(.*?)"(?:,|\})', cleaned, re.DOTALL)
        if t:
            return t.group(1).replace("\\n", "\n").strip()
    return raw.strip()

def _safe_md(text: str) -> str:
    """Escapes Telegram Markdown special characters strictly to prevent layout crashes."""
    if not text: 
        return ""
    escape_chars = r"_*[]()~`>#+-=|{}.!"
    return "".join(f"\\{c}" if c in escape_chars else c for c in text)


# ── Keyboard builders (no smart replies anywhere) ──────────────────────────────

def kb_main_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📥 Inbox",         callback_data=_cb("inbox", 0)),
         InlineKeyboardButton("✍️ Compose",        callback_data="compose")],
        [InlineKeyboardButton("🔍 Search Emails", callback_data="search_prompt"),
         InlineKeyboardButton("⚙️ Settings",       callback_data="settings")],
    ])

def kb_back(ctx: str = "main", offset: int = 0) -> list:
    if ctx == "inbox":
        return [InlineKeyboardButton("🔙 Back to Inbox",   callback_data=_cb("inbox", offset))]
    if ctx == "search":
        return [InlineKeyboardButton("🔙 Back to Results", callback_data=_cb("srpage", offset))]
    return [InlineKeyboardButton("🔙 Main Menu",            callback_data="menu_main")]

def kb_cancel() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[InlineKeyboardButton("❌ Cancel", callback_data="cancel")]])

def kb_email_list(msgs: list, offset: int, is_search: bool, has_next: bool) -> InlineKeyboardMarkup:
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
    rows.append(kb_back())
    return InlineKeyboardMarkup(rows)

def kb_email_view(msg_id: str, ctx: str, offset: int, has_att: bool) -> InlineKeyboardMarkup:
    mid = msg_id[:16]
    rows = [
        [InlineKeyboardButton("↩️ Reply",      callback_data=_cb("reply", mid, ctx, offset)),
         InlineKeyboardButton("🗑️ Trash",       callback_data=_cb("del",   mid, ctx, offset))],
        [InlineKeyboardButton("🤖 AI Summary", callback_data=_cb("sum",   mid, ctx, offset)),
         InlineKeyboardButton("🔊 Listen",      callback_data=_cb("tts",   mid, ctx, offset))],
    ]
    if has_att:
        rows.append([InlineKeyboardButton("📥 Get Attachments", callback_data=_cb("att", mid, ctx, offset))])
    rows.append(kb_back(ctx, offset))
    return InlineKeyboardMarkup(rows)

def kb_summary(msg_id: str, ctx: str, offset: int, has_att: bool) -> InlineKeyboardMarkup:
    """Summary view — NO smart replies. Core actions only."""
    mid = msg_id[:16]
    rows = [
        [InlineKeyboardButton("📖 Read Full Email", callback_data=_cb("read", mid, ctx, offset)),
         InlineKeyboardButton("🔊 Listen",           callback_data=_cb("tts",  mid, ctx, offset))],
    ]
    if has_att:
        rows.append([InlineKeyboardButton("📥 Get Attachments", callback_data=_cb("att", mid, ctx, offset))])
    rows.append([InlineKeyboardButton("↩️ Reply to Email", callback_data=_cb("reply", mid, ctx, offset))])
    rows.append(kb_back(ctx, offset))
    return InlineKeyboardMarkup(rows)

def kb_notification(msg_id: str, has_att: bool) -> InlineKeyboardMarkup:
    """Push notification — Read, AI Summary, Listen, Get Attachments (conditional)."""
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
    rows = [
        [InlineKeyboardButton("🚀 Send Now",       callback_data="send_draft"),
         InlineKeyboardButton("❌ Cancel",          callback_data="cancel")],
        [InlineKeyboardButton("📎 Add Attachment", callback_data="attach_hint")],
    ]
    if has_files:
        rows.append([InlineKeyboardButton("🗑️ Clear Attachments", callback_data="clear_att")])
    return InlineKeyboardMarkup(rows)

def kb_settings(ai_on: bool, voice: str, auto_on: bool) -> InlineKeyboardMarkup:
    v_map = {"text": "📝 Text Only", "voice": "🔊 Voice Only", "both": "📝+🔊 Both"}
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(f"{'✅' if ai_on   else '❌'} AI Mode",          callback_data="toggle_ai")],
        [InlineKeyboardButton(v_map.get(voice, "📝 Text Only"),                callback_data="cycle_voice")],
        [InlineKeyboardButton(f"{'✅' if auto_on else '❌'} Auto Email Check", callback_data="toggle_auto")],
        [InlineKeyboardButton("🚪 Logout Account",                             callback_data="logout")],
        kb_back(),
    ])

def _draft_text(state: dict) -> str:
    files   = state.get("attachments", [])
    att_ln  = f"\n📎 *{len(files)} attachment(s) staged*" if files else ""
    return (
        f"📄 *Draft Preview*\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"👤 *To:* `{state.get('to', '—')}`\n"
        f"📝 *Subject:* `{state.get('subj', '—')}`\n"
        f"✉️ *Body:*\n_{state.get('body', '—')}_"
        f"{att_ln}\n\n"
        f"Upload files to attach, then tap *Send Now*."
    )


# ── Bot Manager ────────────────────────────────────────────────────────────────

class TelegramBotManager:
    def __init__(self):
        self.application: Application | None = None
        self.ai_engine       = AIEngine()
        self.db              = db_manager
        self.memory          = memory_manager
        self.gmail           = GmailClient()
        self.voice           = voice_handler
        self.contacts        = contact_manager

        self.compose_states:    dict = {}   # uid -> {step, to, subj, body, attachments}
        self.search_states:     dict = {}   # uid -> 'AWAIT_QUERY'
        self.current_queries:   dict = {}   # uid -> last search query string
        self.pending_sends:     dict = {}   # uid -> draft dict (undo window)
        self._mid_cache:        dict = {}   # short_id[:16] -> full Gmail message ID
        self.notified_emails:    set = set()
        self.active_voice_tasks: set = set()
        self.email_lock = asyncio.Lock()

    # ── Internals ──────────────────────────────────────────────────────────────

    def _full_mid(self, short: str) -> str:
        return self._mid_cache.get(short, short)

    def _store_mid(self, full_id: str):
        self._mid_cache[full_id[:16]] = full_id

    def _bg(self, coro):
        asyncio.create_task(coro)

    async def _prefs(self, uid: int) -> dict:
        try:
            return await self.db.get_user_preferences(uid) or {}
        except Exception:
            return {}

    async def _send(self, update: Update, text: str,
                    markup: InlineKeyboardMarkup | None = None,
                    parse_mode: str = "Markdown"):
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
            logger.debug(f"_send: {e}")

    async def _edit(self, obj, text: str,
                    markup: InlineKeyboardMarkup | None = None,
                    parse_mode: str = "Markdown"):
        try:
            if hasattr(obj, "edit_text"):
                await obj.edit_text(text, parse_mode=parse_mode, reply_markup=markup,
                                    disable_web_page_preview=True)
            else:
                await obj.reply_text(text, parse_mode=parse_mode, reply_markup=markup,
                                     disable_web_page_preview=True)
        except Exception as e:
            logger.debug(f"_edit: {e}")

    # ── Access gate ────────────────────────────────────────────────────────────

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
        self.application = ApplicationBuilder().token(settings.BOT_TOKEN).build()
        self.application.add_handler(CommandHandler("start", self.cmd_start))
        self.application.add_handler(CommandHandler("menu",  self.cmd_menu))
        self.application.add_handler(CallbackQueryHandler(self.handle_button))
        self.application.add_handler(MessageHandler(
            filters.TEXT & ~filters.COMMAND, self.handle_text))
        self.application.add_handler(MessageHandler(filters.VOICE, self.handle_voice))
        self.application.add_handler(MessageHandler(
            filters.Document.ALL | filters.PHOTO | filters.AUDIO | filters.VIDEO,
            self.handle_attachment))
        await self.application.initialize()
        
        if self.application.job_queue:
            self.application.job_queue.run_repeating(self.job_emails,    interval=60,  first=15)
            self.application.job_queue.run_repeating(self.job_scheduled, interval=60,  first=30)
            self.application.job_queue.run_repeating(self.job_ping,      interval=840, first=60)
            
        # Auto-adapt runtime environments layer toggle (Dev vs Production safety)
        if settings.RENDER_WEB_SERVICE_URL and not settings.RENDER_WEB_SERVICE_URL.startswith("http://localhost"):
            await self.application.bot.set_webhook(
                url=f"{settings.RENDER_WEB_SERVICE_URL}/webhook/telegram")
            logger.info("✅ Bot production webhook live.")
        else:
            logger.info("⚠️ Local development cluster context detected. Skipping global webhook binding hook.")
            
        await self.application.start()

    async def process_webhook(self, data: dict):
        if self.application:
            update = Update.de_json(data, self.application.bot)
            await self.application.process_update(update)

    # ── Commands ───────────────────────────────────────────────────────────────

    async def cmd_start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Only /start gets the welcome message. menu_main callback gets clean dashboard."""
        u   = update.effective_user
        acc = await self._check_access(u.id, u.first_name or "", u.username or "")
        if await self._gate(update, u.id, acc["status"]):
            return
        await self._send(update,
            f"👋 *Welcome, {u.first_name}!*\n\n"
            "I'm your AI Email Assistant. Use the buttons below to manage your Gmail "
            "with text or voice commands.",
            kb_main_menu())

    async def cmd_menu(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        u   = update.effective_user
        acc = await self._check_access(u.id, u.first_name or "", u.username or "")
        if await self._gate(update, u.id, acc["status"]):
            return
        await self._send(update, "🎛️ *Main Dashboard*\n\nSelect an action:", kb_main_menu())

    # ── Email list ─────────────────────────────────────────────────────────────

    async def _show_list(self, msg_obj, uid: int, offset: int, is_search: bool):
        query = self.current_queries.get(uid, "is:unread") if is_search else "label:INBOX"
        try:
            messages = await self.gmail.get_emails(uid, query=query, max_results=offset + 3)
        except Exception:
            messages = []

        if not messages and offset == 0:
            lbl = f"📭 No results for: `{query}`" if is_search else "📭 Your inbox is empty."
            await self._edit(msg_obj, lbl, InlineKeyboardMarkup([kb_back()]))
            return

        display  = messages[offset:offset + 2]
        has_next = len(messages) > offset + 2
        header   = f"🔍 *Results:* `{query}`\n\n" if is_search else "📥 *Your Inbox*\n\n"
        lines    = [header]

        for i, m in enumerate(display):
            self._store_mid(m["id"])
            meta    = await self.gmail.get_email_metadata(uid, m["id"])
            if "error" in meta:
                continue
            sender  = meta.get("sender",  "Unknown").replace("*","").replace("_","")
            subject = meta.get("subject", "No Subject").replace("*","").replace("_","")
            lines.append(f"*{offset + i + 1}.* {sender}\n   _{subject}_\n")

        await self._edit(msg_obj, "\n".join(lines),
                         kb_email_list(display, offset, is_search, has_next))

    # ── Full email render ──────────────────────────────────────────────────────

    async def _show_email(self, query, mid_short: str, ctx: str, offset: int, uid: int):
        await query.edit_message_text("⏳ Loading email...")
        full_mid = self._full_mid(mid_short)
        body     = await self.gmail.read_full_email(uid, full_mid)
        meta     = await self.gmail.get_email_metadata(uid, full_mid)
        self._store_mid(meta.get("id", full_mid))

        def _esc(s: str) -> str:
            return s.replace("&","&amp;").replace("<","&lt;").replace(">","&gt;")

        safe_body    = _esc(body[:4000] + ("\n\n[… Truncated]" if len(body) > 4000 else ""))
        safe_sender  = _esc(meta.get("sender",  "Unknown"))
        safe_subject = _esc(meta.get("subject", "No Subject"))

        safe_body = re.sub(r'(https?://[^\s<>"]+)',
                           r'<a href="\1">🔗 Link</a>', safe_body)

        att_list = meta.get("attachments", [])
        att_line = f"\n📎 <b>{len(att_list)} Attachment(s)</b>" if att_list else ""

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

    # ── Text handler ───────────────────────────────────────────────────────────

    async def handle_text(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        u   = update.effective_user
        acc = await self._check_access(u.id, u.first_name or "", u.username or "")
        if await self._gate(update, u.id, acc["status"]):
            return
        uid  = u.id
        text = update.message.text

        if uid in self.compose_states:
            await self._compose_step(update, uid, text)
            return

        if self.search_states.get(uid) == "AWAIT_QUERY":
            self.search_states.pop(uid)
            self.current_queries[uid] = text
            wait = await update.message.reply_text(f"🔍 Searching `{text}`...")
            found = await self.contacts.find_contacts_by_name(uid, text)
            if found:
                extra = " OR ".join(f"from:{c['email_address']}" for c in found)
                self.current_queries[uid] = f"({extra}) OR {text}"
            await self._show_list(wait, uid, offset=0, is_search=True)
            return

        if not acc["user"].get("ai_allowed", True):
            await update.message.reply_text("🚫 *AI access restricted* for your account.",
                                             parse_mode="Markdown")
            return

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
                await update.message.reply_text(
                    _draft_text(state), parse_mode="Markdown",
                    reply_markup=kb_draft(bool(state.get("attachments"))))
            else:
                state["step"] = "AWAIT_SUBJ"
                await update.message.reply_text(
                    f"✅ *To:* `{text}`\n\n📝 *Enter Subject:*",
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

        msg = await update.message.reply_text("🎙️ *Processing voice note...*", parse_mode="Markdown")
        fp  = os.path.join(tempfile.gettempdir(), f"voice_{uuid.uuid4().hex}.ogg")
        try:
            vf = await context.bot.get_file(update.message.voice.file_id)
            await vf.download_to_drive(fp)
            transcribed = await self.ai_engine.transcribe_audio(fp, u.id)
        finally:
            if os.path.exists(fp):
                os.remove(fp)

        if "[Audio Unclear]" in transcribed or transcribed.startswith("System Error"):
            await msg.edit_text("❌ *Audio unclear.* Please try again.", parse_mode="Markdown")
            return

        uid = u.id

        # Route voice to compose body if waiting
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
            f"🗣️ *Heard:* _{transcribed}_\n\n✨ *Processing...*",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("❌ Cancel", callback_data=f"cancel_voice:{task_id}")
            ]]))

        raw = await self.ai_engine.agent_chat(transcribed, uid)
        if task_id not in self.active_voice_tasks:
            return
        self.active_voice_tasks.discard(task_id)
        await self._dispatch_ai(update, context, msg, raw, uid, await self._prefs(uid))

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

        if getattr(att, "file_size", 0) > 20 * 1024 * 1024:
            await update.message.reply_text("❌ *File too large* (max 20 MB).", parse_mode="Markdown")
            return

        uid   = u.id
        ext   = (getattr(att, "file_name", "file") or "file").rsplit(".", 1)[-1]
        fname = getattr(att, "file_name", f"file_{uuid.uuid4().hex[:6]}.{ext}")
        fpath = os.path.join(tempfile.gettempdir(), f"att_{uuid.uuid4().hex}.{ext}")
        msg   = await update.message.reply_text("📥 *Downloading...*", parse_mode="Markdown")

        try:
            fo = await context.bot.get_file(att.file_id)
            await fo.download_to_drive(fpath)
        except Exception:
            await msg.edit_text("❌ *Download failed.*", parse_mode="Markdown")
            return

        if uid in self.compose_states:
            state = self.compose_states[uid]
            state.setdefault("attachments", []).append(fpath)
            state["step"] = "AWAIT_ATT"
            await msg.edit_text(
                _draft_text(state), parse_mode="Markdown",
                reply_markup=kb_draft(True))
            return

        self.gmail.add_user_attachment(uid, fpath)
        caption = update.message.caption or ""
        if caption:
            raw = await self.ai_engine.agent_chat(f"[Uploaded: {fname}] {caption}", uid)
            await self._dispatch_ai(update, context, msg, raw, uid, await self._prefs(uid))
        else:
            await msg.edit_text(
                f"✅ *Saved:* `{fname}`\nTell me what to do with it or compose an email.",
                parse_mode="Markdown",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("✉️ Compose Email", callback_data="compose")],
                    kb_back(),
                ]))

    # ── AI response dispatcher ─────────────────────────────────────────────────

    async def _dispatch_ai(self, update, context, msg_obj,
                            raw: str, uid: int, prefs: dict):
        """
        Parses AI output. Never leaks raw JSON. Handles HITL draft injection.
        [Specify Recipient] placeholder caught and compose flow triggered.
        """
        text_content = _clean_ai_text(raw)
        draft_data   = None

        # Try full JSON parse for draft field
        try:
            cleaned = re.sub(r'```json|```', '', raw).strip()
            m       = re.search(r'\{.*\}', cleaned, re.DOTALL)
            if m:
                parsed     = json.loads(m.group(0))
                text_content = _clean_ai_text(raw)
                draft_data   = parsed.get("draft")
        except Exception:
            pass

        # Also check pending_drafts from ai_engine
        if uid in self.ai_engine.pending_drafts:
            draft_data = self.ai_engine.pending_drafts.pop(uid)

        # HITL draft injection
        if draft_data:
            to_field = (draft_data.get("to") or "").strip()
            if not to_field or "[Specify Recipient]" in to_field:
                self.compose_states[uid] = {
                    "step": "AWAIT_TO",
                    "subj": draft_data.get("subject", ""),
                    "body": draft_data.get("body", ""),
                    "attachments": [],
                }
                await self._edit(msg_obj,
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
                await self._edit(msg_obj, _draft_text(self.compose_states[uid]), kb_draft())
            return

        # Voice output
        voice_pref = prefs.get("voice_preference", "text")
        try:
            parsed_full = json.loads(re.sub(r'```json|```', '', raw).strip())
            is_voice_type = parsed_full.get("response_type") == "voice"
        except Exception:
            is_voice_type = False

        if is_voice_type and voice_pref in ("voice", "both"):
            await context.bot.send_chat_action(chat_id=uid, action=ChatAction.RECORD_VOICE)
            clean_tts = re.sub(r'[*_#`]', '', text_content)
            audio     = await self.voice.synthesize(
                clean_tts, telegram_id=uid,
                preferred_method=prefs.get("preferred_tts_method", "google"))
            if audio and os.path.exists(audio):
                with open(audio, "rb") as f:
                    if voice_pref == "both":
                        await self._edit(msg_obj, f"🤖 {text_content}",
                                          InlineKeyboardMarkup([kb_back()]))
                        await context.bot.send_voice(
                            chat_id=uid, voice=f,
                            reply_markup=InlineKeyboardMarkup([kb_back()]))
                    else:
                        await context.bot.send_voice(
                            chat_id=uid, voice=f, caption="🔊 AI Response",
                            reply_markup=InlineKeyboardMarkup([kb_back()]))
                        try:
                            await msg_obj.delete()
                        except Exception:
                            pass
                try:
                    os.remove(audio)
                except Exception:
                    pass
                return

        await self._edit(msg_obj, f"🤖 {text_content}",
                          InlineKeyboardMarkup([kb_back()]))

    # ── Button handler ─────────────────────────────────────────────────────────

    async def handle_button(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        query  = update.callback_query
        uid    = query.from_user.id
        data   = query.data
        try:
            await query.answer()
        except Exception:
            pass

        action, args = _parse_cb(data)

        # ── Static actions ─────────────────────────────────────────────────────

        if action == "menu_main":
            # Clean dashboard — no welcome text, just the action grid
            self.compose_states.pop(uid, None)
            self.search_states.pop(uid, None)
            await self._send(update, "🎛️ *Main Dashboard*\n\nSelect an action:", kb_main_menu())
            return

        if action == "inbox":
            offset = int(args[0]) if args else 0
            await self._show_list(query.message, uid, offset, is_search=False)
            return

        if action == "srpage":
            offset = int(args[0]) if args else 0
            await self._show_list(query.message, uid, offset, is_search=True)
            return

        if action == "search_prompt":
            self.search_states[uid] = "AWAIT_QUERY"
            await query.edit_message_text(
                "🔍 *Search Emails*\n\n"
                "Type your Gmail query below:\n"
                "_(e.g. `from:john`, `invoice`, `is:unread`, `subject:meeting`)_",
                parse_mode="Markdown",
                reply_markup=InlineKeyboardMarkup([kb_back()]))
            return

        if action == "compose":
            self.compose_states[uid] = {"step": "AWAIT_TO", "attachments": []}
            await query.edit_message_text(
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
            self.pending_sends.pop(uid, None)
            await query.edit_message_text(
                "🚫 *Canceled.*\n\nReturning to dashboard.",
                parse_mode="Markdown",
                reply_markup=InlineKeyboardMarkup([kb_back()]))
            return

        if action == "cancel_voice":
            self.active_voice_tasks.discard(args[0] if args else "")
            await query.edit_message_text("🚫 *Voice command canceled.*", parse_mode="Markdown",
                reply_markup=InlineKeyboardMarkup([kb_back()]))
            return

        if action == "attach_hint":
            await query.answer("📎 Upload any file in this chat to attach it!", show_alert=True)
            return

        if action == "clear_att":
            state = self.compose_states.get(uid, {})
            for fp in state.get("attachments", []):
                try:
                    os.remove(fp)
                except Exception:
                    pass
            state["attachments"] = []
            await query.edit_message_text(
                _draft_text(state), parse_mode="Markdown",
                reply_markup=kb_draft(False))
            return

        if action == "send_draft":
            await self._do_send_draft(query, uid, context)
            return

        if action == "undo_send":
            self.pending_sends.pop(uid, None)
            await query.edit_message_text(
                "✅ *Send canceled.* The email was not sent.",
                parse_mode="Markdown",
                reply_markup=InlineKeyboardMarkup([kb_back()]))
            return

        # ── Settings ──────────────────────────────────────────────────────────

        if action == "settings":
            prefs = await self._prefs(uid)
            await query.edit_message_text(
                "⚙️ *Settings*\n\nConfigure your assistant preferences:",
                parse_mode="Markdown",
                reply_markup=kb_settings(
                    prefs.get("ai_mode_enabled", True),
                    prefs.get("voice_preference", "text"),
                    prefs.get("auto_check_enabled", True)))
            return

        if action == "toggle_ai":
            prefs   = await self._prefs(uid)
            new_val = not prefs.get("ai_mode_enabled", True)
            await self.db.update_user_preferences(uid, {"ai_mode_enabled": new_val})
            prefs = await self._prefs(uid)
            await query.edit_message_text("⚙️ *Settings*", parse_mode="Markdown",
                reply_markup=kb_settings(prefs.get("ai_mode_enabled", True),
                    prefs.get("voice_preference", "text"), prefs.get("auto_check_enabled", True)))
            return

        if action == "cycle_voice":
            prefs   = await self._prefs(uid)
            cycle   = {"text": "voice", "voice": "both", "both": "text"}
            new_val = cycle.get(prefs.get("voice_preference", "text"), "text")
            await self.db.update_user_preferences(uid, {"voice_preference": new_val})
            prefs = await self._prefs(uid)
            await query.edit_message_text("⚙️ *Settings*", parse_mode="Markdown",
                reply_markup=kb_settings(prefs.get("ai_mode_enabled", True),
                    prefs.get("voice_preference", "text"), prefs.get("auto_check_enabled", True)))
            return

        if action == "toggle_auto":
            prefs   = await self._prefs(uid)
            new_val = not prefs.get("auto_check_enabled", True)
            await self.db.update_user_preferences(uid, {"auto_check_enabled": new_val})
            prefs = await self._prefs(uid)
            await query.edit_message_text("⚙️ *Settings*", parse_mode="Markdown",
                reply_markup=kb_settings(prefs.get("ai_mode_enabled", True),
                    prefs.get("voice_preference", "text"), prefs.get("auto_check_enabled", True)))
            return

        if action == "logout":
            await self.db.db.run(lambda: self.db.db.client.table("users")
                                  .update({"auth_token": None})
                                  .eq("telegram_id", uid).execute())
            self.gmail.clear_user_attachments(uid)
            self.compose_states.pop(uid, None)
            await query.edit_message_text(
                "✅ *Logged out.*\nSend /start to reconnect your Google account.",
                parse_mode="Markdown")
            return

        # ── Parameterized email actions: action:mid_short:ctx:offset ──────────

        if action == "read":
            if len(args) < 3:
                return
            mid_s, ctx, offset = args[0], args[1], int(args[2])
            await self._show_email(query, mid_s, ctx, offset, uid)
            return

        if action == "sum":
            if len(args) < 3:
                return
            mid_s, ctx, offset = args[0], args[1], int(args[2])
            await self._do_summary(query, mid_s, ctx, offset, uid)
            return

        if action == "tts":
            if len(args) < 3:
                return
            mid_s, ctx, offset = args[0], args[1], int(args[2])
            await self._do_tts(query, context, mid_s, ctx, offset, uid)
            return

        if action == "att":
            if len(args) < 3:
                return
            mid_s, ctx, offset = args[0], args[1], int(args[2])
            await self._do_attachments(query, context, mid_s, ctx, offset, uid)
            return

        if action == "del":
            if len(args) < 3:
                return
            mid_s, ctx, offset = args[0], args[1], int(args[2])
            full_mid = self._full_mid(mid_s)
            if await self.gmail.delete_email(uid, full_mid):
                await query.edit_message_text(
                    "🗑️ *Email moved to Trash.*",
                    parse_mode="Markdown",
                    reply_markup=InlineKeyboardMarkup([
                        [InlineKeyboardButton("↩️ Undo",
                            callback_data=_cb("untrash", mid_s, ctx, offset))],
                        kb_back(ctx, offset),
                    ]))
            return

        if action == "untrash":
            if len(args) < 3:
                return
            mid_s, ctx, offset = args[0], args[1], int(args[2])
            if await self.gmail.untrash_email(uid, self._full_mid(mid_s)):
                await self._show_email(query, mid_s, ctx, offset, uid)
            return

        if action == "reply":
            if len(args) < 3:
                return
            mid_s, ctx, offset = args[0], args[1], int(args[2])
            full_mid = self._full_mid(mid_s)
            meta     = await self.gmail.get_email_metadata(uid, full_mid)
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
            await query.edit_message_text(
                f"↩️ *Reply to:* `{email}`\n\n✍️ Type your reply:",
                parse_mode="Markdown", reply_markup=kb_cancel())
            return

    # ── Email action sub-handlers ──────────────────────────────────────────────

    async def _do_send_draft(self, query, uid: int, context):
        state = self.compose_states.pop(uid, None)
        if not state or not state.get("to"):
            await query.edit_message_text("❌ *Draft expired.* Start a new compose.",
                parse_mode="Markdown",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton(
                    "✉️ Compose", callback_data="compose")]]))
            return

        self.pending_sends[uid] = state
        msg = await query.edit_message_text(
            "⏳ *Sending in 7 seconds...*\n_(tap Undo to cancel)_",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("↩️ Undo Send", callback_data="undo_send")],
                kb_back(),
            ]))

        async def _send():
            await asyncio.sleep(7)
            if uid not in self.pending_sends:
                return
            draft  = self.pending_sends.pop(uid)
            result = await self.gmail.send_email(
                uid, draft["to"], draft["subj"], draft.get("body", ""),
                draft.get("attachments", []))
            self._bg(self._save_contact(uid, draft["to"]))
            icon = "✅" if "successfully" in result.lower() else "❌"
            try:
                await msg.edit_text(
                    f"{icon} {result}", parse_mode="Markdown",
                    reply_markup=InlineKeyboardMarkup([kb_back()]))
            except Exception:
                pass

        asyncio.create_task(_send())

    async def _do_summary(self, query, mid_short: str,
                           ctx: str, offset: int, uid: int):
        """
        Generates structured AI summary.
        NO smart replies. Clean professional layout.
        Raw JSON is never exposed.
        """
        await query.edit_message_text("⏳ *Generating AI Summary...*", parse_mode="Markdown")
        full_mid = self._full_mid(mid_short)
        body     = await self.gmail.read_full_email(uid, full_mid)
        meta     = await self.gmail.get_email_metadata(uid, full_mid)

        raw_sum = await self.ai_engine.agent_chat(
            "Summarize this email professionally in 3-4 concise bullet points. "
            "Be direct. Use • symbol for each bullet:\n\n" + body[:3000], uid)

        sum_text = _clean_ai_text(raw_sum)

        # Ensure bullet format if AI didn't add bullets
        if not any(c in sum_text for c in ["•", "-", "*", "1."]):
            lines    = [l.strip() for l in sum_text.split("\n") if l.strip()]
            sum_text = "\n".join(f"• {l}" for l in lines[:4])

        sender  = meta.get("sender",  "Unknown").replace("*","").replace("_","")
        subject = meta.get("subject", "No Subject").replace("*","").replace("_","")
        att_ct  = len(meta.get("attachments", []))

        # Premium structured layout
        text = (
            f"📩 *New Email Summary*\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"👤 *From:* {sender}\n"
            f"📝 *Subject:* {subject}\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"🤖 *AI Summary:*\n\n"
            f"{sum_text}"
        )

        await query.edit_message_text(
            text, parse_mode="Markdown",
            reply_markup=kb_summary(full_mid, ctx, offset, bool(att_ct)))

    async def _do_tts(self, query, context, mid_short: str,
                       ctx: str, offset: int, uid: int):
        """
        Synthesizes voice summary.
        Overlay ('Generating...') deleted immediately after audio is sent.
        Caption includes full From and Subject.
        """
        await query.edit_message_text("🔊 *Generating audio summary...*", parse_mode="Markdown")
        await context.bot.send_chat_action(chat_id=uid, action=ChatAction.RECORD_VOICE)

        full_mid = self._full_mid(mid_short)
        body     = await self.gmail.read_full_email(uid, full_mid)
        meta     = await self.gmail.get_email_metadata(uid, full_mid)

        raw = await self.ai_engine.agent_chat(
            "In exactly 2-3 sentences, give a spoken summary for text-to-speech. "
            "No markdown symbols, no bullets, natural speech only:\n\n" + body[:3000], uid)
        tts_text  = _clean_ai_text(raw)
        clean_tts = re.sub(r'[*_#`•]', '', tts_text)

        audio = await self.voice.synthesize(clean_tts, telegram_id=uid)

        sender  = meta.get("sender",  "").replace("*","").replace("_","")
        subject = meta.get("subject", "").replace("*","").replace("_","")
        att_ct  = len(meta.get("attachments", []))

        rows = [
            [InlineKeyboardButton("📖 Read Full Email",
                                  callback_data=_cb("read", full_mid[:16], ctx, offset))]
        ]
        if att_ct:
            rows.append([InlineKeyboardButton("📥 Get Attachments",
                                               callback_data=_cb("att", full_mid[:16], ctx, offset))])
        rows.append(kb_back(ctx, offset))
        kb = InlineKeyboardMarkup(rows)

        # Explicit dynamic caption with full context
        caption = (
            f"🔊 *Audio Summary*\n"
            f"📧 *From:* {sender}\n"
            f"📝 *Subject:* {subject}"
        )

        if audio and os.path.exists(audio):
            with open(audio, "rb") as f:
                await context.bot.send_voice(
                    chat_id=uid, voice=f,
                    caption=caption, parse_mode="Markdown", reply_markup=kb)
            try:
                os.remove(audio)
            except Exception:
                pass
            # Delete the "Generating..." overlay immediately
            try:
                await query.message.delete()
            except Exception:
                pass
        else:
            await query.edit_message_text(
                "❌ *Audio generation failed.*",
                parse_mode="Markdown", reply_markup=kb)

    async def _do_attachments(self, query, context, mid_short: str,
                               ctx: str, offset: int, uid: int):
        """
        Fetches and sends email attachments.
        Includes a guardrail to block batches larger than 10 files.
        """
        await query.edit_message_text("⏳ *Fetching attachments...*", parse_mode="Markdown")
        full_mid = self._full_mid(mid_short)
        back_kb  = InlineKeyboardMarkup([[
            InlineKeyboardButton("🔙 Back to Email",
                                 callback_data=_cb("read", mid_short, ctx, offset))
        ]])

        # Guardrail security constraint logic validation parameters
        try:
            meta = await self.gmail.get_email_metadata(uid, full_mid)
            if len(meta.get("attachments", [])) > 10:
                await query.edit_message_text("⚠️ *Download Blocked:* Batch attachment limits exceeded maximum threshold bounds (Max 10 files).", parse_mode="Markdown", reply_markup=back_kb)
                return
        except Exception:
            pass

        try:
            paths = await self.gmail.get_attachments(uid, full_mid)
        except Exception:
            paths = []

        if not paths:
            await query.edit_message_text(
                "📭 *No downloadable attachments found.*",
                parse_mode="Markdown", reply_markup=back_kb)
            return

        await query.edit_message_text(
            f"📤 *Sending {len(paths)} attachment(s)...*", parse_mode="Markdown")

        sent = 0
        for fp in paths:
            try:
                with open(fp, "rb") as f:
                    await context.bot.send_document(chat_id=uid, document=f)
                sent += 1
            except Exception as e:
                logger.error(f"Attachment send error: {e}")
            finally:
                try:
                    os.remove(fp)
                except Exception:
                    pass

        await query.edit_message_text(
            f"✅ *{sent}/{len(paths)} file(s) sent.*",
            parse_mode="Markdown", reply_markup=back_kb)

    # ── Background jobs ────────────────────────────────────────────────────────

    async def job_ping(self, context: ContextTypes.DEFAULT_TYPE):
        import httpx
        try:
            async with httpx.AsyncClient(timeout=10) as c:
                await c.get(f"{settings.RENDER_WEB_SERVICE_URL}/health")
        except Exception:
            pass

    async def job_emails(self, context: ContextTypes.DEFAULT_TYPE):
        """
        Background email check.
        FIX: uses await self.db.db.run() — NOT the non-existent run_lambda.
        Premium notification format. No smart replies.
        """
        async with self.email_lock:
            try:
                users = await self.db.get_active_auto_check_users()
                for user in users:
                    uid = user["telegram_id"]
                    try:
                        emails = await self.gmail.get_emails(
                            uid, query="is:unread newer_than:1d", max_results=10)
                    except Exception:
                        continue

                    for email_item in emails:
                        mid = email_item["id"]
                        if mid in self.notified_emails:
                            continue
                        self.notified_emails.add(mid)
                        self._store_mid(mid)

                        try:
                            meta = await self.gmail.get_email_metadata(uid, mid)
                        except Exception:
                            continue
                        if "error" in meta:
                            continue

                        sender  = meta.get("sender",  "Unknown").replace("*","").replace("_","")
                        subject = meta.get("subject", "No Subject").replace("*","").replace("_","")
                        att_ct  = len(meta.get("attachments", []))
                        att_line = f"\n📎 *{att_ct} Attachment(s) Found*" if att_ct else ""

                        # Premium structured notification
                        text = (
                            f"📩 *New Email Received*\n"
                            f"━━━━━━━━━━━━━━━━━━\n"
                            f"👤 *From:* {sender}\n"
                            f"📝 *Subject:* {subject}"
                            f"{att_line}"
                        )

                        # Cache to DB — correct async pattern
                        try:
                            await self.db.db.run(
                                lambda u=uid, m=mid, s=sender, sub=subject:
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

            except Exception as e:
                logger.error(f"job_emails error: {e}")

    async def job_scheduled(self, context: ContextTypes.DEFAULT_TYPE):
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

                    result = await self.gmail.send_email(
                        uid, task["to_email"], task["subject"], task["body"], paths)
                    status = "sent" if "successfully" in result.lower() else "failed"

                    await self.db.db.run(
                        lambda t=task, s=status: self.db.db.client.table("scheduled_emails")
                        .update({"status": s}).eq("id", t["id"]).execute())

                    note = (f"✅ *Scheduled Email Sent!*\n*To:* `{task['to_email']}`"
                            if status == "sent"
                            else f"❌ *Scheduled Email Failed*\n{result}")
                    await context.bot.send_message(chat_id=uid, text=note, parse_mode="Markdown")
                finally:
                    # Thread leak block logic: safely clear storage even on crash cascades
                    for fp in paths:
                        if os.path.exists(fp):
                            try: os.remove(fp)
                            except Exception: pass
        except Exception as e:
            logger.error(f"job_scheduled error: {e}")

# ── Singleton ──────────────────────────────────────────────────────────────────
telegram_handler = TelegramBotManager()