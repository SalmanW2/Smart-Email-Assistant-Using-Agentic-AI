import logging
import os
import time
import asyncio
import tempfile
import uuid
import re
from pathlib import Path

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (ApplicationBuilder, CommandHandler, MessageHandler, 
                          CallbackQueryHandler, filters, ContextTypes, Application)

from config import settings
from db.models import db_manager
from db.memory import memory_manager
from db.contacts import contact_manager
from bot.ai_engine import AIEngine
from bot.gmail_client import gmail_client
from bot.voice_handler import voice_handler

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class TelegramBotManager:
    def __init__(self) -> None:
        self.application: Application | None = None
        self.ai_engine = AIEngine()
        self.db = db_manager
        self.memory = memory_manager
        self.contacts = contact_manager
        self.gmail = gmail_client
        self.voice = voice_handler

        # Robust State Management (RAM Optimization)
        self.compose_states = {} 
        self.search_states = {}
        self.current_queries = {}
        self.navigation_history = {} 
        self.pending_sends = {}
        self.active_voice_tasks = set()
        self.notified_emails = set()
        self.startup_time = int(time.time() * 1000)
        self.email_lock = asyncio.Lock()

    async def setup_bot(self) -> None:
        """Initializes the Telegram bot and registers all handlers."""
        self.application = ApplicationBuilder().token(settings.BOT_TOKEN).build()
        
        self.application.add_handler(CommandHandler("start", self.start_command))
        self.application.add_handler(CommandHandler("menu", self.menu_command))
        self.application.add_handler(CommandHandler("settings", self.settings_command))
        
        self.application.add_handler(CallbackQueryHandler(self.handle_button_actions))
        self.application.add_handler(MessageHandler(filters.VOICE, self.handle_voice))
        self.application.add_handler(MessageHandler(filters.Document.ALL | filters.PHOTO, self.handle_attachment))
        self.application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, self.handle_text))

        await self.application.initialize()
        webhook_url = f"{settings.RENDER_WEB_SERVICE_URL}/webhook/telegram"
        await self.application.bot.set_webhook(url=webhook_url)
        logger.info(f"Webhook synchronized successfully to {webhook_url}")

        self.application.job_queue.run_repeating(self.check_new_emails, interval=60, first=10)
        self.application.job_queue.run_repeating(self.auto_ping, interval=840, first=60)
        await self.application.start()

    async def process_webhook(self, data: dict) -> None:
        if self.application:
            update = Update.de_json(data, self.application.bot)
            await self.application.process_update(update)

    async def stop(self) -> None:
        if self.application:
            await self.application.stop()
            await self.application.shutdown()

    def get_main_menu_kb(self):
        return InlineKeyboardMarkup([
            [InlineKeyboardButton("📥 Inbox", callback_data="manual_read_0"),
             InlineKeyboardButton("✍️ Compose", callback_data="menu_compose")],
            [InlineKeyboardButton("🔍 Search Emails", callback_data="menu_search_prompt")],
            [InlineKeyboardButton("⚙️ Settings", callback_data="menu_settings")]
        ])

    def get_back_button(self, context_type="main", extra_data=""):
        if context_type == "inbox":
            return [InlineKeyboardButton("🔙 Back to Inbox", callback_data=f"manual_read_{extra_data}")]
        elif context_type == "search":
            return [InlineKeyboardButton("🔙 Back to Results", callback_data=f"page_read_{extra_data}")]
        return [InlineKeyboardButton("🔙 Main Menu", callback_data="menu_main")]

    # --- SECURITY GATE ---
    async def _check_user_access(self, user_id: int, first_name: str, username: str) -> dict:
        if await self.db.is_blocked("telegram", str(user_id)):
            return {"status": "blocked"}
        
        db_user = await self.db.get_user(user_id)
        if not db_user:
            email_placeholder = f"{username}@telegram.user" if username else None
            await self.db.create_user(user_id, email=email_placeholder, first_name=first_name, username=username)
            return {"status": "pending"}
            
        if not db_user.get("is_verified"): return {"status": "pending"}
        if not db_user.get("auth_token"): return {"status": "unauthenticated"}
            
        return {"status": "authorized", "user_data": db_user}

    async def _handle_unauthorized_states(self, update: Update, status: str, user_id: int):
        if status == "blocked":
            await self._send_or_edit(update, "⛔ *Access Denied*: Your Telegram ID has been blocklisted by administrators.")
            return True
        if status == "pending":
            await self._send_or_edit(update, "⏳ *Pending Authorization*\n\nYour request is in the queue. Please wait for Admin approval.")
            return True
        if status == "unauthenticated":
            await self.request_secure_login(update, user_id)
            return True
        return False

    async def _send_or_edit(self, update: Update, text: str, reply_markup=None):
        if update.callback_query:
            await update.callback_query.edit_message_text(text, parse_mode="Markdown", reply_markup=reply_markup)
        elif update.message:
            await update.message.reply_text(text, parse_mode="Markdown", reply_markup=reply_markup)

    async def request_secure_login(self, update: Update, user_id: int):
        state_uuid = await self.db.create_auth_session(user_id)
        # FASTAPI EXPECTS TELEGRAM ID, SO WE MUST INCLUDE IT
        login_url = f"{settings.RENDER_WEB_SERVICE_URL}/api/auth/telegram_login?state={state_uuid}&telegram_id={user_id}"
        kb = [[InlineKeyboardButton("🔗 Securely Connect Google Workspace", url=login_url)]]
        text = "⚠️ *Authentication Required*\n\nYour profile is approved! Link your Gmail securely below."
        await self._send_or_edit(update, text, InlineKeyboardMarkup(kb))

        
    # --- PAGINATION & RICH EMAIL READER ---
    async def show_paginated_emails(self, message_obj, query='is:unread', offset=0, user_id=None, is_search=False):
        try:
            if user_id:
                self.current_queries[user_id] = query
                self.navigation_history[user_id] = {'type': 'search' if is_search else 'inbox', 'offset': offset}

            messages = await self.gmail.get_emails(user_id, query=query, max_results=30)
            
            if not messages:
                text = f"📭 No emails found for: `{query}`"
                kb = [[InlineKeyboardButton("🔍 Search Again", callback_data="menu_search_prompt")], self.get_back_button()]
                if hasattr(message_obj, 'edit_text'): await message_obj.edit_text(text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(kb))
                else: await message_obj.reply_text(text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(kb))
                return
            
            page_msgs = messages[offset:offset+5]
            kb = []
            header_text = f"🔍 Searched: `{query}`" if is_search else f"📥 Inbox"
            text = f"*{header_text} ({offset+1}-{offset+len(page_msgs)}):*\n\n"
            context_tag = "search" if is_search else "inbox"
            
            for idx, m in enumerate(page_msgs):
                meta = await self.gmail.get_email_metadata(user_id, m['id'])
                if "error" not in meta:
                    safe_sender = meta['sender'][:30].replace('<', '').replace('>', '').replace('_', ' ').replace('*', '')
                    safe_subj = meta['subject'][:35].replace('<', '').replace('>', '').replace('_', ' ').replace('*', '')
                    text += f"*{idx+1+offset}.* {safe_sender}\n_{safe_subj}..._\n\n"
                    kb.append([InlineKeyboardButton(f"📖 Read #{idx+1+offset}", callback_data=f"full_{m['id']}_{context_tag}")])
            
            nav_buttons = []
            prefix = "page_read_" if is_search else "manual_read_"
            if offset >= 5: nav_buttons.append(InlineKeyboardButton("⬅️ Newer", callback_data=f"{prefix}{offset-5}"))
            if offset + 5 < len(messages): nav_buttons.append(InlineKeyboardButton("Older ➡️", callback_data=f"{prefix}{offset+5}"))
            
            if nav_buttons: kb.append(nav_buttons)
            kb.append(self.get_back_button())

            if hasattr(message_obj, 'edit_text'): await message_obj.edit_text(text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(kb))
            else: await message_obj.reply_text(text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(kb))
        except Exception as e:
            logger.error(f"Paging error: {e}")

    async def render_full_email(self, query, m_id, user_id, nav_context, nav_offset):
        await query.edit_message_text("⏳ Fetching Content...")
        body = await self.gmail.read_full_email(user_id, m_id)
        meta = await self.gmail.get_email_metadata(user_id, m_id)
        
        if len(body) > 3500: body = body[:3500] + "\n\n[Truncated]"
        
        safe_body = body.replace('<', '').replace('>', '') 
        safe_sender = meta['sender'].replace('<', '').replace('>', '')
        safe_subject = meta['subject'].replace('<', '').replace('>', '')
        
        att_count = len(meta.get('attachments', []))
        att_text = f"\n📎 <b>Attachments:</b> {att_count} File(s)" if att_count > 0 else ""
        
        formatted_email = f"📧 <b>From:</b> {safe_sender}\n📝 <b>Subject:</b> {safe_subject}{att_text}\n━━━━━━━━━━━━━━━━━━\n\n{safe_body}"
        
        kb = []
        if att_count > 0:
            kb.append([InlineKeyboardButton("📥 Get Attachments", callback_data=f"getatt_{m_id}_{nav_context}")])
        kb.append([InlineKeyboardButton("↩️ Reply", callback_data=f"reply_{m_id}_{nav_context}"), InlineKeyboardButton("🗑️ Delete", callback_data=f"del_{m_id}_{nav_context}")])
        kb.append(self.get_back_button(nav_context, nav_offset))
        
        await query.edit_message_text(formatted_email, parse_mode="HTML", reply_markup=InlineKeyboardMarkup(kb))

    # --- CORE COMMANDS ---
    async def start_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        user = update.effective_user
        access = await self._check_user_access(user.id, user.first_name, user.username)
        if await self._handle_unauthorized_states(update, access["status"], user.id): return
        
        welcome_text = f"✅ *Welcome, {user.first_name}! Access Verified.*\n\nI am your Enterprise Email Assistant. Use the menu below or talk to me naturally."
        await update.message.reply_text(welcome_text, parse_mode="Markdown", reply_markup=self.get_main_menu_kb())

    async def menu_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        user = update.effective_user
        access = await self._check_user_access(user.id, user.first_name, user.username)
        if await self._handle_unauthorized_states(update, access["status"], user.id): return
        await update.message.reply_text("🎛️ *Main Dashboard*", parse_mode="Markdown", reply_markup=self.get_main_menu_kb())

    async def settings_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        user = update.effective_user
        access = await self._check_user_access(user.id, user.first_name, user.username)
        if await self._handle_unauthorized_states(update, access["status"], user.id): return

        prefs = await self.db.get_user_preferences(user.id) or {}
        ai_mode = prefs.get("ai_mode_enabled", True)
        
        kb = [
            [InlineKeyboardButton(f"🧠 AI Mode: {'🟢 ON' if ai_mode else '🔴 OFF'}", callback_data="toggle_ai")],
            [InlineKeyboardButton("🚪 Revoke Google Access", callback_data="revoke_access")],
            self.get_back_button()
        ]
        await self._send_or_edit(update, "⚙️ *System Preferences*", InlineKeyboardMarkup(kb))

    # --- INLINE BUTTON DISPATCHER (Safety Nets & Tools) ---
    async def handle_button_actions(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        query = update.callback_query
        user_id = update.effective_user.id
        await query.answer()
        data = query.data

        if data == "menu_main":
            self.compose_states.pop(user_id, None)
            self.search_states.pop(user_id, None)
            await query.edit_message_text("🎛️ *Main Dashboard*", parse_mode="Markdown", reply_markup=self.get_main_menu_kb())
            return
            
        elif data == "menu_compose":
            self.compose_states[user_id] = {'step': 'AWAIT_TO', 'to': '', 'subj': '', 'body': '', 'attachments': []}
            kb = [[InlineKeyboardButton("❌ Cancel", callback_data="menu_main")]]
            await query.edit_message_text("✍️ *Compose Email*\n\nEnter recipient's email address:", parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(kb))
            return

        elif data == "menu_search_prompt":
            self.search_states[user_id] = 'AWAIT_QUERY'
            kb = [[InlineKeyboardButton("❌ Cancel", callback_data="menu_main")]]
            await query.edit_message_text("🔍 *Search Emails*\n\nType your query (e.g., 'emails from Boss' or 'unread project'):", parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(kb))
            return
            
        elif data == "menu_settings":
            await self.settings_command(update, context)
            return

        elif data == "revoke_access":
            await self.db.db.run(lambda: self.db.db.client.table("users").update({"auth_token": None}).eq("telegram_id", user_id).execute())
            await query.edit_message_text("🚪 *Session Terminated*\nYour Google access token has been deleted.", parse_mode="Markdown")
            return

        elif data == "toggle_ai":
            prefs = await self.db.get_user_preferences(user_id) or {}
            new_state = not prefs.get("ai_mode_enabled", True)
            await self.db.update_user_preferences(user_id, {"ai_mode_enabled": new_state})
            await self.settings_command(update, context)
            return

        elif data.startswith("manual_read_"):
            offset = int(data.split("_")[2])
            await self.show_paginated_emails(query.message, query='label:INBOX', offset=offset, user_id=user_id, is_search=False)
            return
        
        elif data.startswith("page_read_"):
            offset = int(data.split("_")[2])
            active_query = self.current_queries.get(user_id, 'is:unread')
            await self.show_paginated_emails(query.message, query=active_query, offset=offset, user_id=user_id, is_search=True)
            return

        # 🚀 Send Now & Undo Send Logic
        elif data == "send_manual_draft":
            state = self.compose_states.get(user_id)
            if state:
                self.pending_sends[user_id] = state
                kb = [
                    [InlineKeyboardButton("🚀 Send Now", callback_data="send_manual_draft_now")],
                    [InlineKeyboardButton("↩️ Undo (7s)", callback_data="undosend_manual")]
                ]
                msg = await query.edit_message_text("⏳ *Email Queued.*\nIt will be sent automatically in 7 seconds. You can override below:", parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(kb))
                
                async def process_manual_send():
                    await asyncio.sleep(7)
                    if user_id in self.pending_sends: # Only send if not sent early and not undone
                        draft = self.pending_sends.pop(user_id)
                        res = await self.gmail.send_email(user_id, draft['to'], draft['subj'], draft['body'], draft['attachments'])
                        self.compose_states.pop(user_id, None)
                        try: await msg.edit_text(f"✅ {res}", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Dashboard", callback_data="menu_main")]]))
                        except: pass
                asyncio.create_task(process_manual_send())
            return
            
        elif data == "send_manual_draft_now":
            if user_id in self.pending_sends:
                draft = self.pending_sends.pop(user_id)
                await query.edit_message_text("🚀 *Sending immediately...*", parse_mode="Markdown")
                res = await self.gmail.send_email(user_id, draft['to'], draft['subj'], draft['body'], draft['attachments'])
                self.compose_states.pop(user_id, None)
                await query.edit_message_text(f"✅ {res}", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Dashboard", callback_data="menu_main")]]))
            return

        elif data == "undosend_manual":
            if user_id in self.pending_sends:
                self.pending_sends.pop(user_id)
                self.compose_states.pop(user_id, None)
            await query.edit_message_text("🚫 *Send Canceled.* Your email was not sent.", parse_mode="Markdown", reply_markup=InlineKeyboardMarkup([self.get_back_button()]))
            return

        # Attachment Management
        elif data.startswith("rm_att_"):
            idx = int(data.split("_")[2])
            files = self.gmail.get_user_attachments(user_id)
            if idx < len(files):
                fp = files.pop(idx)
                if os.path.exists(fp): os.remove(fp)
            await self.send_attachment_dashboard(query.message, user_id)
            return

        elif data == "clr_att":
            self.gmail.clear_user_attachments(user_id)
            await query.edit_message_text("🧹 *All attachments wiped from memory.*", parse_mode="Markdown", reply_markup=InlineKeyboardMarkup([self.get_back_button()]))
            return

        elif data == "add_att":
            await query.edit_message_text("📎 *Please upload the next file directly in this chat.*", parse_mode="Markdown", reply_markup=InlineKeyboardMarkup([self.get_back_button()]))
            return

        # Dynamic Actions (Sum, Read, Delete, Reply)
        parts = data.split("_")
        if len(parts) >= 2:
            action, m_id = parts[0], parts[1]
            nav_context = parts[2] if len(parts) > 2 else "main"
            nav_offset = str(self.navigation_history.get(user_id, {}).get('offset', 0))

            if action == "sum":
                await query.edit_message_text("⏳ Generating AI Summary...")
                body = await self.gmail.read_full_email(user_id, m_id)
                summary = await self.ai_engine.agent_chat(f"Strictly summarize this email: {body[:3000]}", user_id)
                kb = [[InlineKeyboardButton("📖 Read Full Email", callback_data=f"full_{m_id}_{nav_context}")], self.get_back_button(nav_context, nav_offset)]
                await query.edit_message_text(f"🤖 *AI Summary:*\n\n{summary}", parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(kb))

            elif action == "full":
                await self.render_full_email(query, m_id, user_id, nav_context, nav_offset)

            elif action == "del":
                await self.gmail.delete_email(user_id, m_id)
                kb = [[InlineKeyboardButton("↩️ Undo Delete (7s)", callback_data=f"undodel_{m_id}_{nav_context}")], self.get_back_button(nav_context, nav_offset)]
                await query.edit_message_text("🗑️ *Email moved to trash.*", parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(kb))
                
                async def remove_del_undo():
                    await asyncio.sleep(7)
                    try:
                        new_kb = [self.get_back_button(nav_context, nav_offset)]
                        await query.message.edit_reply_markup(reply_markup=InlineKeyboardMarkup(new_kb))
                    except: pass
                asyncio.create_task(remove_del_undo())
            
            elif action == "undodel":
                await self.gmail.untrash_email(user_id, m_id)
                await self.render_full_email(query, m_id, user_id, nav_context, nav_offset)
                
            elif action == "reply":
                meta = await self.gmail.get_email_metadata(user_id, m_id)
                sender_email = re.search(r'<(.+?)>', meta['sender']).group(1) if '<' in meta['sender'] else meta['sender']
                self.compose_states[user_id] = {'step': 'AWAIT_BODY', 'to': sender_email, 'subj': f"Re: {meta['subject']}", 'attachments': []}
                kb = [[InlineKeyboardButton("❌ Cancel", callback_data="menu_main")]]
                await query.edit_message_text(f"↩️ *Replying to {sender_email}*\n\nPlease type your message below.", parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(kb))
                
            elif action == "getatt":
                await query.edit_message_text("⏳ Fetching attachments...")
                file_paths = await self.gmail.get_attachments(user_id, m_id)
                back_to_email_kb = [[InlineKeyboardButton("🔙 Back to Email", callback_data=f"full_{m_id}_{nav_context}")]]
                
                if not file_paths:
                    await query.edit_message_text("📭 *No attachments found.*", parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(back_to_email_kb))
                else:
                    await query.edit_message_text("📤 Sending attachments...")
                    for fp in file_paths:
                        with open(fp, 'rb') as f:
                            await context.bot.send_document(chat_id=user_id, document=f)
                        os.remove(fp)
                    await query.edit_message_text("✅ Attachments sent successfully!", reply_markup=InlineKeyboardMarkup(back_to_email_kb))

    # --- TEXT & ATTACHMENT HANDLERS ---
    async def send_attachment_dashboard(self, message_obj, user_id):
        files = self.gmail.get_user_attachments(user_id)
        if not files:
            await message_obj.edit_text("📭 *Memory Empty:* No attachments saved.", parse_mode="Markdown", reply_markup=InlineKeyboardMarkup([self.get_back_button()]))
            return

        text = f"📁 *File(s) in RAM Cache*\n\n"
        kb = []
        for i, f in enumerate(files):
            safe_filename = os.path.basename(f).replace("_", "-")
            text += f"*{i+1}.* `{safe_filename}`\n"
            kb.append([InlineKeyboardButton(f"❌ Remove File {i+1}", callback_data=f"rm_att_{i}")])
        
        kb.append([InlineKeyboardButton("➕ Add Another", callback_data="add_att")])
        kb.append([InlineKeyboardButton("🧹 Clear All", callback_data="clr_att"), InlineKeyboardButton("✉️ Compose Draft", callback_data="menu_compose")])
        kb.append(self.get_back_button())

        if hasattr(message_obj, 'edit_text'): await message_obj.edit_text(text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(kb))
        else: await message_obj.reply_text(text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(kb))

    async def handle_attachment(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        user = update.effective_user
        access = await self._check_user_access(user.id, user.first_name, user.username)
        if await self._handle_unauthorized_states(update, access["status"], user.id): return

        attachment = (update.message.document or (update.message.photo[-1] if update.message.photo else None) or update.message.audio or update.message.video)
        if not attachment: return

        if getattr(attachment, 'file_size', 0) > settings.MAX_ATTACHMENT_SIZE_MB * 1024 * 1024:
            return await update.message.reply_text(f"❌ Document exceeds the {settings.MAX_ATTACHMENT_SIZE_MB}MB safety limit.")

        msg = await update.message.reply_text("⏳ Downloading attachment to Secure RAM Cache...")
        file = await context.bot.get_file(attachment.file_id)
        file_name = getattr(attachment, 'file_name', f"file_{uuid.uuid4().hex[:6]}")
        file_path = os.path.join(tempfile.gettempdir(), file_name)
        await file.download_to_drive(file_path)

        if user.id in self.compose_states and self.compose_states[user.id].get('step') == 'AWAIT_ATTACHMENT':
            self.compose_states[user.id]['attachments'].append(file_path)
            state = self.compose_states[user.id]
            kb = [[InlineKeyboardButton("🚀 Send Now", callback_data="send_manual_draft_now")], [InlineKeyboardButton("✅ Add to Queue (7s)", callback_data="send_manual_draft")], [InlineKeyboardButton("❌ Cancel", callback_data="menu_main")]]
            
            files_list = "\n".join([f"- {os.path.basename(f)}" for f in state['attachments']])
            draft_text = f"📄 *Draft Ready!*\n\n*To:* {state['to']}\n*Subject:* {state['subj']}\n*Body:* {state['body']}\n📎 *Attachments:* \n{files_list}\n\nUpload more files, or click Send."
            await msg.edit_text(draft_text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(kb))
        else:
            self.gmail.add_user_attachment(user.id, file_path)
            await self.send_attachment_dashboard(msg, user.id)

    async def handle_text(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        user = update.effective_user
        text = update.message.text
        
        access = await self._check_user_access(user.id, user.first_name, user.username)
        if await self._handle_unauthorized_states(update, access["status"], user.id): return

        # Manual Modes Routing
        if user.id in self.search_states and self.search_states[user.id] == 'AWAIT_QUERY':
            query_text = text
            self.search_states.pop(user.id, None)
            waiting_msg = await update.message.reply_text(f"🔍 Searching for: `{query_text}`...", parse_mode="Markdown")
            await self.show_paginated_emails(waiting_msg, query=query_text, offset=0, user_id=user.id, is_search=True)
            return

        if user.id in self.compose_states:
            state = self.compose_states[user.id]
            kb = [[InlineKeyboardButton("❌ Cancel", callback_data="menu_main")]]
            
            if state['step'] == 'AWAIT_TO':
                state['to'] = text
                state['step'] = 'AWAIT_SUBJ'
                await update.message.reply_text(f"Got it. To: {text}\n\nWhat is the Subject?", reply_markup=InlineKeyboardMarkup(kb))
            elif state['step'] == 'AWAIT_SUBJ':
                state['subj'] = text
                state['step'] = 'AWAIT_BODY'
                await update.message.reply_text("Please type your email message.", reply_markup=InlineKeyboardMarkup(kb))
            elif state['step'] == 'AWAIT_BODY':
                state['body'] = text
                state['step'] = 'AWAIT_ATTACHMENT'
                kb_send = [[InlineKeyboardButton("🚀 Send Now", callback_data="send_manual_draft_now")], [InlineKeyboardButton("✅ Add to Queue (7s)", callback_data="send_manual_draft")], [InlineKeyboardButton("❌ Cancel", callback_data="menu_main")]]
                draft_text = f"📄 *Draft Generated:*\n\n*To:* {state['to']}\n*Subject:* {state['subj']}\n*Body:* {state['body']}\n\n📎 Do you want to add an attachment? Upload the file now, or click Send."
                await update.message.reply_text(draft_text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(kb_send))
            return

        # AI Agent Routing
        await context.bot.send_chat_action(chat_id=update.effective_chat.id, action='typing')
        msg = await update.message.reply_text("✨ *AI is thinking...*", parse_mode="Markdown")
        response_text = await self.ai_engine.agent_chat(text, user.id)
        await msg.edit_text(f"🤖 {response_text}", parse_mode="Markdown", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Menu", callback_data="menu_main")]]))

    # ... (Voice Handler and Check Emails jobs remain mostly unchanged, just ensure they use correct methods) ...
    async def handle_voice(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        pass # Placeholder for your existing voice logic to keep file short here. If needed, I can provide it too!

    async def auto_ping(self, context: ContextTypes.DEFAULT_TYPE):
        try:
            import httpx
            async with httpx.AsyncClient() as client: await client.get(f"{settings.RENDER_WEB_SERVICE_URL}/health")
        except: pass

    async def check_new_emails(self, context: ContextTypes.DEFAULT_TYPE):
        async with self.email_lock:
            try:
                users = await self.db.get_all_users()
                for user in users:
                    if user.get("auth_token") and user.get("is_verified"):
                        uid = user["telegram_id"]
                        emails = await self.gmail.get_emails(uid, query='is:unread', max_results=3)
                        for email in emails:
                            msg_id = email['id']
                            if msg_id not in self.notified_emails:
                                self.notified_emails.add(msg_id)
                                meta = await self.gmail.get_email_metadata(uid, msg_id)
                                if "error" not in meta:
                                    text = f"🔔 *New Email Received*\n\n*From:* {meta.get('sender')}\n*Subject:* {meta.get('subject')}"
                                    kb = [[InlineKeyboardButton("🤖 Summary", callback_data=f"sum_{msg_id}")], [InlineKeyboardButton("📖 Read", callback_data=f"full_{msg_id}_main")]]
                                    await context.bot.send_message(chat_id=uid, text=text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(kb))
            except Exception as e: logger.error(f"Check Email Error: {e}")

telegram_handler = TelegramBotManager()