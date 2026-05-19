import logging
import os
import time
import asyncio
import tempfile
import uuid
import re
import json
from pathlib import Path
from datetime import datetime, timezone

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.constants import ChatAction
from telegram.ext import (ApplicationBuilder, CommandHandler, MessageHandler, 
                          CallbackQueryHandler, filters, ContextTypes, Application)

from config import settings
from db.models import db_manager
from db.memory import memory_manager
from bot.ai_engine import AIEngine
from bot.gmail_client import GmailClient
from bot.voice_handler import voice_handler
from bot.contact_manager import contact_manager

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class TelegramBotManager:
    def __init__(self) -> None:
        self.application: Application | None = None
        self.ai_engine = AIEngine()
        self.db = db_manager
        self.memory = memory_manager
        self.gmail = GmailClient()
        self.voice = voice_handler
        self.contact_manager = contact_manager

        # --- Comprehensive State Management ---
        self.compose_states = {} 
        self.search_states = {}
        self.current_queries = {}
        self.navigation_history = {} 
        self.active_voice_tasks = set()
        self.notified_emails = set()
        self.pending_sends = {}
        self.email_lock = asyncio.Lock()
        self.startup_time = int(time.time() * 1000)

    def run_in_background(self, coro):
        loop = asyncio.get_event_loop()
        loop.create_task(coro)

    async def _bg_save_contact(self, telegram_id: int, email_address: str, name: str = ""):
        try:
            match = re.search(r'<(.+?)>', email_address)
            clean_email = match.group(1) if match else email_address
            if not name: 
                name = clean_email.split('@')[0]
            await self.db.db.run(lambda: self.db.db.client.table("contacts").upsert({
                "telegram_id": telegram_id, "contact_alias": name, "email_address": clean_email, "contact_name": name
            }, on_conflict="telegram_id,email_address").execute())
        except Exception: pass

    async def _bg_save_attachment_memory(self, telegram_id: int, file_id: str, file_name: str):
        try:
            await self.db.db.run(lambda: self.db.db.client.table("saved_attachments").insert({
                "telegram_id": telegram_id, "file_id": file_id, "file_name": file_name, "context_topic": "Uploaded via Chat"
            }).execute())
        except Exception: pass

    async def setup_bot(self):
        self.application = ApplicationBuilder().token(settings.BOT_TOKEN).build()
        self.application.add_handler(CommandHandler("start", self.start))
        self.application.add_handler(CommandHandler("menu", self.show_main_menu))
        self.application.add_handler(CallbackQueryHandler(self.handle_button_actions))
        self.application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, self.handle_text))
        self.application.add_handler(MessageHandler(filters.VOICE, self.handle_voice))
        self.application.add_handler(MessageHandler(filters.Document.ALL | filters.PHOTO | filters.VIDEO | filters.AUDIO, self.handle_attachment))

        await self.application.initialize()
        
        if self.application.job_queue:
            self.application.job_queue.run_repeating(self.check_new_emails, interval=60, first=10)
            self.application.job_queue.run_repeating(self.check_scheduled_emails, interval=60, first=30)
            self.application.job_queue.run_repeating(self.auto_ping, interval=840, first=60)
            
        await self.application.bot.set_webhook(url=f"{settings.RENDER_WEB_SERVICE_URL}/webhook/telegram")
        logger.info("Webhook synchronized successfully.")
        await self.application.start()

    async def process_webhook(self, data: dict):
        if self.application:
            update = Update.de_json(data, self.application.bot)
            await self.application.process_update(update)

    # ==========================================
    # SECURITY & ACCESS CONTROL
    # ==========================================
    async def _check_user_access(self, user_id: int, first_name: str, username: str) -> dict:
        if await self.db.is_blocked("telegram", str(user_id)): return {"status": "blocked"}
        db_user = await self.db.get_user(user_id)
        if not db_user:
            await self.db.create_user(user_id, email=None, first_name=first_name, username=username)
            return {"status": "pending"}
        if not db_user.get("is_verified"): return {"status": "pending"}
        if not db_user.get("auth_token"): return {"status": "unauthenticated"}
        return {"status": "authorized", "user_data": db_user}

    async def _handle_unauthorized_states(self, update: Update, status: str, user_id: int) -> bool:
        if status == "blocked":
            await self._send_or_edit(update, "🚫 *Access Revoked*\nYour account has been restricted.")
            return True
        elif status == "pending":
            await self._send_or_edit(update, "⏳ *Verification Pending*\nPlease wait for admin approval.")
            return True
        elif status == "unauthenticated":
            state_uuid = await self.db.create_auth_session(user_id)
            login_url = f"{settings.RENDER_WEB_SERVICE_URL}/api/auth/telegram_login?state={state_uuid}&telegram_id={user_id}"
            kb = [[InlineKeyboardButton("🔗 Connect Google Workspace", url=login_url)]]
            await self._send_or_edit(update, "⚠️ *Authentication Required*\nPlease link your Gmail to continue.", InlineKeyboardMarkup(kb))
            return True
        return False

    async def _send_or_edit(self, update: Update, text: str, reply_markup: InlineKeyboardMarkup | None = None):
        try:
            if update.callback_query: await update.callback_query.edit_message_text(text, parse_mode="Markdown", reply_markup=reply_markup)
            elif update.message: await update.message.reply_text(text, parse_mode="Markdown", reply_markup=reply_markup)
        except: pass

    def get_back_button(self, context="main", offset=0):
        if context == "search": return [InlineKeyboardButton("🔙 Back to Results", callback_data=f"search_page_{offset}")]
        elif context == "inbox": return [InlineKeyboardButton("🔙 Back to Inbox", callback_data=f"manual_read_{offset}")]
        return [InlineKeyboardButton("🔙 Main Dashboard", callback_data="menu_main")]

    # ==========================================
    # SMART AI RESPONSE PARSER
    # ==========================================
    async def _send_smart_ai_response(self, update: Update, context: ContextTypes.DEFAULT_TYPE, msg_obj, raw_ai_response: str, user_id: int, user_prefs: dict):
        try:
            clean_json = raw_ai_response.replace('```json', '').replace('```', '').strip()
            json_match = re.search(r'\{.*\}', clean_json, re.DOTALL)
            if json_match:
                clean_json = json_match.group(0)
            parsed_data = json.loads(clean_json)
            text_content = parsed_data.get("text", "Processing...")
            response_type = parsed_data.get("response_type", "text")
        except Exception:
            text_content = raw_ai_response
            response_type = "text"

        voice_pref = user_prefs.get("voice_preference", "text")

        if response_type == "voice" and voice_pref in ["voice", "both"]:
            await context.bot.send_chat_action(chat_id=user_id, action=ChatAction.RECORD_VOICE)
            clean_tts_text = re.sub(r'[*_#`]', '', text_content)
            audio_path = await self.voice.synthesize(clean_tts_text, telegram_id=user_id, preferred_method=user_prefs.get("preferred_tts_method", "google"))
            
            if audio_path and os.path.exists(audio_path):
                with open(audio_path, 'rb') as audio:
                    await msg_obj.reply_voice(voice=audio)
                os.remove(audio_path)
                
                if voice_pref == "both":
                    await msg_obj.edit_text(f"🤖 {text_content}", parse_mode="Markdown", reply_markup=InlineKeyboardMarkup([self.get_back_button()]))
                else:
                    await msg_obj.delete() 
                return
        
        await msg_obj.edit_text(f"🤖 {text_content}", parse_mode="Markdown", reply_markup=InlineKeyboardMarkup([self.get_back_button()]))

    # ==========================================
    # UI RENDERERS
    # ==========================================
    async def render_full_email(self, query, m_id, nav_context, nav_offset, user_id):
        await query.edit_message_text("⏳ Fetching...")
        body = await self.gmail.read_full_email(user_id, m_id)
        meta = await self.gmail.get_email_metadata(user_id, m_id)
        
        if len(body) > 3500: body = body[:3500] + "\n\n[Truncated]"
        
        safe_body = body.replace('<', '').replace('>', '') 
        safe_sender = meta.get('sender', '').replace('<', '').replace('>', '')
        safe_subject = meta.get('subject', '').replace('<', '').replace('>', '')
        
        url_pattern = re.compile(r'(https?://[^\s]+)')
        safe_body = url_pattern.sub(r'<a href="\1">🔗 Click Here</a>', safe_body)
        
        att_count = len(meta.get('attachments', []))
        att_text = f"\n📎 <b>Attachments:</b> {att_count} File(s)" if att_count > 0 else ""
        
        formatted_email = f"📧 <b>From:</b> {safe_sender}\n📝 <b>Subject:</b> {safe_subject}{att_text}\n━━━━━━━━━━━━━━━━━━\n\n{safe_body}"
        
        kb = []
        if att_count > 0:
            kb.append([InlineKeyboardButton("📥 Get Attachments", callback_data=f"getatt_{m_id}_{nav_context}_{nav_offset}")])
        kb.append([InlineKeyboardButton("↩️ Reply", callback_data=f"manual_reply_{m_id}_{nav_context}_{nav_offset}"), InlineKeyboardButton("🗑️ Trash", callback_data=f"manual_del_{m_id}_{nav_context}_{nav_offset}")])
        kb.append([InlineKeyboardButton("🤖 AI Summary", callback_data=f"sum_{m_id}_{nav_context}_{nav_offset}"), InlineKeyboardButton("🔊 Listen", callback_data=f"tts_sum_{m_id}_{nav_context}_{nav_offset}")])
        kb.append(self.get_back_button(nav_context, int(nav_offset)))
        
        await query.edit_message_text(formatted_email, parse_mode="HTML", reply_markup=InlineKeyboardMarkup(kb))

    async def send_attachment_dashboard(self, message_obj, user_id):
        files = self.gmail.get_user_attachments(user_id)
        if not files:
            text = "📭 *Memory Empty:* No files saved in current session."
            kb = [self.get_back_button()]
            if hasattr(message_obj, 'edit_text'): await message_obj.edit_text(text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(kb))
            else: await message_obj.reply_text(text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(kb))
            return

        text = f"📁 *Temporary File(s) Ready*\nTotal Files: {len(files)}\n\n"
        text += "💡 *Tip for AI:* To send these files, simply say: _'Send an email to Ali and attach the files.'_\n\n"
        kb = []
        for i, f in enumerate(files):
            safe_filename = os.path.basename(f).replace("_", "-").replace("*", "")
            text += f"*{i+1}.* `{safe_filename}`\n"
            kb.append([InlineKeyboardButton(f"❌ Remove File {i+1}", callback_data=f"rm_att_{i}")])
        
        kb.append([InlineKeyboardButton("➕ Add Another Attachment", callback_data="add_att")])
        kb.append([InlineKeyboardButton("🧹 Clear Session", callback_data="clr_att"), InlineKeyboardButton("✉️ Draft Email", callback_data="menu_compose")])
        kb.append(self.get_back_button())

        if hasattr(message_obj, 'edit_text'): await message_obj.edit_text(text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(kb))
        else: await message_obj.reply_text(text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(kb))

    async def show_paginated_emails(self, message_obj, query='is:unread', offset=0, user_id=None, is_search=False):
        try:
            if user_id:
                self.current_queries[user_id] = query
                self.navigation_history[user_id] = {'type': 'search' if is_search else 'inbox', 'offset': offset}

            safe_query = "in:inbox" if query == "label:INBOX" else query
            # Fetch offset + 3 to determine if there is a next page
            messages = await self.gmail.get_emails(user_id, query=safe_query, max_results=offset + 3)
            
            if not messages and offset == 0:
                text = f"📭 No emails found for: `{safe_query}`" if is_search else "📭 Your Inbox is empty."
                kb = [[InlineKeyboardButton("🔍 Search Again", callback_data="menu_search_prompt")], self.get_back_button()] if is_search else [self.get_back_button()]
                if hasattr(message_obj, 'edit_text'): await message_obj.edit_text(text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(kb))
                else: await message_obj.reply_text(text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(kb))
                return

            display_messages = messages[offset:offset+2]
            has_next = len(messages) > offset + 2
            
            output_lines = [f"🔍 *Results:* `{safe_query}`\n" if is_search else "📥 *Your Inbox:*\n"]
            kb = []
            nav_context = "search" if is_search else "inbox"

            for i, msg in enumerate(display_messages):
                meta = await self.gmail.get_email_metadata(user_id, msg['id'])
                if "error" in meta: continue
                sender = meta.get('sender', 'Unknown').replace('*', '').replace('_', '')
                subj = meta.get('subject', 'No Subject').replace('*', '').replace('_', '')
                
                output_lines.append(f"*{i+1+offset}.* {sender[:40]}\n_{subj[:50]}_\n")
                kb.append([InlineKeyboardButton(f"📖 Read {i+1+offset}", callback_data=f"full_{msg['id']}_{nav_context}_{offset}")])

            nav_row = []
            if offset > 0: nav_row.append(InlineKeyboardButton("⬅️ Prev", callback_data=f"{'search_page' if is_search else 'manual_read'}_{offset-2}"))
            if has_next: nav_row.append(InlineKeyboardButton("Next ➡️", callback_data=f"{'search_page' if is_search else 'manual_read'}_{offset+2}"))
            
            if nav_row: kb.append(nav_row)
            kb.append(self.get_back_button())

            final_text = "\n".join(output_lines)
            if hasattr(message_obj, 'edit_text'): await message_obj.edit_text(final_text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(kb))
            else: await message_obj.reply_text(final_text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(kb))

        except Exception as e:
            err_text = f"❌ Error retrieving emails: {str(e)}"
            if hasattr(message_obj, 'edit_text'): await message_obj.edit_text(err_text, reply_markup=InlineKeyboardMarkup([self.get_back_button()]))
            else: await message_obj.reply_text(err_text, reply_markup=InlineKeyboardMarkup([self.get_back_button()]))

    # ==========================================
    # CORE INTERACTION HANDLERS
    # ==========================================
    async def start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        user = update.effective_user
        access = await self._check_user_access(user.id, user.first_name, user.username)
        if await self._handle_unauthorized_states(update, access["status"], user.id): return
        
        kb = [
            [InlineKeyboardButton("📥 Inbox", callback_data="manual_read_0"),
             InlineKeyboardButton("✍️ Compose", callback_data="menu_compose")],
            [InlineKeyboardButton("🔍 Search Emails", callback_data="menu_search_prompt"),
             InlineKeyboardButton("📎 Attachments", callback_data="show_attachments")],
            [InlineKeyboardButton("⚙️ Settings", callback_data="menu_settings")]
        ]
        text = f"👋 *Welcome {user.first_name}!*\n\nI am your AI Email Assistant. Select an option below or send me a message/voice note."
        await self._send_or_edit(update, text, InlineKeyboardMarkup(kb))

    async def show_main_menu(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        kb = [
            [InlineKeyboardButton("📥 Inbox", callback_data="manual_read_0"),
             InlineKeyboardButton("✍️ Compose", callback_data="menu_compose")],
            [InlineKeyboardButton("🔍 Search Emails", callback_data="menu_search_prompt"),
             InlineKeyboardButton("📎 Attachments", callback_data="show_attachments")],
            [InlineKeyboardButton("⚙️ Settings", callback_data="menu_settings")]
        ]
        text = "🎛️ *Main Dashboard*\n\nWhat would you like to do next?"
        await self._send_or_edit(update, text, InlineKeyboardMarkup(kb))

    async def handle_text(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        user = update.effective_user
        access = await self._check_user_access(user.id, user.first_name, user.username)
        if await self._handle_unauthorized_states(update, access["status"], user.id): return

        user_id = user.id
        text = update.message.text

        if user_id in self.compose_states:
            state = self.compose_states[user_id]
            kb_cancel = [[InlineKeyboardButton("❌ Cancel", callback_data="cancel_compose")]]
            if state['step'] == 'AWAIT_TO':
                state['to'] = text; state['step'] = 'AWAIT_SUBJ'
                await update.message.reply_text(f"Got it. To: {text}\n📝 Subject?", reply_markup=InlineKeyboardMarkup(kb_cancel))
            elif state['step'] == 'AWAIT_SUBJ':
                state['subj'] = text; state['step'] = 'AWAIT_BODY'
                await update.message.reply_text("✍️ Message?", reply_markup=InlineKeyboardMarkup(kb_cancel))
            elif state['step'] == 'AWAIT_BODY':
                state['body'] = text; state['step'] = 'AWAIT_ATTACHMENT'; state['attachments'] = []
                kb_send = [[InlineKeyboardButton("🚀 Send Now", callback_data="send_manual_draft_direct")], [InlineKeyboardButton("❌ Cancel", callback_data="cancel_compose")]]
                await update.message.reply_text(f"📄 *Draft Ready*\n\n*To:* {state.get('to')}\n*Subject:* {state.get('subj')}\n\nUpload an attachment or click Send Now.", parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(kb_send))
            elif state['step'] == 'AWAIT_ATTACHMENT':
                await update.message.reply_text("Upload file or Send.", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🚀 Send Now", callback_data="send_manual_draft_direct")]]))
            return

        if user_id in self.search_states and self.search_states[user_id] == 'AWAIT_QUERY':
            query_text = text
            self.search_states.pop(user_id, None)
            waiting_msg = await update.message.reply_text(f"🔍 Searching...", parse_mode="Markdown")
            found_contacts = await self.contact_manager.find_contacts_by_name(user_id, query_text)
            if found_contacts:
                emails = [c['email_address'] for c in found_contacts]
                email_query = " OR ".join([f"from:{e}" for e in emails])
                query_text = f"({email_query}) OR {query_text}"
            await self.show_paginated_emails(waiting_msg, query=query_text, offset=0, user_id=user_id, is_search=True)
            return

        if not access["user_data"].get("ai_allowed", True):
            return await update.message.reply_text("🚫 *AI Access Restricted*.", parse_mode="Markdown")

        msg = await update.message.reply_text("✨ *Thinking...*", parse_mode="Markdown")
        await context.bot.send_chat_action(chat_id=user_id, action=ChatAction.TYPING)
        
        raw_ai_response = await self.ai_engine.agent_chat(text, user_id)
        user_prefs = await self.db.get_user_preferences(user_id) or {}
        await self._send_smart_ai_response(update, context, msg, raw_ai_response, user_id, user_prefs)

    async def handle_voice(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        user = update.effective_user
        access = await self._check_user_access(user.id, user.first_name, user.username)
        if await self._handle_unauthorized_states(update, access["status"], user.id): return
        if not access["user_data"].get("voice_allowed", True):
            return await update.message.reply_text("🚫 *Voice Access Restricted*.", parse_mode="Markdown")

        msg = await update.message.reply_text("🎙️ *Processing...*", parse_mode="Markdown")
        await context.bot.send_chat_action(chat_id=user.id, action=ChatAction.RECORD_VOICE)
        
        try:
            voice_file = await context.bot.get_file(update.message.voice.file_id)
            file_path = os.path.join(tempfile.gettempdir(), f"voice_{uuid.uuid4().hex}.ogg")
            await voice_file.download_to_drive(file_path)

            transcribed_text = await self.ai_engine.transcribe_audio(file_path, user.id)
            if os.path.exists(file_path): os.remove(file_path)

            if transcribed_text.startswith("System Error:") or "[Audio Unclear]" in transcribed_text:
                return await msg.edit_text("❌ *Audio Unclear.* Could you repeat that?", parse_mode="Markdown")

            task_id = str(int(time.time() * 1000))
            self.active_voice_tasks.add(task_id)

            kb = [[InlineKeyboardButton("❌ Cancel Process", callback_data=f"cancel_voice_{task_id}")]]
            await msg.edit_text(f"🗣️ *You:* _{transcribed_text}_\n\n✨ *Thinking...*", parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(kb))
            
            raw_ai_response = await self.ai_engine.agent_chat(transcribed_text, user.id)
            
            if task_id not in self.active_voice_tasks: return 
            self.active_voice_tasks.remove(task_id)

            user_prefs = await self.db.get_user_preferences(user.id) or {}
            await self._send_smart_ai_response(update, context, msg, raw_ai_response, user.id, user_prefs)

        except Exception as e:
            logger.error(f"Voice Error: {e}")
            await msg.edit_text("❌ *Error processing voice note.*", parse_mode="Markdown")

    async def handle_attachment(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        user = update.effective_user
        access = await self._check_user_access(user.id, user.first_name, user.username)
        if await self._handle_unauthorized_states(update, access["status"], user.id): return

        attachment = (update.message.document or (update.message.photo[-1] if update.message.photo else None) or update.message.audio or update.message.video)
        if not attachment: return

        if getattr(attachment, 'file_size', 0) > 20 * 1024 * 1024:
            return await update.message.reply_text("❌ *File is too large for Telegram (Max 20MB).* Provide a Drive link instead.", parse_mode="Markdown")

        msg = await update.message.reply_text("📥 *Downloading...*", parse_mode="Markdown")
        try:
            file_obj = await context.bot.get_file(attachment.file_id)
            ext = getattr(attachment, 'file_name', f"file_{uuid.uuid4().hex}").split('.')[-1]
            file_name = getattr(attachment, 'file_name', f"uploaded_file.{ext}")
            file_path = os.path.join(tempfile.gettempdir(), f"doc_{uuid.uuid4().hex}.{ext}")
            await file_obj.download_to_drive(file_path)

            if user.id in self.compose_states and self.compose_states[user.id].get('step') == 'AWAIT_ATTACHMENT':
                self.compose_states[user.id]['attachments'].append(file_path)
                kb = [[InlineKeyboardButton("🚀 Send Email Now", callback_data="send_manual_draft_direct")]]
                await msg.edit_text(f"📎 *File Attached:* {file_name}\nSend now or upload more.", parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(kb))
                return

            self.gmail.add_user_attachment(user.id, file_path)
            self.run_in_background(self._bg_save_attachment_memory(user.id, attachment.file_id, file_name))
            
            caption = update.message.caption or ""
            if caption:
                raw_ai_response = await self.ai_engine.agent_chat(f"[Uploaded Document: {file_name}] {caption}", user.id)
                user_prefs = await self.db.get_user_preferences(user.id) or {}
                await self._send_smart_ai_response(update, context, msg, raw_ai_response, user.id, user_prefs)
            else:
                await msg.delete()
                await self.send_attachment_dashboard(update.message, user.id)
        except Exception:
            await msg.edit_text("❌ *Failed to process the document.*", parse_mode="Markdown")

    # ==========================================
    # BACKGROUND JOBS & CRONS
    # ==========================================
    async def auto_ping(self, context: ContextTypes.DEFAULT_TYPE):
        import httpx
        try:
            async with httpx.AsyncClient() as client:
                await client.get(f"{settings.RENDER_WEB_SERVICE_URL}/health")
        except: pass

    async def check_new_emails(self, context: ContextTypes.DEFAULT_TYPE):
        async with self.email_lock:
            try:
                users = await self.db.get_active_auto_check_users()
                for user in users:
                    uid = user["telegram_id"]
                    # Fetching 10 to ensure we don't miss ones below top 3 if unread pile up
                    emails = await self.gmail.get_emails(uid, query='is:unread', max_results=10)
                    for email in emails:
                        msg_id = email['id']
                        if msg_id not in self.notified_emails:
                            self.notified_emails.add(msg_id)
                            meta = await self.gmail.get_email_metadata(uid, msg_id)
                            if "error" not in meta:
                                safe_sender = meta.get('sender', '').replace('*', '').replace('_', '')
                                safe_subject = meta.get('subject', '').replace('*', '').replace('_', '')
                                await self.memory.cache_email(telegram_id=uid, gmail_message_id=msg_id, sender=safe_sender, sender_email=safe_sender, subject=safe_subject, preview="Cached via background job", received_at=settings.get_utc_now())
                                self.run_in_background(self._bg_save_contact(uid, safe_sender))
                                
                                text = f"🔔 *New Email*\n\n*From:* {safe_sender[:30]}\n*Subject:* {safe_subject[:40]}"
                                kb = [
                                    [InlineKeyboardButton("📖 Read", callback_data=f"full_{msg_id}_inbox_0")],
                                    [InlineKeyboardButton("🤖 AI Summary", callback_data=f"sum_{msg_id}_inbox_0"),
                                     InlineKeyboardButton("🔊 Listen Summary", callback_data=f"tts_sum_{msg_id}_inbox_0")]
                                ]
                                await context.bot.send_message(chat_id=uid, text=text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(kb))
            except Exception: pass

    async def check_scheduled_emails(self, context: ContextTypes.DEFAULT_TYPE):
        try:
            current_utc = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
            result = await self.db.db.run(lambda: self.db.db.client.table("scheduled_emails").select("*").eq("status", "pending").lte("scheduled_time", current_utc).execute())
            pending_emails = getattr(result, 'data', []) if result else []
            
            for task in pending_emails:
                uid = task['telegram_id']
                attachments = task.get('attachments', [])
                local_files = []
                
                for att in attachments:
                    if isinstance(att, dict) and "file_id" in att:
                        try:
                            file_obj = await context.bot.get_file(att["file_id"])
                            path = os.path.join(tempfile.gettempdir(), att.get("file_name", "attached_file"))
                            await file_obj.download_to_drive(path)
                            local_files.append(path)
                        except Exception as e:
                            logger.error(f"Failed to download scheduled attachment: {e}")

                res = await self.gmail.send_email(uid, task['to_email'], task['subject'], task['body'], local_files)
                status = "sent" if "successfully" in res.lower() else "failed"
                await self.db.db.run(lambda: self.db.db.client.table("scheduled_emails").update({"status": status}).eq("id", task['id']).execute())
                
                msg = f"✅ *Scheduled Email Sent!*\n*To:* {task['to_email']}" if status == "sent" else f"❌ *Scheduled Email Failed!*\n*Error:* {res}"
                await context.bot.send_message(chat_id=uid, text=msg, parse_mode="Markdown")
                
                for path in local_files:
                    if os.path.exists(path): os.remove(path)
        except Exception: pass

    # ==========================================
    # INLINE KEYBOARD ACTIONS (Buttons)
    # ==========================================
    async def handle_button_actions(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        query = update.callback_query
        user_id = query.from_user.id
        data = query.data
        try: await query.answer()
        except: pass

        if data == "menu_main":
            self.compose_states.pop(user_id, None)
            self.search_states.pop(user_id, None)
            await self.show_main_menu(update, context)

        elif data == "action_logout":
            await self.db.db.run(lambda: self.db.db.client.table("users").update({"auth_token": None}).eq("telegram_id", user_id).execute())
            self.gmail.clear_user_attachments(user_id)
            await query.edit_message_text("✅ *Logged out successfully.*\n\nSend /start to connect a new account.", parse_mode="Markdown")

        elif data == "show_attachments":
            await self.send_attachment_dashboard(query.message, user_id)

        elif data.startswith("manual_read_"):
            offset = int(data.split('_')[2])
            await self.show_paginated_emails(query.message, query='label:INBOX', offset=offset, user_id=user_id, is_search=False)

        elif data.startswith("search_page_"):
            offset = int(data.split('_')[2])
            q = self.current_queries.get(user_id, 'is:unread')
            await self.show_paginated_emails(query.message, query=q, offset=offset, user_id=user_id, is_search=True)

        elif data == "menu_search_prompt":
            self.search_states[user_id] = 'AWAIT_QUERY'
            await query.edit_message_text("🔍 Please type your search query (e.g., 'from:ali' or 'project'):", reply_markup=InlineKeyboardMarkup([self.get_back_button()]))

        elif data == "menu_compose":
            self.compose_states[user_id] = {'step': 'AWAIT_TO'}
            await query.edit_message_text("✉️ *Compose Mode*\nPlease type the recipient's email address:", parse_mode="Markdown", reply_markup=InlineKeyboardMarkup([self.get_back_button()]))

        elif data == "cancel_compose":
            self.compose_states.pop(user_id, None)
            self.search_states.pop(user_id, None)
            self.pending_sends.pop(user_id, None)
            await query.edit_message_text("🚫 *Process Canceled*\n\nThe action was safely terminated.", parse_mode="Markdown", reply_markup=InlineKeyboardMarkup([self.get_back_button()]))

        elif data.startswith("cancel_voice_"):
            task_id = data.split("_")[2]
            if task_id in self.active_voice_tasks:
                self.active_voice_tasks.remove(task_id)
            await query.edit_message_text("🚫 *Process Canceled*\n\nVoice command execution halted.", parse_mode="Markdown", reply_markup=InlineKeyboardMarkup([self.get_back_button()]))

        elif data.startswith("rm_att_"):
            idx = int(data.split("_")[2])
            files = self.gmail.get_user_attachments(user_id)
            if idx < len(files):
                fp = files.pop(idx)
                if os.path.exists(fp): os.remove(fp)
            await self.send_attachment_dashboard(query.message, user_id)

        elif data == "clr_att":
            self.gmail.clear_user_attachments(user_id)
            await query.edit_message_text("🧹 *All temporary session files have been securely wiped.*", parse_mode="Markdown", reply_markup=InlineKeyboardMarkup([self.get_back_button()]))

        elif data == "add_att":
            self.compose_states[user_id] = self.compose_states.get(user_id, {'step': 'AWAIT_ATTACHMENT', 'attachments': []})
            self.compose_states[user_id]['step'] = 'AWAIT_ATTACHMENT'
            await query.edit_message_text("📎 *Ready for next file.*\nPlease upload the document, photo, or audio directly in this chat now.", parse_mode="Markdown", reply_markup=InlineKeyboardMarkup([self.get_back_button()]))

        elif data == "send_manual_draft_direct":
            state = self.compose_states.pop(user_id, None)
            if not state: return await query.edit_message_text("❌ Draft expired.", reply_markup=InlineKeyboardMarkup([self.get_back_button()]))
            
            self.pending_sends[user_id] = state
            kb = [[InlineKeyboardButton("↩️ Undo Send", callback_data="undosend_manual")], self.get_back_button()]
            msg = await query.edit_message_text("⏳ *Email queued.* Sending in 7 seconds...", parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(kb))
            
            async def process_manual_send():
                await asyncio.sleep(7)
                if user_id in self.pending_sends:
                    draft = self.pending_sends.pop(user_id)
                    res = await self.gmail.send_email(user_id, draft['to'], draft['subj'], draft['body'], draft.get('attachments', []))
                    self.run_in_background(self._bg_save_contact(user_id, draft['to']))
                    try:
                        await msg.edit_text(f"✅ {res}", reply_markup=InlineKeyboardMarkup([self.get_back_button()]))
                    except: pass
            asyncio.create_task(process_manual_send())

        elif data == "undosend_manual":
            if user_id in self.pending_sends:
                self.pending_sends.pop(user_id)
            await query.edit_message_text("🚫 *Email Send Canceled.*", parse_mode="Markdown", reply_markup=InlineKeyboardMarkup([self.get_back_button()]))

        elif data == "menu_settings":
            kb = [
                [InlineKeyboardButton("🚪 Logout Account", callback_data="action_logout")],
                self.get_back_button()
            ]
            await query.edit_message_text("⚙️ *Settings*\nConfigure assistant behavior or logout.", parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(kb))

        elif any(data.startswith(x) for x in ["full_", "sum_", "tts_sum_", "manual_del_", "manual_reply_", "manual_untrash_", "getatt_", "sr_"]):
            parts = data.split('_')
            action = parts[0] if not data.startswith("manual_") and not data.startswith("tts_") else f"{parts[0]}_{parts[1]}"
            m_id = parts[1] if len(parts) == 4 else parts[2]
            nav_context = parts[2] if len(parts) == 4 else parts[3] if len(parts) > 3 else "main"
            offset = parts[3] if len(parts) == 4 else parts[4] if len(parts) > 4 else "0"
            
            if action == "full":
                await self.render_full_email(query, m_id, nav_context, offset, user_id)
            
            elif action == "sr":
                actual_m_id = parts[1]
                reply_text = data.split(f"sr_{actual_m_id}_")[1]
                await query.edit_message_text(f"🚀 *Sending Quick Reply:* _{reply_text}_...", parse_mode="Markdown")
                meta = await self.gmail.get_email_metadata(user_id, actual_m_id)
                sender = meta.get('sender', '')
                sender_email = re.search(r'<(.+?)>', sender).group(1) if '<' in sender else sender
                res = await self.gmail.send_email(user_id, sender_email, f"Re: {meta.get('subject')}", reply_text, [])
                self.run_in_background(self._bg_save_contact(user_id, sender_email))
                await query.edit_message_text(f"✅ {res}", reply_markup=InlineKeyboardMarkup([self.get_back_button()]))

            elif action == "getatt":
                await query.edit_message_text("⏳ Fetching attachments...")
                file_paths = await self.gmail.get_attachments(user_id, m_id)
                back_kb = [[InlineKeyboardButton("🔙 Back to Email", callback_data=f"full_{m_id}_{nav_context}_{offset}")]]
                if not file_paths:
                    await query.edit_message_text("📭 *No attachments found in this email.*", parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(back_kb))
                else:
                    await query.edit_message_text("📤 Sending attachments, please wait...")
                    for fp in file_paths:
                        with open(fp, 'rb') as f:
                            await context.bot.send_document(chat_id=user_id, document=f)
                        os.remove(fp)
                    await query.edit_message_text("✅ Attachments sent successfully!", reply_markup=InlineKeyboardMarkup(back_kb))

            elif action == "sum":
                await query.edit_message_text("⏳ Generating AI Summary...")
                body = await self.gmail.read_full_email(user_id, m_id)
                
                raw_response = await self.ai_engine.agent_chat(f"Strictly summarize this email: {body[:3000]}", user_id)
                try:
                    summary_json = json.loads(raw_response.replace('```json', '').replace('```', '').strip())
                    summary_text = summary_json.get("text", "Error creating summary")
                except:
                    summary_text = raw_response

                smart_replies = await self.ai_engine.generate_smart_replies(body)
                kb = []
                for reply_text in smart_replies:
                    kb.append([InlineKeyboardButton(f"✅ Quick Reply: {reply_text}", callback_data=f"sr_{m_id}_{reply_text[:25]}")])

                kb.append([InlineKeyboardButton("📖 Read Full", callback_data=f"full_{m_id}_{nav_context}_{offset}")])
                kb.append(self.get_back_button(nav_context, int(offset)))
                await query.edit_message_text(f"🤖 *AI Summary:*\n\n{summary_text}", parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(kb))

            elif action == "tts_sum":
                await query.edit_message_text("🔊 Analyzing & Generating Audio Summary...")
                await context.bot.send_chat_action(chat_id=user_id, action=ChatAction.RECORD_VOICE)
                body = await self.gmail.read_full_email(user_id, m_id)
                
                raw_response = await self.ai_engine.agent_chat(f"Create a concise 3-sentence spoken summary for this email without formatting. Do not include introductory text, just the core facts: {body[:3000]}", user_id)
                try:
                    summary_json = json.loads(raw_response.replace('```json', '').replace('```', '').strip())
                    text_to_speak = summary_json.get("text", raw_response)
                except:
                    text_to_speak = raw_response

                clean_tts_text = re.sub(r'[*_#`]', '', text_to_speak)
                audio_path = await self.voice.synthesize(clean_tts_text, telegram_id=user_id)
                
                smart_replies = await self.ai_engine.generate_smart_replies(body)
                kb = []
                for reply_text in smart_replies:
                    kb.append([InlineKeyboardButton(f"✅ Quick Reply: {reply_text}", callback_data=f"sr_{m_id}_{reply_text[:25]}")])
                kb.append([InlineKeyboardButton("📖 Read Full", callback_data=f"full_{m_id}_{nav_context}_{offset}")])
                kb.append(self.get_back_button(nav_context, int(offset)))

                if audio_path and os.path.exists(audio_path):
                    with open(audio_path, 'rb') as audio:
                        await context.bot.send_voice(chat_id=user_id, voice=audio, caption="🔊 Concise Audio Summary")
                    os.remove(audio_path)
                    await query.edit_message_text(f"🤖 *AI Audio Summary Sent!*\n\n{text_to_speak}", parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(kb))
                else:
                    await query.edit_message_text("❌ Failed to generate audio.", reply_markup=InlineKeyboardMarkup(kb))

            elif action == "manual_del":
                if await self.gmail.delete_email(user_id, m_id):
                    kb = [[InlineKeyboardButton("↩️ Undo Delete", callback_data=f"manual_untrash_{m_id}_{nav_context}_{offset}")], self.get_back_button(nav_context, int(offset))]
                    await query.edit_message_text("🗑️ Email moved to trash.", reply_markup=InlineKeyboardMarkup(kb))

            elif action == "manual_untrash":
                if await self.gmail.untrash_email(user_id, m_id):
                    await query.edit_message_text("✅ Email restored to Inbox.", reply_markup=InlineKeyboardMarkup([self.get_back_button(nav_context, int(offset))]))

            elif action == "manual_reply":
                meta = await self.gmail.get_email_metadata(user_id, m_id)
                sender = meta.get('sender', '')
                sender_email = re.search(r'<(.+?)>', sender).group(1) if '<' in sender else sender
                subj = meta.get('subject', '')
                if not subj.startswith("Re:"): subj = "Re: " + subj
                self.compose_states[user_id] = {'step': 'AWAIT_BODY', 'to': sender_email, 'subj': subj}
                await query.edit_message_text(f"✉️ *Replying to:* {sender_email}\n\n✍️ Type your message below. 📎 You can add an attachment in the next step.", parse_mode="Markdown", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ Cancel", callback_data="cancel_compose")]]))

telegram_handler = TelegramBotManager()