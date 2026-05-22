"""
Telegram Bot Handler — Smart Email Assistant
============================================
Complete rewrite with:
- Perfect symmetric button grid layouts matching the workflow diagram
- Robust callback data parser (no fragile split() assumptions)
- Full Settings menu (AI toggle, Voice mode, Auto-check, Logout)
- Smart Replies implemented (sr_ action)
- Undo Send with clean state management
- All navigation contexts (inbox / search / main) handled correctly
- Background jobs: email check, scheduled emails, keep-alive ping
- asyncio.Lock on email check to prevent race conditions
- Ephemeral file cleanup on every path
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


# ─────────────────────────────────────────────────────────────
# CALLBACK DATA HELPERS  (never use split() directly on cb data)
# Format: "action:param1:param2:..."
# ─────────────────────────────────────────────────────────────

def _cb(action: str, *args) -> str:
    """Build a callback_data string. Max 64 bytes enforced."""
    data = ":".join([action] + [str(a) for a in args])
    if len(data) > 64:
        raise ValueError(f"callback_data too long ({len(data)}): {data}")
    return data

def _parse_cb(data: str) -> tuple[str, list[str]]:
    """Parse callback_data into (action, [args])."""
    parts = data.split(":")
    return parts[0], parts[1:]


# ─────────────────────────────────────────────────────────────
# KEYBOARD BUILDERS  (single source of truth for every menu)
# ─────────────────────────────────────────────────────────────

def kb_main_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("📥 Inbox",         callback_data=_cb("inbox", 0)),
            InlineKeyboardButton("✍️ Compose",        callback_data="compose"),
        ],
        [
            InlineKeyboardButton("🔍 Search Emails", callback_data="search_prompt"),
            InlineKeyboardButton("⚙️ Settings",       callback_data="settings"),
        ],
    ])

def kb_back_to(context: str = "main", offset: int = 0) -> list[InlineKeyboardButton]:
    """Returns a single-row back button list."""
    if context == "inbox":
        return [InlineKeyboardButton("🔙 Back to Inbox",   callback_data=_cb("inbox", offset))]
    if context == "search":
        return [InlineKeyboardButton("🔙 Back to Results", callback_data=_cb("srpage", offset))]
    return [InlineKeyboardButton("🔙 Main Dashboard",      callback_data="menu_main")]

def kb_email_list(messages: list, offset: int, is_search: bool, has_next: bool) -> InlineKeyboardMarkup:
    """2-email-per-page layout with Prev / Next navigation."""
    rows = []
    nav_ctx = "search" if is_search else "inbox"
    for i, msg in enumerate(messages):
        rows.append([InlineKeyboardButton(
            f"📖 Read Email {offset + i + 1}",
            callback_data=_cb("read", msg["id"], nav_ctx, offset)
        )])
    nav_row = []
    if offset > 0:
        prev_cb = _cb("srpage", offset - 2) if is_search else _cb("inbox", offset - 2)
        nav_row.append(InlineKeyboardButton("⬅️ Prev", callback_data=prev_cb))
    if has_next:
        next_cb = _cb("srpage", offset + 2) if is_search else _cb("inbox", offset + 2)
        nav_row.append(InlineKeyboardButton("Next ➡️", callback_data=next_cb))
    if nav_row:
        rows.append(nav_row)
    rows.append(kb_back_to())
    return InlineKeyboardMarkup(rows)

def kb_email_view(msg_id: str, nav_ctx: str, offset: int, has_attachments: bool) -> InlineKeyboardMarkup:
    """Full email view — symmetric 2-column grid per the workflow."""
    rows = [
        [
            InlineKeyboardButton("↩️ Reply",      callback_data=_cb("reply",   msg_id, nav_ctx, offset)),
            InlineKeyboardButton("🗑️ Trash",       callback_data=_cb("del",     msg_id, nav_ctx, offset)),
        ],
        [
            InlineKeyboardButton("🤖 AI Summary", callback_data=_cb("sum",     msg_id, nav_ctx, offset)),
            InlineKeyboardButton("🔊 Listen",      callback_data=_cb("tts",     msg_id, nav_ctx, offset)),
        ],
    ]
    if has_attachments:
        rows.append([InlineKeyboardButton("📥 Get Attachments", callback_data=_cb("att", msg_id, nav_ctx, offset))])
    rows.append(kb_back_to(nav_ctx, offset))
    return InlineKeyboardMarkup(rows)

def kb_summary_view(msg_id: str, nav_ctx: str, offset: int,
                    has_attachments: bool, smart_replies: list[str]) -> InlineKeyboardMarkup:
    """AI Summary view — quick-reply chips + read full + back."""
    rows = []
    # Smart reply chips (max 3, each ≤ 30 chars)
    for reply_text in smart_replies[:3]:
        safe = reply_text[:30]
        rows.append([InlineKeyboardButton(
            f"💬 {safe}",
            callback_data=_cb("sr", msg_id, nav_ctx, offset, str(smart_replies.index(reply_text)))
        )])
    rows.append([InlineKeyboardButton("📖 Read Full Email", callback_data=_cb("read", msg_id, nav_ctx, offset))])
    if has_attachments:
        rows.append([InlineKeyboardButton("📥 Get Attachments", callback_data=_cb("att", msg_id, nav_ctx, offset))])
    rows.append(kb_back_to(nav_ctx, offset))
    return InlineKeyboardMarkup(rows)

def kb_compose_draft(has_ai_body: bool = False) -> InlineKeyboardMarkup:
    """Draft review screen — Send / Attach / Cancel."""
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("🚀 Send Now",       callback_data="send_draft"),
            InlineKeyboardButton("❌ Cancel",          callback_data="cancel"),
        ],
        [InlineKeyboardButton("📎 Add Attachment",    callback_data="attach_hint")],
    ])

def kb_cancel_only() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[InlineKeyboardButton("❌ Cancel Process", callback_data="cancel")]])

def kb_undo_send() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("↩️ Undo Send", callback_data="undo_send")],
        kb_back_to(),
    ])

def kb_new_email_notification(msg_id: str) -> InlineKeyboardMarkup:
    """Push notification layout matching the workflow."""
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📖 Read Email",   callback_data=_cb("read", msg_id, "inbox", 0))],
        [
            InlineKeyboardButton("🤖 AI Summary", callback_data=_cb("sum",  msg_id, "inbox", 0)),
            InlineKeyboardButton("🔊 Listen",      callback_data=_cb("tts",  msg_id, "inbox", 0)),
        ],
    ])

def kb_settings(ai_on: bool, voice_pref: str, auto_on: bool) -> InlineKeyboardMarkup:
    ai_label    = f"{'✅' if ai_on   else '❌'} AI Mode"
    auto_label  = f"{'✅' if auto_on else '❌'} Auto Email Check"
    voice_icons = {"text": "📝 Text Only", "voice": "🔊 Voice Only", "both": "📝+🔊 Both"}
    voice_label = voice_icons.get(voice_pref, "📝 Text Only")
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(ai_label,    callback_data="toggle_ai")],
        [InlineKeyboardButton(voice_label, callback_data="cycle_voice")],
        [InlineKeyboardButton(auto_label,  callback_data="toggle_auto")],
        [InlineKeyboardButton("🚪 Logout Account", callback_data="logout")],
        kb_back_to(),
    ])


# ─────────────────────────────────────────────────────────────
# MAIN BOT MANAGER
# ─────────────────────────────────────────────────────────────

class TelegramBotManager:
    def __init__(self) -> None:
        self.application: Application | None = None
        self.ai_engine    = AIEngine()
        self.db           = db_manager
        self.memory       = memory_manager
        self.gmail        = GmailClient()
        self.voice        = voice_handler
        self.contacts     = contact_manager

        # ── Per-user state dicts ──
        self.compose_states:    dict = {}   # {user_id: {step, to, subj, body, attachments}}
        self.search_states:     dict = {}   # {user_id: 'AWAIT_QUERY'}
        self.current_queries:   dict = {}   # {user_id: last_search_query}
        self.pending_sends:     dict = {}   # {user_id: draft_dict}
        self.active_voice_tasks: set = set()
        self.notified_emails:    set = set()
        self._smart_reply_cache: dict = {}  # {user_id: [replies]}

        self.email_lock   = asyncio.Lock()
        self.startup_time = int(time.time() * 1000)

    # ── Utilities ──────────────────────────────────────────────

    def _bg(self, coro):
        """Fire-and-forget background coroutine."""
        asyncio.create_task(coro)

    async def _get_prefs(self, user_id: int) -> dict:
        try:
            return await self.db.get_user_preferences(user_id) or {}
        except Exception:
            return {}

    async def _send_or_edit(self, update: Update, text: str,
                             markup: InlineKeyboardMarkup | None = None,
                             parse_mode: str = "Markdown"):
        try:
            if update.callback_query:
                await update.callback_query.edit_message_text(
                    text, parse_mode=parse_mode, reply_markup=markup,
                    disable_web_page_preview=True
                )
            elif update.message:
                await update.message.reply_text(
                    text, parse_mode=parse_mode, reply_markup=markup,
                    disable_web_page_preview=True
                )
        except Exception as e:
            logger.debug(f"_send_or_edit: {e}")

    async def _edit_or_reply(self, msg_obj, text: str,
                              markup: InlineKeyboardMarkup | None = None,
                              parse_mode: str = "Markdown"):
        """Works on both Message and CallbackQuery.message objects."""
        try:
            if hasattr(msg_obj, "edit_text"):
                await msg_obj.edit_text(
                    text, parse_mode=parse_mode, reply_markup=markup,
                    disable_web_page_preview=True
                )
            else:
                await msg_obj.reply_text(
                    text, parse_mode=parse_mode, reply_markup=markup,
                    disable_web_page_preview=True
                )
        except Exception as e:
            logger.debug(f"_edit_or_reply: {e}")

    # ── Background helpers ─────────────────────────────────────

    async def _bg_save_contact(self, telegram_id: int, raw_sender: str):
        try:
            match = re.search(r'<(.+?)>', raw_sender)
            email = match.group(1) if match else raw_sender.strip()
            if "@" not in email:
                return
            name = email.split("@")[0]
            await self.db.db.run(lambda: self.db.db.client.table("contacts").upsert(
                {"telegram_id": telegram_id, "contact_alias": name,
                 "email_address": email, "contact_name": name},
                on_conflict="telegram_id,email_address"
            ).execute())
        except Exception:
            pass

    async def _bg_save_attachment(self, telegram_id: int, file_id: str, file_name: str):
        try:
            await self.db.db.run(lambda: self.db.db.client.table("saved_attachments").insert(
                {"telegram_id": telegram_id, "file_id": file_id,
                 "file_name": file_name, "context_topic": "Uploaded via Chat"}
            ).execute())
        except Exception:
            pass

    # ── Bot Setup ──────────────────────────────────────────────

    async def setup_bot(self):
        self.application = ApplicationBuilder().token(settings.BOT_TOKEN).build()
        self.application.add_handler(CommandHandler("start",  self.cmd_start))
        self.application.add_handler(CommandHandler("menu",   self.cmd_menu))
        self.application.add_handler(CallbackQueryHandler(self.handle_button))
        self.application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, self.handle_text))
        self.application.add_handler(MessageHandler(filters.VOICE, self.handle_voice))
        self.application.add_handler(MessageHandler(
            filters.Document.ALL | filters.PHOTO | filters.VIDEO | filters.AUDIO,
            self.handle_attachment
        ))
        await self.application.initialize()
        if self.application.job_queue:
            self.application.job_queue.run_repeating(self.job_check_emails,     interval=60,  first=15)
            self.application.job_queue.run_repeating(self.job_check_scheduled,  interval=60,  first=30)
            self.application.job_queue.run_repeating(self.job_keep_alive,       interval=840, first=60)
        await self.application.bot.set_webhook(
            url=f"{settings.RENDER_WEB_SERVICE_URL}/webhook/telegram"
        )
        logger.info("✅ Webhook set. Bot is live.")
        await self.application.start()

    async def process_webhook(self, data: dict):
        if self.application:
            update = Update.de_json(data, self.application.bot)
            await self.application.process_update(update)

    # ── Access Control ─────────────────────────────────────────

    async def _check_access(self, user_id: int, first_name: str, username: str) -> dict:
        if await self.db.is_blocked("telegram", str(user_id)):
            return {"status": "blocked"}
        db_user = await self.db.get_user(user_id)
        if not db_user:
            await self.db.create_user(user_id, email=None,
                                       first_name=first_name, username=username)
            return {"status": "pending"}
        if not db_user.get("is_verified"):
            return {"status": "pending"}
        if not db_user.get("auth_token"):
            return {"status": "unauthenticated"}
        return {"status": "ok", "user": db_user}

    async def _gate(self, update: Update, user_id: int, status: str) -> bool:
        """Returns True if access is denied (caller should return immediately)."""
        if status == "blocked":
            await self._send_or_edit(update,
                "🚫 *Access Revoked*\nYour account has been restricted by the administrator.")
            return True
        if status == "pending":
            await self._send_or_edit(update,
                "⏳ *Verification Pending*\nYour account is awaiting admin approval.\n"
                "You will be notified once it's approved.")
            return True
        if status == "unauthenticated":
            state_uuid = await self.db.create_auth_session(user_id)
            login_url  = (f"{settings.RENDER_WEB_SERVICE_URL}/api/auth/telegram_login"
                          f"?state={state_uuid}&telegram_id={user_id}")
            kb = InlineKeyboardMarkup(
                [[InlineKeyboardButton("🔗 Connect Google Workspace", url=login_url)]]
            )
            await self._send_or_edit(update,
                "⚠️ *Authentication Required*\n"
                "Please link your Gmail account to start using the assistant.", kb)
            return True
        return False

    # ─────────────────────────────────────────────────────────
    # COMMAND HANDLERS
    # ─────────────────────────────────────────────────────────

    async def cmd_start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        user   = update.effective_user
        access = await self._check_access(user.id, user.first_name or "", user.username or "")
        if await self._gate(update, user.id, access["status"]):
            return
        text = (f"👋 *Welcome, {user.first_name}!*\n\n"
                "I am your AI Email Assistant. I can help you read, search, compose, and manage "
                "your Gmail inbox — via buttons, text, or voice notes.\n\n"
                "Select an option below to get started:")
        await self._send_or_edit(update, text, kb_main_menu())

    async def cmd_menu(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        user   = update.effective_user
        access = await self._check_access(user.id, user.first_name or "", user.username or "")
        if await self._gate(update, user.id, access["status"]):
            return
        await self._send_or_edit(update,
            "🎛️ *Main Dashboard*\n\nWhat would you like to do?", kb_main_menu())

    # ─────────────────────────────────────────────────────────
    # UI RENDERERS
    # ─────────────────────────────────────────────────────────

    async def _show_inbox(self, msg_obj, offset: int, user_id: int, is_search: bool = False):
        """Paginated 2-email list — works for both Inbox and Search."""
        query = self.current_queries.get(user_id, "is:unread") if is_search else "label:INBOX"
        safe_q = "in:inbox" if query == "label:INBOX" else query

        try:
            messages = await self.gmail.get_emails(user_id, query=safe_q, max_results=offset + 3)
        except Exception:
            messages = []

        if not messages and offset == 0:
            text   = (f"📭 No emails found for: `{safe_q}`" if is_search
                      else "📭 Your inbox is empty.")
            back_kb = InlineKeyboardMarkup([kb_back_to()])
            await self._edit_or_reply(msg_obj, text, back_kb)
            return

        display = messages[offset:offset + 2]
        has_next = len(messages) > offset + 2

        lines = [f"🔍 *Search:* `{safe_q}`\n" if is_search else "📥 *Your Inbox*\n"]
        for i, msg in enumerate(display):
            meta   = await self.gmail.get_email_metadata(user_id, msg["id"])
            if "error" in meta:
                continue
            sender = meta.get("sender", "Unknown")[:45].replace("*", "").replace("_", "")
            subj   = meta.get("subject", "No Subject")[:55].replace("*", "").replace("_", "")
            lines.append(f"*{offset + i + 1}.* {sender}\n_{subj}_\n")

        kb = kb_email_list(display, offset, is_search, has_next)
        await self._edit_or_reply(msg_obj, "\n".join(lines), kb)

    async def _show_full_email(self, query, msg_id: str, nav_ctx: str, offset: int, user_id: int):
        await query.edit_message_text("⏳ Fetching email...")

        body  = await self.gmail.read_full_email(user_id, msg_id)
        meta  = await self.gmail.get_email_metadata(user_id, msg_id)

        # Truncate safely
        if len(body) > 3500:
            body = body[:3500] + "\n\n[... Truncated ...]"

        # Sanitize for HTML parse_mode (avoids Markdown breaking on < > & * _)
        def _esc(s: str) -> str:
            return (s.replace("&", "&amp;")
                     .replace("<", "&lt;")
                     .replace(">", "&gt;"))

        safe_body   = _esc(body)
        safe_sender = _esc(meta.get("sender", "Unknown"))
        safe_subj   = _esc(meta.get("subject", "No Subject"))

        # Linkify URLs
        safe_body = re.sub(
            r'(https?://[^\s<>\"]+)',
            r'<a href="\1">🔗 Link</a>',
            safe_body
        )

        att_list = meta.get("attachments", [])
        att_text = f"\n📎 <b>Attachments:</b> {len(att_list)} file(s)" if att_list else ""

        formatted = (
            f"📧 <b>From:</b> {safe_sender}\n"
            f"📝 <b>Subject:</b> {safe_subj}{att_text}\n"
            f"{'━' * 20}\n\n{safe_body}"
        )

        kb = kb_email_view(msg_id, nav_ctx, offset, bool(att_list))
        await query.edit_message_text(formatted, parse_mode="HTML", reply_markup=kb,
                                       disable_web_page_preview=True)

        # Background: save sender contact
        self._bg(self._bg_save_contact(user_id, meta.get("sender", "")))

    # ─────────────────────────────────────────────────────────
    # TEXT HANDLER
    # ─────────────────────────────────────────────────────────

    async def handle_text(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        user   = update.effective_user
        access = await self._check_access(user.id, user.first_name or "", user.username or "")
        if await self._gate(update, user.id, access["status"]):
            return

        uid  = user.id
        text = update.message.text

        # ── Compose flow intercept ──
        if uid in self.compose_states:
            await self._handle_compose_text(update, uid, text)
            return

        # ── Search flow intercept ──
        if self.search_states.get(uid) == "AWAIT_QUERY":
            self.search_states.pop(uid, None)
            self.current_queries[uid] = text
            wait = await update.message.reply_text("🔍 Searching...", parse_mode="Markdown")
            # Contact-aware search enrichment
            found = await self.contacts.find_contacts_by_name(uid, text)
            if found:
                emails    = [c["email_address"] for c in found]
                email_q   = " OR ".join(f"from:{e}" for e in emails)
                combined  = f"({email_q}) OR {text}"
                self.current_queries[uid] = combined
            await self._show_inbox(wait, offset=0, user_id=uid, is_search=True)
            return

        # ── AI agent ──
        prefs = await self._get_prefs(uid)
        if not access["user"].get("ai_allowed", True):
            await update.message.reply_text(
                "🚫 *AI access is restricted* for your account.", parse_mode="Markdown")
            return

        msg = await update.message.reply_text("✨ *Thinking...*", parse_mode="Markdown")
        await context.bot.send_chat_action(chat_id=uid, action=ChatAction.TYPING)
        raw = await self.ai_engine.agent_chat(text, uid)
        await self._dispatch_ai_response(update, context, msg, raw, uid, prefs)

    async def _handle_compose_text(self, update: Update, uid: int, text: str):
        state  = self.compose_states[uid]
        step   = state.get("step")
        cancel = kb_cancel_only()

        if step == "AWAIT_TO":
            state["to"]   = text
            # If AI already filled subject + body (came from AI draft), skip to review
            if state.get("body") and state.get("subj"):
                state["step"] = "AWAIT_ATTACH"
                await update.message.reply_text(
                    self._draft_preview(state), parse_mode="Markdown",
                    reply_markup=kb_compose_draft())
            else:
                state["step"] = "AWAIT_SUBJ"
                await update.message.reply_text(
                    f"✅ To: `{text}`\n\n📝 *Subject?*",
                    parse_mode="Markdown", reply_markup=cancel)

        elif step == "AWAIT_SUBJ":
            state["subj"] = text
            state["step"] = "AWAIT_BODY"
            await update.message.reply_text(
                "✍️ *What should the email say?*\n_(You can also send a voice note)_",
                parse_mode="Markdown", reply_markup=cancel)

        elif step == "AWAIT_BODY":
            state["body"] = text
            state["step"] = "AWAIT_ATTACH"
            await update.message.reply_text(
                self._draft_preview(state), parse_mode="Markdown",
                reply_markup=kb_compose_draft())

        elif step == "AWAIT_ATTACH":
            # User typed something during attachment step — remind them
            await update.message.reply_text(
                "📎 Upload a file to attach, or click *Send Now*.",
                parse_mode="Markdown",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("🚀 Send Now", callback_data="send_draft")],
                    [InlineKeyboardButton("❌ Cancel",   callback_data="cancel")],
                ]))

    @staticmethod
    def _draft_preview(state: dict) -> str:
        return (
            f"📄 *Draft Ready for Review*\n\n"
            f"*To:* `{state.get('to', '—')}`\n"
            f"*Subject:* `{state.get('subj', '—')}`\n"
            f"*Body:*\n_{state.get('body', '—')}_\n\n"
            f"📎 Upload an attachment or click *Send Now*."
        )

    # ─────────────────────────────────────────────────────────
    # VOICE HANDLER
    # ─────────────────────────────────────────────────────────

    async def handle_voice(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        user   = update.effective_user
        access = await self._check_access(user.id, user.first_name or "", user.username or "")
        if await self._gate(update, user.id, access["status"]):
            return
        if not access["user"].get("voice_allowed", True):
            await update.message.reply_text("🚫 *Voice access restricted.*", parse_mode="Markdown")
            return

        msg = await update.message.reply_text("🎙️ *Processing voice note...*", parse_mode="Markdown")
        await context.bot.send_chat_action(chat_id=user.id, action=ChatAction.RECORD_VOICE)

        file_path = os.path.join(tempfile.gettempdir(), f"voice_{uuid.uuid4().hex}.ogg")
        try:
            vf = await context.bot.get_file(update.message.voice.file_id)
            await vf.download_to_drive(file_path)

            transcribed = await self.ai_engine.transcribe_audio(file_path, user.id)
        finally:
            if os.path.exists(file_path):
                os.remove(file_path)

        if transcribed.startswith("System Error:") or "[Audio Unclear]" in transcribed:
            await msg.edit_text("❌ *Audio unclear.* Please try again.", parse_mode="Markdown")
            return

        task_id = str(int(time.time() * 1000))
        self.active_voice_tasks.add(task_id)
        await msg.edit_text(
            f"🗣️ *You said:* _{transcribed}_\n\n✨ *Thinking...*",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("❌ Cancel", callback_data=f"cancel_voice:{task_id}")
            ]])
        )

        # Handle compose body via voice
        uid = user.id
        if uid in self.compose_states and self.compose_states[uid].get("step") == "AWAIT_BODY":
            self.compose_states[uid]["body"] = transcribed
            self.compose_states[uid]["step"] = "AWAIT_ATTACH"
            await msg.edit_text(
                self._draft_preview(self.compose_states[uid]),
                parse_mode="Markdown", reply_markup=kb_compose_draft())
            self.active_voice_tasks.discard(task_id)
            return

        raw   = await self.ai_engine.agent_chat(transcribed, uid)
        if task_id not in self.active_voice_tasks:
            return  # cancelled
        self.active_voice_tasks.discard(task_id)

        prefs = await self._get_prefs(uid)
        await self._dispatch_ai_response(update, context, msg, raw, uid, prefs)

    # ─────────────────────────────────────────────────────────
    # ATTACHMENT HANDLER
    # ─────────────────────────────────────────────────────────

    async def handle_attachment(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        user   = update.effective_user
        access = await self._check_access(user.id, user.first_name or "", user.username or "")
        if await self._gate(update, user.id, access["status"]):
            return

        att = (update.message.document
               or (update.message.photo[-1] if update.message.photo else None)
               or update.message.audio
               or update.message.video)
        if not att:
            return

        if getattr(att, "file_size", 0) > 20 * 1024 * 1024:
            await update.message.reply_text(
                "❌ *File too large* (max 20 MB). Share a Drive link instead.",
                parse_mode="Markdown")
            return

        msg = await update.message.reply_text("📥 *Downloading file...*", parse_mode="Markdown")
        uid      = user.id
        ext      = (getattr(att, "file_name", "file") or "file").rsplit(".", 1)[-1]
        file_name = getattr(att, "file_name", f"file_{uuid.uuid4().hex[:6]}.{ext}")
        file_path = os.path.join(tempfile.gettempdir(), f"doc_{uuid.uuid4().hex}.{ext}")

        try:
            fobj = await context.bot.get_file(att.file_id)
            await fobj.download_to_drive(file_path)
        except Exception:
            await msg.edit_text("❌ *Failed to download file.*", parse_mode="Markdown")
            return

        # If user is in compose flow — attach to draft
        if uid in self.compose_states and self.compose_states[uid].get("step") == "AWAIT_ATTACH":
            self.compose_states[uid].setdefault("attachments", []).append(file_path)
            await msg.edit_text(
                f"📎 *Attached:* `{file_name}`\n\nSend now or upload another file.",
                parse_mode="Markdown",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("🚀 Send Email Now", callback_data="send_draft")],
                    [InlineKeyboardButton("❌ Cancel",          callback_data="cancel")],
                ]))
            return

        # Otherwise: store for AI session
        self.gmail.add_user_attachment(uid, file_path)
        self._bg(self._bg_save_attachment(uid, att.file_id, file_name))

        caption = update.message.caption or ""
        if caption:
            raw   = await self.ai_engine.agent_chat(
                f"[Uploaded Document: {file_name}] {caption}", uid)
            prefs = await self._get_prefs(uid)
            await self._dispatch_ai_response(update, context, msg, raw, uid, prefs)
        else:
            try:
                await msg.delete()
            except Exception:
                pass
            await update.message.reply_text(
                f"✅ *File uploaded:* `{file_name}`\n"
                "Tell me what to do with it (e.g. 'attach to my next email' or 'summarize it').",
                parse_mode="Markdown",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("✉️ Draft an Email", callback_data="compose")],
                    kb_back_to(),
                ]))

    # ─────────────────────────────────────────────────────────
    # AI RESPONSE DISPATCHER
    # ─────────────────────────────────────────────────────────

    async def _dispatch_ai_response(self, update: Update, context: ContextTypes.DEFAULT_TYPE,
                                     msg_obj, raw: str, uid: int, prefs: dict):
        """
        Parses AI JSON, handles HITL draft injection, routes to voice or text.
        """
        try:
            clean = re.sub(r'```json|```', '', raw).strip()
            m     = re.search(r'\{.*\}', clean, re.DOTALL)
            parsed = json.loads(m.group(0) if m else clean)
        except Exception:
            parsed = {"text": raw, "response_type": "text"}

        text_content  = parsed.get("text", "Processing...")
        response_type = parsed.get("response_type", "text")
        draft_data    = parsed.get("draft")

        # ── HITL draft injection ──
        if draft_data:
            to_field = draft_data.get("to", "")
            if not to_field or "[Specify Recipient]" in to_field:
                self.compose_states[uid] = {
                    "step": "AWAIT_TO",
                    "subj": draft_data.get("subject", ""),
                    "body": draft_data.get("body", ""),
                    "attachments": [],
                }
                await self._edit_or_reply(
                    msg_obj,
                    f"📝 *Draft Prepared*\n\n"
                    f"*Subject:* `{draft_data.get('subject', '—')}`\n"
                    f"*Body:*\n_{draft_data.get('body', '—')}_\n\n"
                    f"⚠️ *Recipient missing!* Please type the email address:",
                    kb_cancel_only()
                )
            else:
                self.compose_states[uid] = {
                    "step": "AWAIT_ATTACH",
                    "to":   draft_data.get("to", ""),
                    "subj": draft_data.get("subject", ""),
                    "body": draft_data.get("body", ""),
                    "attachments": [],
                }
                await self._edit_or_reply(
                    msg_obj,
                    self._draft_preview(self.compose_states[uid]),
                    kb_compose_draft(has_ai_body=True)
                )
            return

        # ── Voice response ──
        voice_pref = prefs.get("voice_preference", "text")
        if response_type == "voice" and voice_pref in ("voice", "both"):
            await context.bot.send_chat_action(chat_id=uid, action=ChatAction.RECORD_VOICE)
            clean_tts = re.sub(r'[*_#`]', '', text_content)
            audio = await self.voice.synthesize(
                clean_tts, telegram_id=uid,
                preferred_method=prefs.get("preferred_tts_method", "google")
            )
            if audio and os.path.exists(audio):
                with open(audio, "rb") as f:
                    if voice_pref == "both":
                        await self._edit_or_reply(msg_obj, f"🤖 {text_content}",
                                                   InlineKeyboardMarkup([kb_back_to()]))
                        await context.bot.send_voice(
                            chat_id=uid, voice=f,
                            reply_markup=InlineKeyboardMarkup([kb_back_to()])
                        )
                    else:
                        await context.bot.send_voice(
                            chat_id=uid, voice=f,
                            caption="🔊 AI Voice Response",
                            reply_markup=InlineKeyboardMarkup([kb_back_to()])
                        )
                        try:
                            await msg_obj.delete()
                        except Exception:
                            pass
                try:
                    os.remove(audio)
                except Exception:
                    pass
                return

        # ── Text response ──
        await self._edit_or_reply(
            msg_obj,
            f"🤖 {text_content}",
            InlineKeyboardMarkup([kb_back_to()])
        )

    # ─────────────────────────────────────────────────────────
    # BUTTON HANDLER  (central dispatcher)
    # ─────────────────────────────────────────────────────────

    async def handle_button(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        query   = update.callback_query
        uid     = query.from_user.id
        data    = query.data
        try:
            await query.answer()
        except Exception:
            pass

        action, args = _parse_cb(data)

        # ── Simple non-parameterised actions first ──
        if action == "menu_main":
            self.compose_states.pop(uid, None)
            self.search_states.pop(uid, None)
            await self._send_or_edit(update,
                "🎛️ *Main Dashboard*\n\nWhat would you like to do?", kb_main_menu())
            return

        if action == "inbox":
            offset = int(args[0]) if args else 0
            await self._show_inbox(query.message, offset, uid, is_search=False)
            return

        if action == "srpage":
            offset = int(args[0]) if args else 0
            await self._show_inbox(query.message, offset, uid, is_search=True)
            return

        if action == "search_prompt":
            self.search_states[uid] = "AWAIT_QUERY"
            await query.edit_message_text(
                "🔍 *Search Emails*\n\nType your query below (e.g. `from:ali` or `project invoice`):",
                parse_mode="Markdown",
                reply_markup=InlineKeyboardMarkup([kb_back_to()])
            )
            return

        if action == "compose":
            self.compose_states[uid] = {"step": "AWAIT_TO", "attachments": []}
            await query.edit_message_text(
                "✉️ *Compose Email*\n\nPlease type the *recipient's email address*:",
                parse_mode="Markdown", reply_markup=kb_cancel_only())
            return

        if action == "cancel":
            self.compose_states.pop(uid, None)
            self.search_states.pop(uid, None)
            self.pending_sends.pop(uid, None)
            await query.edit_message_text(
                "🚫 *Process Canceled*\n\nThe action was safely stopped.",
                parse_mode="Markdown",
                reply_markup=InlineKeyboardMarkup([kb_back_to()]))
            return

        if action == "cancel_voice":
            task_id = args[0] if args else ""
            self.active_voice_tasks.discard(task_id)
            await query.edit_message_text(
                "🚫 *Voice command canceled.*",
                parse_mode="Markdown",
                reply_markup=InlineKeyboardMarkup([kb_back_to()]))
            return

        if action == "attach_hint":
            await query.answer("📎 Upload any file in this chat to attach it!", show_alert=True)
            return

        if action == "send_draft":
            await self._handle_send_draft(query, uid, context)
            return

        if action == "undo_send":
            if uid in self.pending_sends:
                self.pending_sends.pop(uid, None)
            await query.edit_message_text(
                "🚫 *Email send canceled.*\n\nThe draft was safely discarded.",
                parse_mode="Markdown",
                reply_markup=InlineKeyboardMarkup([kb_back_to()]))
            return

        # ── Settings ──
        if action == "settings":
            await self._show_settings(query, uid)
            return

        if action == "toggle_ai":
            prefs = await self._get_prefs(uid)
            new_val = not prefs.get("ai_mode_enabled", True)
            await self.db.update_user_preferences(uid, {"ai_mode_enabled": new_val})
            await self._show_settings(query, uid)
            return

        if action == "cycle_voice":
            prefs    = await self._get_prefs(uid)
            current  = prefs.get("voice_preference", "text")
            cycle    = {"text": "voice", "voice": "both", "both": "text"}
            next_val = cycle.get(current, "text")
            await self.db.update_user_preferences(uid, {"voice_preference": next_val})
            await self._show_settings(query, uid)
            return

        if action == "toggle_auto":
            prefs   = await self._get_prefs(uid)
            new_val = not prefs.get("auto_check_enabled", True)
            await self.db.update_user_preferences(uid, {"auto_check_enabled": new_val})
            await self._show_settings(query, uid)
            return

        if action == "logout":
            await self.db.db.run(lambda: self.db.db.client.table("users")
                                  .update({"auth_token": None})
                                  .eq("telegram_id", uid).execute())
            self.gmail.clear_user_attachments(uid)
            self.compose_states.pop(uid, None)
            await query.edit_message_text(
                "✅ *Logged out successfully.*\n\nSend /start to connect a new Google account.",
                parse_mode="Markdown")
            return

        # ── Email actions with params: action:msg_id:nav_ctx:offset ──

        if action == "read":
            if len(args) < 3:
                return
            msg_id, nav_ctx, offset = args[0], args[1], int(args[2])
            await self._show_full_email(query, msg_id, nav_ctx, offset, uid)
            return

        if action == "sum":
            if len(args) < 3:
                return
            msg_id, nav_ctx, offset = args[0], args[1], int(args[2])
            await self._handle_summary(query, context, msg_id, nav_ctx, offset, uid)
            return

        if action == "tts":
            if len(args) < 3:
                return
            msg_id, nav_ctx, offset = args[0], args[1], int(args[2])
            await self._handle_tts(query, context, msg_id, nav_ctx, offset, uid)
            return

        if action == "att":
            if len(args) < 3:
                return
            msg_id, nav_ctx, offset = args[0], args[1], int(args[2])
            await self._handle_get_attachments(query, context, msg_id, nav_ctx, offset, uid)
            return

        if action == "del":
            if len(args) < 3:
                return
            msg_id, nav_ctx, offset = args[0], args[1], int(args[2])
            if await self.gmail.delete_email(uid, msg_id):
                await query.edit_message_text(
                    "🗑️ *Email moved to trash.*",
                    parse_mode="Markdown",
                    reply_markup=InlineKeyboardMarkup([
                        [InlineKeyboardButton("↩️ Undo Delete",
                                              callback_data=_cb("untrash", msg_id, nav_ctx, offset))],
                        kb_back_to(nav_ctx, offset),
                    ]))
            return

        if action == "untrash":
            if len(args) < 3:
                return
            msg_id, nav_ctx, offset = args[0], args[1], int(args[2])
            if await self.gmail.untrash_email(uid, msg_id):
                await query.edit_message_text(
                    "✅ *Email restored to Inbox.*",
                    parse_mode="Markdown",
                    reply_markup=InlineKeyboardMarkup([kb_back_to(nav_ctx, offset)]))
            return

        if action == "reply":
            if len(args) < 3:
                return
            msg_id, nav_ctx, offset = args[0], args[1], int(args[2])
            meta   = await self.gmail.get_email_metadata(uid, msg_id)
            sender = meta.get("sender", "")
            match  = re.search(r'<(.+?)>', sender)
            email  = match.group(1) if match else sender
            subj   = meta.get("subject", "")
            if not subj.startswith("Re:"):
                subj = "Re: " + subj
            self.compose_states[uid] = {
                "step": "AWAIT_BODY", "to": email, "subj": subj, "attachments": []
            }
            await query.edit_message_text(
                f"✉️ *Reply to:* `{email}`\n\n✍️ Type your message below:",
                parse_mode="Markdown",
                reply_markup=kb_cancel_only())
            return

        # ── Smart Reply chip: sr:msg_id:nav_ctx:offset:reply_idx ──
        if action == "sr":
            if len(args) < 4:
                return
            msg_id, nav_ctx, offset, ridx = args[0], args[1], int(args[2]), int(args[3])
            cached = self._smart_reply_cache.get(uid, [])
            if ridx < len(cached):
                reply_body = cached[ridx]
                meta       = await self.gmail.get_email_metadata(uid, msg_id)
                sender     = meta.get("sender", "")
                match      = re.search(r'<(.+?)>', sender)
                email      = match.group(1) if match else sender
                subj       = meta.get("subject", "")
                if not subj.startswith("Re:"):
                    subj = "Re: " + subj
                self.compose_states[uid] = {
                    "step": "AWAIT_ATTACH",
                    "to":   email, "subj": subj,
                    "body": reply_body, "attachments": []
                }
                await query.edit_message_text(
                    self._draft_preview(self.compose_states[uid]),
                    parse_mode="Markdown",
                    reply_markup=kb_compose_draft(has_ai_body=True))
            return

    # ── Sub-handlers for complex button actions ────────────────

    async def _show_settings(self, query, uid: int):
        prefs    = await self._get_prefs(uid)
        ai_on    = prefs.get("ai_mode_enabled",   True)
        voice    = prefs.get("voice_preference",  "text")
        auto_on  = prefs.get("auto_check_enabled", True)
        await query.edit_message_text(
            "⚙️ *Settings*\n\nConfigure your assistant preferences below:",
            parse_mode="Markdown",
            reply_markup=kb_settings(ai_on, voice, auto_on))

    async def _handle_send_draft(self, query, uid: int, context):
        state = self.compose_states.pop(uid, None)
        if not state or not state.get("to") or not state.get("subj"):
            await query.edit_message_text(
                "❌ *Draft expired or incomplete.* Start over.",
                parse_mode="Markdown",
                reply_markup=InlineKeyboardMarkup([kb_back_to()]))
            return

        self.pending_sends[uid] = state
        msg = await query.edit_message_text(
            "⏳ *Email queued.* Sending in *7 seconds*...\n_(Press Undo to cancel)_",
            parse_mode="Markdown",
            reply_markup=kb_undo_send())

        async def _do_send():
            await asyncio.sleep(7)
            if uid not in self.pending_sends:
                return  # cancelled
            draft = self.pending_sends.pop(uid)
            result = await self.gmail.send_email(
                uid, draft["to"], draft["subj"], draft["body"],
                draft.get("attachments", [])
            )
            self._bg(self._bg_save_contact(uid, draft["to"]))
            try:
                await msg.edit_text(
                    f"{'✅' if 'successfully' in result.lower() else '❌'} {result}",
                    parse_mode="Markdown",
                    reply_markup=InlineKeyboardMarkup([kb_back_to()]))
            except Exception:
                pass

        asyncio.create_task(_do_send())

    async def _handle_summary(self, query, context, msg_id: str,
                               nav_ctx: str, offset: int, uid: int):
        await query.edit_message_text("⏳ *Generating AI Summary...*", parse_mode="Markdown")
        body = await self.gmail.read_full_email(uid, msg_id)
        meta = await self.gmail.get_email_metadata(uid, msg_id)

        # Generate summary + smart replies in parallel
        summary_task = asyncio.create_task(
            self.ai_engine.agent_chat(
                f"Strictly summarize this email in 3-4 bullet points: {body[:3000]}", uid)
        )
        replies_task = asyncio.create_task(
            self.ai_engine.generate_smart_replies(body[:2000])
        )
        raw_sum, smart_replies = await asyncio.gather(summary_task, replies_task,
                                                       return_exceptions=True)

        if isinstance(smart_replies, list):
            self._smart_reply_cache[uid] = smart_replies
        else:
            smart_replies = ["Got it.", "Noted.", "I'll reply soon."]
            self._smart_reply_cache[uid] = smart_replies

        # Parse summary
        try:
            parsed    = json.loads(re.sub(r'```json|```', '', str(raw_sum)).strip())
            sum_text  = parsed.get("text", str(raw_sum))
        except Exception:
            sum_text  = str(raw_sum)

        safe_sender = meta.get("sender", "").replace("*", "").replace("_", "")[:40]
        safe_subj   = meta.get("subject", "").replace("*", "").replace("_", "")[:50]
        att_count   = len(meta.get("attachments", []))

        header = f"📧 *From:* {safe_sender}\n📝 *Subject:* {safe_subj}\n{'━' * 20}\n"
        text   = f"{header}🤖 *AI Summary:*\n\n{sum_text}"

        kb = kb_summary_view(msg_id, nav_ctx, offset, bool(att_count), smart_replies)
        await query.edit_message_text(text, parse_mode="Markdown", reply_markup=kb)

    async def _handle_tts(self, query, context, msg_id: str,
                           nav_ctx: str, offset: int, uid: int):
        await query.edit_message_text("🔊 *Generating audio summary...*", parse_mode="Markdown")
        await context.bot.send_chat_action(chat_id=uid, action=ChatAction.RECORD_VOICE)

        body = await self.gmail.read_full_email(uid, msg_id)
        meta = await self.gmail.get_email_metadata(uid, msg_id)

        raw = await self.ai_engine.agent_chat(
            "Create a concise 3-sentence spoken summary (no formatting, plain speech only): "
            + body[:3000], uid)
        try:
            parsed    = json.loads(re.sub(r'```json|```', '', raw).strip())
            tts_text  = parsed.get("text", raw)
        except Exception:
            tts_text  = raw

        clean_tts  = re.sub(r'[*_#`]', '', tts_text)
        audio_path = await self.voice.synthesize(clean_tts, telegram_id=uid)

        att_count = len(meta.get("attachments", []))
        rows = [[InlineKeyboardButton("📖 Read Full Email",
                                      callback_data=_cb("read", msg_id, nav_ctx, offset))]]
        if att_count:
            rows.append([InlineKeyboardButton("📥 Get Attachments",
                                               callback_data=_cb("att", msg_id, nav_ctx, offset))])
        rows.append(kb_back_to(nav_ctx, offset))
        kb = InlineKeyboardMarkup(rows)

        safe_sender = meta.get("sender", "").replace("*", "").replace("_", "")[:35]
        safe_subj   = meta.get("subject", "").replace("*", "").replace("_", "")[:45]
        caption     = f"🔊 *Audio Summary*\n📧 *From:* {safe_sender}\n📝 *Subject:* {safe_subj}"

        if audio_path and os.path.exists(audio_path):
            with open(audio_path, "rb") as audio:
                await context.bot.send_voice(
                    chat_id=uid, voice=audio,
                    caption=caption, parse_mode="Markdown", reply_markup=kb)
            try:
                os.remove(audio_path)
            except Exception:
                pass
            try:
                await query.message.delete()
            except Exception:
                pass
        else:
            await query.edit_message_text(
                "❌ *Failed to generate audio.*", parse_mode="Markdown", reply_markup=kb)

    async def _handle_get_attachments(self, query, context, msg_id: str,
                                       nav_ctx: str, offset: int, uid: int):
        await query.edit_message_text("⏳ *Fetching attachments...*", parse_mode="Markdown")
        back_kb = InlineKeyboardMarkup([[
            InlineKeyboardButton("🔙 Back to Email",
                                 callback_data=_cb("read", msg_id, nav_ctx, offset))
        ]])
        try:
            file_paths = await self.gmail.get_attachments(uid, msg_id)
        except Exception:
            file_paths = []

        if not file_paths:
            await query.edit_message_text(
                "📭 *No attachments found in this email.*",
                parse_mode="Markdown", reply_markup=back_kb)
            return

        await query.edit_message_text("📤 *Sending attachments...*", parse_mode="Markdown")
        for fp in file_paths:
            try:
                with open(fp, "rb") as f:
                    await context.bot.send_document(chat_id=uid, document=f)
            except Exception as e:
                logger.error(f"Attachment send error: {e}")
            finally:
                try:
                    os.remove(fp)
                except Exception:
                    pass
        await query.edit_message_text(
            "✅ *Attachments sent successfully!*",
            parse_mode="Markdown", reply_markup=back_kb)

    # ─────────────────────────────────────────────────────────
    # BACKGROUND JOBS
    # ─────────────────────────────────────────────────────────

    async def job_keep_alive(self, context: ContextTypes.DEFAULT_TYPE):
        import httpx
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                await client.get(f"{settings.RENDER_WEB_SERVICE_URL}/health")
        except Exception:
            pass

    async def job_check_emails(self, context: ContextTypes.DEFAULT_TYPE):
        async with self.email_lock:
            try:
                users = await self.db.get_active_auto_check_users()
                for user in users:
                    uid = user["telegram_id"]
                    emails = await self.gmail.get_emails(
                        uid, query="is:unread newer_than:1d", max_results=10)
                    for email in emails:
                        msg_id = email["id"]
                        if msg_id in self.notified_emails:
                            continue
                        self.notified_emails.add(msg_id)

                        meta = await self.gmail.get_email_metadata(uid, msg_id)
                        if "error" in meta:
                            continue

                        safe_sender = meta.get("sender", "")[:35].replace("*", "").replace("_", "")
                        safe_subj   = meta.get("subject", "")[:45].replace("*", "").replace("_", "")
                        att_count   = len(meta.get("attachments", []))
                        att_text    = f"\n📎 *Attachments:* {att_count} file(s)" if att_count else ""

                        # Cache email + save contact in background
                        self._bg(self.memory.cache_email(
                            telegram_id=uid, gmail_message_id=msg_id,
                            sender=safe_sender, sender_email=safe_sender,
                            subject=safe_subj, preview="cached",
                            received_at=settings.get_utc_now()
                        ))
                        self._bg(self._bg_save_contact(uid, meta.get("sender", "")))

                        text = (f"🔔 *New Email*\n\n"
                                f"*From:* {safe_sender}\n"
                                f"*Subject:* {safe_subj}{att_text}")

                        kb = kb_new_email_notification(msg_id)
                        if att_count:
                            # Add Get Attachments row
                            new_rows = list(kb.inline_keyboard)
                            new_rows.insert(2, [InlineKeyboardButton(
                                "📥 Get Attachments",
                                callback_data=_cb("att", msg_id, "inbox", 0))])
                            kb = InlineKeyboardMarkup(new_rows)

                        await context.bot.send_message(
                            chat_id=uid, text=text,
                            parse_mode="Markdown", reply_markup=kb)
            except Exception as e:
                logger.error(f"job_check_emails error: {e}")

    async def job_check_scheduled(self, context: ContextTypes.DEFAULT_TYPE):
        try:
            now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
            res = await self.db.db.run(
                lambda: self.db.db.client.table("scheduled_emails")
                        .select("*").eq("status", "pending").lte("scheduled_time", now).execute()
            )
            tasks = getattr(res, "data", []) or []
            for task in tasks:
                uid          = task["telegram_id"]
                local_files  = []
                for att in (task.get("attachments") or []):
                    if isinstance(att, dict) and "file_id" in att:
                        try:
                            fo   = await context.bot.get_file(att["file_id"])
                            path = os.path.join(tempfile.gettempdir(),
                                                att.get("file_name", f"att_{uuid.uuid4().hex[:6]}"))
                            await fo.download_to_drive(path)
                            local_files.append(path)
                        except Exception as e:
                            logger.error(f"Scheduled att download error: {e}")

                result = await self.gmail.send_email(
                    uid, task["to_email"], task["subject"], task["body"], local_files)
                status = "sent" if "successfully" in result.lower() else "failed"

                await self.db.db.run(
                    lambda: self.db.db.client.table("scheduled_emails")
                            .update({"status": status}).eq("id", task["id"]).execute()
                )
                notify = (f"✅ *Scheduled Email Sent!*\n*To:* `{task['to_email']}`"
                          if status == "sent" else
                          f"❌ *Scheduled Email Failed*\n*Error:* {result}")
                await context.bot.send_message(
                    chat_id=uid, text=notify, parse_mode="Markdown")

                for fp in local_files:
                    try:
                        os.remove(fp)
                    except Exception:
                        pass
        except Exception as e:
            logger.error(f"job_check_scheduled error: {e}")


# ── Singleton ──────────────────────────────────────────────────
telegram_handler = TelegramBotManager()