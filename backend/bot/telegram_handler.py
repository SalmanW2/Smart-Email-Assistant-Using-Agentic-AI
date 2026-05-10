import logging
import os
import time
import asyncio
import re
import tempfile
import uuid
from datetime import datetime, timedelta
from pathlib import Path
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, InputFile
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, filters, ContextTypes
from bot.ai_engine import AIEngine
from db.models import db_manager
from db.memory import memory_manager
from config import settings
import edge_tts

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class TelegramHandler:
    def __init__(self, application: Application) -> None:
        self.application = application
        self.ai_engine = AIEngine()
        self.db = db_manager
        self.memory = memory_manager
        self.notified_emails = set()
        self.startup_time = int(time.time() * 1000)
        self.email_lock = asyncio.Lock()

    def _register_handlers(self):
        self.application.add_handler(CommandHandler("start", self.start_command))
        self.application.add_handler(CommandHandler("settings", self.settings_command))
        self.application.add_handler(CallbackQueryHandler(self.handle_button_actions))
        self.application.add_handler(MessageHandler(filters.VOICE, self.handle_voice))
        self.application.add_handler(MessageHandler(
            filters.Document.ALL | filters.PHOTO | filters.AUDIO,
            self.handle_attachment
        ))
        self.application.add_handler(MessageHandler(
            filters.TEXT & ~filters.COMMAND, self.handle_text
        ))

    def get_main_menu_kb(self):
        return InlineKeyboardMarkup([
            [InlineKeyboardButton("📥 Inbox", callback_data="manual_read_0"),
             InlineKeyboardButton("✍️ Compose", callback_data="menu_compose")],
            [InlineKeyboardButton("🔍 Search", callback_data="menu_search_prompt")],
            [InlineKeyboardButton("⚙️ Settings", callback_data="menu_settings")]
        ])

    def get_back_button(self, context_type="main", extra_data=""):
        if context_type == "inbox":
            return [InlineKeyboardButton("🔙 Back to Inbox", callback_data=f"manual_read_{extra_data}")]
        elif context_type == "search":
            return [InlineKeyboardButton("🔙 Back to Results", callback_data=f"page_read_{extra_data}")]
        return [InlineKeyboardButton("🔙 Main Menu", callback_data="menu_main")]

    async def auto_ping(self, context: ContextTypes.DEFAULT_TYPE):
        try:
            import httpx
            async with httpx.AsyncClient() as client:
                await client.get(settings.RENDER_WEB_SERVICE_URL)
        except Exception: pass

    async def check_new_emails(self, context: ContextTypes.DEFAULT_TYPE):
        async with self.email_lock:
            service = self.ai_engine.gmail_client.get_service()
            if not service: return
            try:
                results = service.users().messages().list(userId='me', q='is:unread', maxResults=3).execute()
                messages = results.get('messages', [])

                for msg in messages:
                    m_id = msg['id']
                    if m_id not in self.notified_emails:
                        self.notified_emails.add(m_id)
                        
                        msg_data = service.users().messages().get(userId='me', id=m_id, format='minimal').execute()
                        internal_date = int(msg_data.get('internalDate', 0))

                        if internal_date > self.startup_time:
                            meta = self.ai_engine.gmail_client.get_email_metadata(m_id)
                            att_count = len(meta.get('attachments', []))
                            att_text = f"\n📎 *Attachments:* {att_count} File(s) enclosed." if att_count > 0 else ""
                            
                            text = (
                                f"🔔 *New Email Received!*\n\n"
                                f"👤 *From:* {meta['sender']}\n"
                                f"📝 *Subject:* {meta['subject']}"
                                f"{att_text}"
                            )
                            kb = [
                                [InlineKeyboardButton("🤖 Generate Summary", callback_data=f"sum_{m_id}")],
                                [InlineKeyboardButton("📖 Read Full Email", callback_data=f"full_{m_id}_main")],
                                [InlineKeyboardButton("🗑️ Delete", callback_data=f"del_{m_id}_main")]
                            ]
                            await context.bot.send_message(
                                chat_id=settings.OWNER_TELEGRAM_ID,
                                text=text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(kb)
                            )
            except Exception: pass

    async def start_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        user = update.effective_user
        if not user:
            return

        try:
            if await self.db.is_blocked("telegram", str(user.id)):
                await update.message.reply_text("You are blocked from using this service.")
                return
        except Exception:
            pass

        try:
            db_user = await self.db.get_user(user.id)
            if not db_user:
                await self.db.create_user(user.id)
                db_user = await self.db.get_user(user.id)
        except Exception:
            await update.message.reply_text("Database error. Please try again.")
            return

        # FIXED: Generates state correctly based on your models.py
        state_uuid = await self.db.create_auth_session(user.id)
        
        # FIXED: Pointing directly to Render backend API for Telegram users
        login_url = f"{settings.RENDER_WEB_SERVICE_URL}/api/auth/telegram_login?state={state_uuid}&telegram_id={user.id}"
        
        await update.message.reply_text(
            f"Welcome {user.first_name}! I'm your Smart Email Assistant.\n\n"
            "This bot learns your contacts, manages Gmail actions naturally, and preserves memory summaries.\n\n"
            f"Connect your inbox here:\n{login_url}\n\n"
            "Use /settings to update preferences. Once connected, send any message like:\n"
            "- 'Show my latest emails'\n"
            "- 'Email my manager about the status'\n"
            "- 'Summarize this attachment'"
        )

    async def settings_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        user = update.effective_user
        if not user:
            return

        try:
            db_user = await self.db.get_user(user.id)
            if not db_user:
                await update.message.reply_text("Please start with /start")
                return
        except Exception:
            await update.message.reply_text("Database error.")
            return

        try:
            prefs = await self.db.get_user_preferences(user.id) or {}
        except Exception:
            prefs = {}

        ai_mode = prefs.get("ai_mode_enabled", db_user.get("ai_mode_enabled", True))
        voice_mode = prefs.get("voice_preference", "text")

        keyboard = [
            [InlineKeyboardButton(f"AI Mode: {'ON' if ai_mode else 'OFF'}", callback_data="toggle_ai")],
            [InlineKeyboardButton(f"Voice: {'ON' if voice_mode == 'voice' else 'OFF'}", callback_data="toggle_voice")],
            [InlineKeyboardButton("Logout", callback_data="logout")],
        ]
        await update.message.reply_text("Settings:", reply_markup=InlineKeyboardMarkup(keyboard))

    async def handle_button_actions(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        query = update.callback_query
        user_id = str(update.effective_user.id)
        await query.answer()
        data = query.data

        try:
            db_user = await self.db.get_user(int(user_id))
            if not db_user or not db_user.get("auth_token"):
                await self.request_login(update)
                return
        except Exception:
            await self.request_login(update)
            return

        if data == "menu_main":
            try:
                await self.db.upsert_user_preferences(int(user_id), {"compose_state": None, "search_state": None})
            except Exception:
                pass
            text = "🎛️ *Workspace Dashboard*\nSelect an action below or type your request."
            await query.edit_message_text(text, parse_mode="Markdown", reply_markup=self.get_main_menu_kb())
        
        elif data == "menu_compose":
            try:
                await self.db.upsert_user_preferences(int(user_id), {"compose_state": {'step': 'AWAIT_TO', 'to': '', 'subj': '', 'body': '', 'attachments': []}})
            except Exception:
                pass
            kb = [[InlineKeyboardButton("❌ Cancel", callback_data="cancel_compose")]]
            await query.edit_message_text("✍️ *Manual Compose*\n\nPlease enter the recipient's email address:", parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(kb))
        
        elif data == "menu_search_prompt":
            try:
                await self.db.upsert_user_preferences(int(user_id), {"search_state": 'AWAIT_QUERY'})
            except Exception:
                pass
            kb = [[InlineKeyboardButton("❌ Cancel", callback_data="cancel_compose")]]
            await query.edit_message_text("🔍 *Manual Search*\n\nPlease type your search query below.\n_(Examples: 'from:ali', 'is:unread', or a simple keyword)_", parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(kb))
        
        elif data == "menu_settings":
            await self.settings_command(update, context)
        
        elif data == "cancel_compose":
            try:
                await self.db.upsert_user_preferences(int(user_id), {"compose_state": None, "search_state": None})
            except Exception:
                pass
            await query.edit_message_text("🚫 *Process Canceled*\n\nThe action was safely terminated. How else may I assist you?", parse_mode="Markdown", reply_markup=InlineKeyboardMarkup([self.get_back_button()]))

    async def request_login(self, update: Update):
        user_id = update.effective_user.id
        # FIXED: Correct auth session creation
        state_uuid = await self.db.create_auth_session(user_id)
        
        # FIXED: Direct Render URL
        link = f"{settings.RENDER_WEB_SERVICE_URL}/api/auth/telegram_login?state={state_uuid}&telegram_id={user_id}"
        
        kb = [[InlineKeyboardButton("🔗 Connect Google Account", url=link)]]
        text = "⚠️ *Please login first!*\nYou need to connect your Google Account to proceed."
        
        if update.callback_query:
            await update.callback_query.edit_message_text(text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(kb))
        elif update.message:
            await update.message.reply_text(text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(kb))
                    
    async def handle_attachment(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        user_id = str(update.effective_user.id)
        try:
            db_user = await self.db.get_user(int(user_id))
            if not db_user or not db_user.get("auth_token"):
                await self.request_login(update)
                return
        except Exception:
            await self.request_login(update)
            return

        attachment = (update.message.document or (update.message.photo[-1] if update.message.photo else None) or update.message.audio or update.message.video)
        if not attachment: return

        if attachment.file_size > 20 * 1024 * 1024:
            await update.message.reply_text("❌ *File is too large for Telegram (Max 20MB).* \nPlease upload it to your Google Drive and paste the shareable link here.", parse_mode="Markdown")
            return

        msg = await update.message.reply_text("⏳ Downloading attachment...")
        file = await context.bot.get_file(attachment.file_id)
        file_name = getattr(attachment, 'file_name', f"file_{int(time.time())}")
        file_path = f"/tmp/{file_name}"
        await file.download_to_drive(file_path)

        try:
            prefs = await self.db.get_user_preferences(int(user_id)) or {}
        except Exception:
            prefs = {}
        compose_state = prefs.get("compose_state")

        if compose_state and compose_state['step'] == 'AWAIT_ATTACHMENT':
            compose_state['attachments'].append(file_path)
            try:
                await self.db.upsert_user_preferences(int(user_id), {"compose_state": compose_state})
            except Exception:
                pass
            kb = [[InlineKeyboardButton("✅ Send Now", callback_data="send_manual_draft"), InlineKeyboardButton("❌ Cancel", callback_data="cancel_compose")]]
            
            files_list = "\n".join([f"- {os.path.basename(f).replace('_', '-')}" for f in compose_state['attachments']])
            draft_text = f"📄 *Draft Ready!*\n\n*To:* {compose_state['to']}\n*Subject:* {compose_state['subj']}\n*Body:* {compose_state['body']}\n📎 *Attachments:* \n{files_list}\n\nYou can upload more files or click Send Now."
            await msg.edit_text(draft_text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(kb))
        else:
            try:
                attachments = prefs.get("attachments", [])
                attachments.append(file_path)
                await self.db.upsert_user_preferences(int(user_id), {"attachments": attachments})
            except Exception:
                pass
            await self.send_attachment_dashboard(msg, int(user_id))

    async def send_attachment_dashboard(self, message_obj, user_id):
        try:
            prefs = await self.db.get_user_preferences(user_id) or {}
        except Exception:
            prefs = {}
        files = prefs.get("attachments", [])
        if not files:
            text = "📭 *Memory Empty:* No attachments saved."
            kb = [self.get_back_button()]
            if hasattr(message_obj, 'edit_text'):
                await message_obj.edit_text(text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(kb))
            else:
                await message_obj.reply_text(text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(kb))
            return

        text = f"📁 *File(s) Saved to Memory*\nTotal Files: {len(files)}\n\n"
        text += "💡 *Tip for AI:* To send these files using the AI, simply send a voice or text message saying: _'Send an email to Ali and attach the files.'_\n\n"
        
        kb = []
        for i, f in enumerate(files):
            safe_filename = os.path.basename(f).replace("_", "-").replace("*", "")
            text += f"*{i+1}.* `{safe_filename}`\n"
            kb.append([InlineKeyboardButton(f"❌ Remove File {i+1}", callback_data=f"rm_att_{i}")])
        
        kb.append([InlineKeyboardButton("➕ Add Another Attachment", callback_data="add_att")])
        kb.append([
            InlineKeyboardButton("🧹 Clear All", callback_data="clr_att"), 
            InlineKeyboardButton("✉️ Draft Email", callback_data="menu_compose")
        ])
        kb.append(self.get_back_button())

        if hasattr(message_obj, 'edit_text'):
            await message_obj.edit_text(text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(kb))
        else:
            await message_obj.reply_text(text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(kb))

    async def handle_text(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        user_id = str(update.effective_user.id)
        try:
            db_user = await self.db.get_user(int(user_id))
            if not db_user or not db_user.get("auth_token"):
                await self.request_login(update)
                return
        except Exception:
            await self.request_login(update)
            return

        text = update.message.text
        
        try:
            prefs = await self.db.get_user_preferences(int(user_id)) or {}
        except Exception:
            prefs = {}

        if prefs.get("search_state") == 'AWAIT_QUERY':
            query_text = text
            try:
                await self.db.upsert_user_preferences(int(user_id), {"search_state": None})
            except Exception:
                pass
            waiting_msg = await update.message.reply_text(f"🔍 Searching for: `{query_text}`...", parse_mode="Markdown")
            await self.show_paginated_emails(waiting_msg, query=query_text, offset=0, user_id=int(user_id), is_search=True)
            return

        if prefs.get("compose_state"):
            state = prefs["compose_state"]
            kb = [[InlineKeyboardButton("❌ Cancel", callback_data="cancel_compose")]]
            
            if state['step'] == 'AWAIT_TO':
                state['to'] = text
                state['step'] = 'AWAIT_SUBJ'
                try:
                    await self.db.upsert_user_preferences(int(user_id), {"compose_state": state})
                except Exception:
                    pass
                await update.message.reply_text(f"Got it. To: {text}\n\nWhat is the Subject?", reply_markup=InlineKeyboardMarkup(kb))
            elif state['step'] == 'AWAIT_SUBJ':
                state['subj'] = text
                state['step'] = 'AWAIT_BODY'
                try:
                    await self.db.upsert_user_preferences(int(user_id), {"compose_state": state})
                except Exception:
                    pass
                await update.message.reply_text("Please type your email message.", reply_markup=InlineKeyboardMarkup(kb))
            elif state['step'] == 'AWAIT_BODY':
                state['body'] = text
                state['step'] = 'AWAIT_ATTACHMENT'
                try:
                    await self.db.upsert_user_preferences(int(user_id), {"compose_state": state})
                except Exception:
                    pass
                kb_send = [[InlineKeyboardButton("✅ Send Now", callback_data="send_manual_draft"), InlineKeyboardButton("❌ Cancel", callback_data="cancel_compose")]]
                draft_text = f"📄 *Draft Generated:*\n\n*To:* {state['to']}\n*Subject:* {state['subj']}\n*Body:* {state['body']}\n\n📎 Do you want to add an attachment? Upload the file now. If no attachment is needed, simply click *Send Now*."
                await update.message.reply_text(draft_text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(kb_send))
            elif state['step'] == 'AWAIT_ATTACHMENT':
                await update.message.reply_text("Please upload an attachment file, or click Send Now if you are ready.", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("✅ Send Now", callback_data="send_manual_draft"), InlineKeyboardButton("❌ Cancel", callback_data="cancel_compose")]]))
            return

        await context.bot.send_chat_action(chat_id=update.effective_chat.id, action='typing')
        res = await asyncio.to_thread(self.ai_engine.agent_chat, text, user_id)
        
        if res.startswith("Error:"):
            await update.message.reply_text(f"⚠️ System Alert: {res}")
        else:
            msg_obj = await update.message.reply_text("⏳ Processing...")
            await self.send_ai_response(msg_obj, res, int(user_id))

    async def send_ai_response(self, message_obj, res_text, user_id):
        kb = []
        try:
            prefs = await self.db.get_user_preferences(user_id) or {}
        except Exception:
            prefs = {}
        has_pending = prefs.get("pending_ai_sends", False)
        if has_pending:
            kb.append([InlineKeyboardButton("↩️ Undo Send", callback_data="undosend_ai")])
        kb.append(self.get_back_button())
        
        sent_msg = await message_obj.edit_text(res_text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(kb))
        
        if has_pending:
            async def process_ai_send():
                await asyncio.sleep(7)
                if prefs.get("pending_ai_sends"):
                    draft = prefs["pending_ai_sends"]
                    try:
                        await self.db.upsert_user_preferences(user_id, {"pending_ai_sends": None})
                    except Exception:
                        pass
                    res = await asyncio.to_thread(self.ai_engine.gmail_client.send_email, draft['to'], draft['subj'], draft['body'], [], user_id=user_id)
                    try:
                        new_kb = [self.get_back_button()]
                        await sent_msg.edit_reply_markup(reply_markup=InlineKeyboardMarkup(new_kb))
                    except: pass
            asyncio.create_task(process_ai_send())

    async def show_paginated_emails(self, message_obj, query='label:INBOX', offset=0, user_id=None, is_search=False):
        service = self.ai_engine.gmail_client.get_service()
        if not service: return
        try:
            if user_id:
                try:
                    await self.db.upsert_user_preferences(user_id, {"current_queries": query, "navigation_history": {'type': 'search' if is_search else 'inbox', 'offset': offset}})
                except Exception:
                    pass

            results = service.users().messages().list(userId='me', q=query, maxResults=30).execute()
            messages = results.get('messages', [])
            
            if not messages:
                text = f"📭 No emails found for: `{query}`"
                kb = [[InlineKeyboardButton("🔍 Search Again", callback_data="menu_search_prompt")], self.get_back_button()]
                if hasattr(message_obj, 'edit_text'):
                    await message_obj.edit_text(text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(kb))
                else:
                    await message_obj.reply_text(text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(kb))
                return
            
            page_msgs = messages[offset:offset+5]
            if not page_msgs:
                await message_obj.reply_text("No more emails found.", reply_markup=InlineKeyboardMarkup([self.get_back_button()]))
                return

            kb = []
            header_text = f"🔍 Searched: `{query}`" if is_search else f"📥 Inbox"
            text = f"*{header_text} ({offset+1}-{offset+len(page_msgs)}):*\n\n"
            
            context_tag = "search" if is_search else "inbox"
            
            for idx, m in enumerate(page_msgs):
                meta = self.ai_engine.gmail_client.get_email_metadata(m['id'])
                safe_sender = meta['sender'][:30].replace('<', '').replace('>', '').replace('_', ' ').replace('*', '')
                safe_subj = meta['subject'][:35].replace('<', '').replace('>', '').replace('_', ' ').replace('*', '')
                
                text += f"*{idx+1+offset}.* {safe_sender}\n_{safe_subj}..._\n\n"
                kb.append([InlineKeyboardButton(f"📖 Read #{idx+1+offset}", callback_data=f"full_{m['id']}_{context_tag}")])
            
            nav_buttons = []
            prefix = "page_read_" if is_search else "manual_read_"
            if offset >= 5: 
                nav_buttons.append(InlineKeyboardButton("⬅️ Newer", callback_data=f"{prefix}{offset-5}"))
            if offset + 5 < len(messages): 
                nav_buttons.append(InlineKeyboardButton("Older ➡️", callback_data=f"{prefix}{offset+5}"))
            
            if nav_buttons: kb.append(nav_buttons)
            kb.append(self.get_back_button())

            if hasattr(message_obj, 'edit_text'):
                await message_obj.edit_text(text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(kb))
            else:
                await message_obj.reply_text(text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(kb))
        except Exception as e:
            error_text = f"⚠️ *Search Error:*\n{str(e)}"
            if hasattr(message_obj, 'edit_text'):
                await message_obj.edit_text(error_text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup([self.get_back_button()]))
            else:
                await message_obj.reply_text(error_text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup([self.get_back_button()]))

    async def handle_voice(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        user_id = str(update.effective_user.id)
        try:
            db_user = await self.db.get_user(int(user_id))
            if not db_user or not db_user.get("auth_token"):
                await self.request_login(update)
                return
        except Exception:
            await self.request_login(update)
            return

        msg = await update.message.reply_text("🎙️ Processing voice note...")
        try:
            voice = update.message.voice
            file = await context.bot.get_file(voice.file_id)
            file_path = f"/tmp/voice_{int(time.time())}.ogg"
            await file.download_to_drive(file_path)
            transcribed_text = await asyncio.to_thread(self.ai_engine.transcribe_audio, file_path)
            if os.path.exists(file_path): os.remove(file_path)

            if transcribed_text.startswith("System Error:") or "[Audio Unclear]" in transcribed_text:
                await msg.edit_text(f"⚠️ *Transcription Error:*\nThe audio was unclear or cut off. Could you please repeat that professionally?", parse_mode="Markdown")
                return
            
            task_id = str(int(time.time() * 1000))
            
            # FIXED: Avoid set().add() which returns None and breaks the database
            try:
                prefs = await self.db.get_user_preferences(int(user_id)) or {}
                active_tasks = set(prefs.get("active_voice_tasks", []))
                active_tasks.add(task_id)
                await self.db.upsert_user_preferences(int(user_id), {"active_voice_tasks": list(active_tasks)})
            except Exception:
                pass

            kb = [[InlineKeyboardButton("❌ Cancel Process", callback_data=f"cancel_voice_{task_id}")]]
            await msg.edit_text(f"🗣️ *You said:* {transcribed_text}\n\n⏳ Processing...", parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(kb))

            res = await asyncio.to_thread(self.ai_engine.agent_chat, transcribed_text, user_id)
            
            try:
                prefs = await self.db.get_user_preferences(int(user_id)) or {}
                active_tasks = set(prefs.get("active_voice_tasks", []))
                if task_id in active_tasks:
                    active_tasks.remove(task_id)
                    await self.db.upsert_user_preferences(int(user_id), {"active_voice_tasks": list(active_tasks)})
                else:
                    return
            except Exception:
                pass

            if res.startswith("Error:"):
                await msg.edit_text(f"⚠️ System Alert: {res}")
            else:
                await self.send_ai_response(msg, res, int(user_id))
        except Exception as e:
            await msg.edit_text(f"❌ Voice processing error: {str(e)}")

    async def send_voice_response(self, update: Update, text: str) -> None:
        audio_path: str | None = None
        try:
            audio_path = await self._generate_audio(text)
            with open(audio_path, "rb") as audio_file:
                await update.message.reply_audio(InputFile(audio_file, filename=Path(audio_path).name))
        except Exception:
            logger.exception("Voice synthesis failed")
            await update.message.reply_text(text, parse_mode="Markdown")
        finally:
            if audio_path and os.path.exists(audio_path):
                os.remove(audio_path)

    async def _generate_audio(self, text: str) -> str:
        try:
            return await asyncio.to_thread(self._edge_tts, text)
        except Exception:
            return await asyncio.to_thread(self._pyttsx3_tts, text)

    def _edge_tts(self, text: str) -> str:
        import asyncio
        async def generate():
            communicate = edge_tts.Communicate(text, "en-US-AriaNeural")
            temp_file = Path(tempfile.gettempdir()) / f"smart-email-voice-{uuid.uuid4().hex}.mp3"
            await communicate.save(str(temp_file))
            return str(temp_file)
        return asyncio.run(generate())

    def _pyttsx3_tts(self, text: str) -> str:
        import pyttsx3
        engine = pyttsx3.init()
        file_path = Path(tempfile.gettempdir()) / f"smart-email-voice-{uuid.uuid4().hex}.mp3"
        engine.save_to_file(text, str(file_path))
        engine.runAndWait()
        return str(file_path)

# --- FIXED BOT MANAGER ---
class TelegramBotManager:
    def __init__(self) -> None:
        self.application: Application | None = None

    async def setup_bot(self) -> None:
        """Called by FastAPI startup event to initialize the bot and webhooks."""
        self.application = Application.builder().token(settings.BOT_TOKEN).build()
        handler = TelegramHandler(self.application)
        handler._register_handlers()
        await self.application.initialize()
        
        # Set Webhook pointing to FastAPI route
        webhook_url = f"{settings.RENDER_WEB_SERVICE_URL}/webhook/telegram"
        await self.application.bot.set_webhook(url=webhook_url)
        logger.info(f"Webhook set to {webhook_url}")

    async def process_webhook(self, data: dict) -> None:
        """Called by FastAPI webhook route to process incoming updates."""
        if self.application:
            update = Update.de_json(data, self.application.bot)
            await self.application.process_update(update)

    async def stop(self) -> None:
        """Called by FastAPI shutdown event."""
        if self.application:
            await self.application.stop()

# Export a single instance for main.py to use
telegram_handler = TelegramBotManager()