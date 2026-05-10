import logging
import os
import time
import asyncio
import tempfile
import uuid
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

        # Robust State Management
        self.compose_states = {} 
        self.search_states = {}
        self.user_attachments = {}
        self.notified_emails = set()
        self.startup_time = int(time.time() * 1000)
        self.email_lock = asyncio.Lock()

    async def setup_bot(self) -> None:
        """Initializes the Telegram bot and registers all robust handlers."""
        self.application = ApplicationBuilder().token(settings.BOT_TOKEN).build()
        
        # Commands
        self.application.add_handler(CommandHandler("start", self.start_command))
        self.application.add_handler(CommandHandler("menu", self.menu_command))
        self.application.add_handler(CommandHandler("settings", self.settings_command))
        self.application.add_handler(CommandHandler("logout", self.logout_command))
        
        # Interactive Handlers
        self.application.add_handler(CallbackQueryHandler(self.handle_button_actions))
        self.application.add_handler(MessageHandler(filters.VOICE, self.handle_voice))
        self.application.add_handler(MessageHandler(filters.Document.ALL | filters.PHOTO, self.handle_attachment))
        self.application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, self.handle_text))

        await self.application.initialize()
        
        # Sync Webhook to Render
        webhook_url = f"{settings.RENDER_WEB_SERVICE_URL}/webhook/telegram"
        await self.application.bot.set_webhook(url=webhook_url)
        logger.info(f"Webhook synchronized successfully to {webhook_url}")

        # Start Background Jobs
        self.application.job_queue.run_repeating(self.check_new_emails, interval=60, first=10)
        self.application.job_queue.run_repeating(self.auto_ping, interval=840, first=60)
        await self.application.start()

    async def process_webhook(self, data: dict) -> None:
        """Processes incoming data securely via FastAPI."""
        if self.application:
            update = Update.de_json(data, self.application.bot)
            await self.application.process_update(update)

    async def stop(self) -> None:
        """Gracefully shuts down the Telegram Bot Application."""
        if self.application:
            await self.application.stop()
            await self.application.shutdown()

    # --- CENTRALIZED ACCESS CONTROL (THE SECURITY GATE) ---
    async def _check_user_access(self, user_id: int, first_name: str, username: str) -> dict:
        """
        The ultimate security gate. Checks Blocklist -> Registration -> Approval -> Authentication.
        Returns a dictionary with the 'status' to dictate the bot's flow.
        """
        # 1. Check if Blocked
        if await self.db.is_blocked("telegram", str(user_id)):
            return {"status": "blocked"}
        
        # 2. Check Registration
        db_user = await self.db.get_user(user_id)
        if not db_user:
            # Register new user automatically but keep them unverified
            email_placeholder = f"{username}@telegram.user" if username else None
            await self.db.create_user(user_id, email=email_placeholder)
            return {"status": "pending"}
            
        # 3. Check Admin Approval
        if not db_user.get("is_verified"):
            return {"status": "pending"}
            
        # 4. Check Google OAuth Link
        if not db_user.get("auth_token"):
            return {"status": "unauthenticated"}
            
        # 5. Fully Authorized
        return {"status": "authorized", "user_data": db_user}

    async def _handle_unauthorized_states(self, update: Update, status: str, user_id: int):
        """Handles sending the appropriate rejection/login messages based on status."""
        if status == "blocked":
            msg = "⛔ *Access Denied*: Your Telegram ID has been blocklisted by administrators due to policy violations."
            await self._send_or_edit(update, msg)
            return True
            
        if status == "pending":
            msg = "⏳ *Pending Authorization*\n\nYour request is in the queue. You cannot use the bot or connect your Google account until an Administrator verifies your profile."
            await self._send_or_edit(update, msg)
            return True
            
        if status == "unauthenticated":
            await self.request_secure_login(update, user_id)
            return True
            
        return False

    async def _send_or_edit(self, update: Update, text: str, reply_markup=None):
        """Helper to cleanly send or edit messages depending on the update type."""
        if update.callback_query:
            await update.callback_query.edit_message_text(text, parse_mode="Markdown", reply_markup=reply_markup)
        elif update.message:
            await update.message.reply_text(text, parse_mode="Markdown", reply_markup=reply_markup)

    # --- OAUTH LINK GENERATION ---
    async def request_secure_login(self, update: Update, user_id: int):
        """Generates a highly secure Google OAuth Link using a Supabase mapped UUID."""
        # This creates a unique UUID session mapped to this user_id in the DB
        state_uuid = await self.db.create_auth_session(user_id)
        
        # The link relies on the state_uuid. telegram_id is passed but validated against the state backend.
        login_url = f"{settings.RENDER_WEB_SERVICE_URL}/api/auth/telegram_login?state={state_uuid}&telegram_id={user_id}"
        
        kb = [[InlineKeyboardButton("🔗 Securely Connect Google Workspace", url=login_url)]]
        text = (
            "⚠️ *Authentication Required*\n\n"
            "Your profile is approved! To activate the Agentic AI capabilities, you must link your Gmail account.\n\n"
            "🛡️ _We use official Google OAuth 2.0. We never see your password._"
        )
        await self._send_or_edit(update, text, InlineKeyboardMarkup(kb))

    # --- CORE COMMANDS ---
    async def start_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        user = update.effective_user
        access = await self._check_user_access(user.id, user.first_name, user.username)
        
        # If not fully authorized, the handler takes care of the rejection/login prompt
        if await self._handle_unauthorized_states(update, access["status"], user.id):
            return

        # If Authorized
        kb = [
            [InlineKeyboardButton("📥 Check Inbox", callback_data="manual_read_0"), InlineKeyboardButton("✍️ Compose Email", callback_data="menu_compose")],
            [InlineKeyboardButton("🔍 Search Emails", callback_data="menu_search_prompt")],
            [InlineKeyboardButton("⚙️ Assistant Settings", callback_data="menu_settings")]
        ]
        welcome_text = (
            f"✅ *Welcome back, {user.first_name}! Access Verified.*\n\n"
            "I am your Enterprise Email Assistant powered by Gemini Agentic AI. "
            "You can type naturally (e.g., _\"Email Ali about the meeting tomorrow\"_), "
            "send me a voice note, or use the menu below."
        )
        await update.message.reply_text(welcome_text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(kb))

    async def menu_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        user = update.effective_user
        access = await self._check_user_access(user.id, user.first_name, user.username)
        if await self._handle_unauthorized_states(update, access["status"], user.id):
            return
            
        kb = [
            [InlineKeyboardButton("📥 Check Inbox", callback_data="manual_read_0"), InlineKeyboardButton("✍️ Compose Email", callback_data="menu_compose")],
            [InlineKeyboardButton("🔍 Search Emails", callback_data="menu_search_prompt")],
            [InlineKeyboardButton("⚙️ Assistant Settings", callback_data="menu_settings")]
        ]
        await update.message.reply_text("🎛️ *Main Dashboard*\nSelect an action below or just speak to the AI natively.", parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(kb))

    async def settings_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        user = update.effective_user
        access = await self._check_user_access(user.id, user.first_name, user.username)
        if await self._handle_unauthorized_states(update, access["status"], user.id):
            return

        prefs = await self.db.get_user_preferences(user.id) or {}
        ai_mode = prefs.get("ai_mode_enabled", True)
        voice_pref = prefs.get("voice_preference", "text")

        kb = [
            [InlineKeyboardButton(f"🧠 AI Mode: {'🟢 ON' if ai_mode else '🔴 OFF'}", callback_data="toggle_ai")],
            [InlineKeyboardButton(f"🎙️ Voice Outputs: {voice_pref.upper()}", callback_data="toggle_voice")],
            [InlineKeyboardButton("🚪 Revoke Google Access", callback_data="revoke_access")]
        ]
        await self._send_or_edit(update, "⚙️ *System Preferences*\nConfigure your assistant interactions:", InlineKeyboardMarkup(kb))

    async def logout_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        user_id = update.effective_user.id
        await self.db.db.run(lambda: self.db.db.client.table("users").update({"auth_token": None}).eq("telegram_id", user_id).execute())
        await update.message.reply_text("🚪 *Session Terminated*\nYour Google Workspace access token has been securely deleted from our servers.", parse_mode="Markdown")

    # --- MEDIA & TEXT HANDLERS ---
    async def handle_voice(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        user = update.effective_user
        access = await self._check_user_access(user.id, user.first_name, user.username)
        if await self._handle_unauthorized_states(update, access["status"], user.id):
            return

        msg = await update.message.reply_text("🎙️ *Processing Audio Stream...*", parse_mode="Markdown")
        try:
            voice_file = await context.bot.get_file(update.message.voice.file_id)
            temp_path = os.path.join(tempfile.gettempdir(), f"voice_{uuid.uuid4().hex}.ogg")
            await voice_file.download_to_drive(temp_path)
            
            transcript = await self.ai_engine.transcribe_audio(temp_path)
            if os.path.exists(temp_path): os.remove(temp_path)

            if "[Audio Unclear]" in transcript or transcript.startswith("System Error"):
                return await msg.edit_text("⚠️ *Transcription Failed*\nThe audio stream was unclear. Please speak directly into the microphone.", parse_mode="Markdown")
            
            await msg.edit_text(f"🗣️ *Transcript:* _{transcript}_\n\n✨ *Agentic AI Analyzing...*", parse_mode="Markdown")
            
            response_text = await self.ai_engine.agent_chat(transcript, user.id)
            await self._deliver_ai_response(msg, response_text, user.id, transcript)

        except Exception as e:
            logger.error(f"Voice Error: {e}")
            await msg.edit_text("❌ A critical error occurred during voice processing.")

    async def handle_attachment(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        user = update.effective_user
        access = await self._check_user_access(user.id, user.first_name, user.username)
        if await self._handle_unauthorized_states(update, access["status"], user.id):
            return

        attachment = update.message.document or (update.message.photo[-1] if update.message.photo else None)
        if not attachment: return

        if getattr(attachment, 'file_size', 0) > settings.MAX_ATTACHMENT_SIZE_MB * 1024 * 1024:
            return await update.message.reply_text(f"❌ Document exceeds the {settings.MAX_ATTACHMENT_SIZE_MB}MB safety limit.")

        msg = await update.message.reply_text("📎 *Buffering Document...*", parse_mode="Markdown")
        file = await context.bot.get_file(attachment.file_id)
        file_name = getattr(attachment, 'file_name', f"file_{uuid.uuid4().hex[:6]}")
        file_path = os.path.join(tempfile.gettempdir(), file_name)
        await file.download_to_drive(file_path)

        if user.id not in self.user_attachments:
            self.user_attachments[user.id] = []
        self.user_attachments[user.id].append(file_path)

        kb = [[InlineKeyboardButton("🧹 Clear Queue", callback_data="clear_att")]]
        await msg.edit_text(f"📁 *Document Stored in Cache*\n`{file_name}` is ready.\n\n_Tip: Send a voice note asking to summarize this document, or ask the AI to attach it to a new email._", parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(kb))

    async def handle_text(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        user = update.effective_user
        text = update.message.text
        
        # 🛡️ THE CRITICAL FIX: Always verify access before processing text
        access = await self._check_user_access(user.id, user.first_name, user.username)
        if await self._handle_unauthorized_states(update, access["status"], user.id):
            return

        # Manual Fallback Modes (If triggered from buttons)
        if user.id in self.compose_states:
            return await self.process_manual_compose(update, user.id, text)
        if user.id in self.search_states:
            return await self.process_manual_search(update, user.id, text)

        # Agentic AI Execution
        await context.bot.send_chat_action(chat_id=update.effective_chat.id, action='typing')
        msg = await update.message.reply_text("✨ *AI Engine Thinking...*", parse_mode="Markdown")
        
        response_text = await self.ai_engine.agent_chat(text, user.id)
        await self._deliver_ai_response(msg, response_text, user.id)

    async def _deliver_ai_response(self, msg_obj, response_text: str, user_id: int, transcript: str = None):
        """Intelligently delivers text or voice depending on DB preferences."""
        prefs = await self.db.get_user_preferences(user_id) or {}
        voice_pref = prefs.get("voice_preference", "text")

        kb = [[InlineKeyboardButton("⚙️ Open Menu", callback_data="menu_main")]]

        if voice_pref in ["voice", "both"]:
            try:
                audio_path = await self.voice.synthesize(response_text)
                if audio_path and os.path.exists(audio_path):
                    with open(audio_path, 'rb') as audio_file:
                        await msg_obj.get_bot().send_voice(chat_id=user_id, voice=audio_file, reply_markup=InlineKeyboardMarkup(kb))
                    os.remove(audio_path)
                    if voice_pref == "voice":
                        await msg_obj.delete()
                        return
            except Exception as e:
                logger.error(f"Voice generation failed: {e}")

        display_text = response_text
        if transcript:
            display_text = f"🗣️ *Transcript:* _{transcript}_\n\n🤖 *AI:* {response_text}"
        
        await msg_obj.edit_text(display_text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(kb))

    # --- INLINE BUTTON DISPATCHER & MANUAL MODES ---
    async def handle_button_actions(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        query = update.callback_query
        user_id = update.effective_user.id
        await query.answer()
        data = query.data

        if data == "menu_main":
            self.compose_states.pop(user_id, None)
            self.search_states.pop(user_id, None)
            await self.menu_command(update, context)
            return

        if data == "menu_settings":
            await self.settings_command(update, context)
            return

        if data == "revoke_access":
            await self.logout_command(update, context)
            return

        if data == "toggle_voice":
            prefs = await self.db.get_user_preferences(user_id) or {}
            current = prefs.get("voice_preference", "text")
            new_pref = "voice" if current == "text" else "both" if current == "voice" else "text"
            await self.db.update_user_preferences(user_id, {"voice_preference": new_pref})
            await self.settings_command(update, context)
            return

        if data == "toggle_ai":
            prefs = await self.db.get_user_preferences(user_id) or {}
            new_state = not prefs.get("ai_mode_enabled", True)
            await self.db.update_user_preferences(user_id, {"ai_mode_enabled": new_state})
            await self.settings_command(update, context)
            return

        if data.startswith("sum_"):
            msg_id = data.split("_")[1]
            await query.edit_message_text("✨ *Reading & Generating Summary...*", parse_mode="Markdown")
            full_text = await self.gmail.read_full_email(user_id, msg_id)
            summary = await self.ai_engine.agent_chat(f"Summarize this email strictly and professionally: {full_text[:3000]}", user_id)
            await query.edit_message_text(f"📑 *AI Summary:*\n\n{summary}", parse_mode="Markdown", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back to Dashboard", callback_data="menu_main")]]))
            return

        if data.startswith("read_"):
            msg_id = data.split("_")[1]
            full_text = await self.gmail.read_full_email(user_id, msg_id)
            await query.edit_message_text(f"📖 *Email Content:*\n\n{full_text[:3500]}", parse_mode="Markdown", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back to Dashboard", callback_data="menu_main")]]))
            return

        if data == "clear_att":
            if user_id in self.user_attachments:
                for f in self.user_attachments[user_id]:
                    if os.path.exists(f): os.remove(f)
                self.user_attachments.pop(user_id)
            await query.edit_message_text("🧹 *Cache Cleared*\nAll buffered attachments have been securely removed.", parse_mode="Markdown", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back", callback_data="menu_main")]]))
            return

        if data == "menu_compose":
            self.compose_states[user_id] = {"step": "to", "data": {}}
            await query.edit_message_text("✍️ *Manual Compose Mode*\n\nEnter the recipient's email address or contact name:", parse_mode="Markdown", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ Cancel", callback_data="menu_main")]]))
            return
            
        if data == "menu_search_prompt":
            self.search_states[user_id] = True
            await query.edit_message_text("🔍 *Manual Search*\n\nType your search query (e.g., 'emails from Ali', 'unread project emails'):", parse_mode="Markdown", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ Cancel", callback_data="menu_main")]]))
            return

    async def process_manual_compose(self, update: Update, user_id: int, text: str):
        state = self.compose_states[user_id]
        kb = [[InlineKeyboardButton("❌ Abort", callback_data="menu_main")]]
        
        if state["step"] == "to":
            resolved_email = await self.contacts.resolve_contact(user_id, text)
            state["data"]["to"] = resolved_email or text
            state["step"] = "subject"
            await update.message.reply_text(f"📧 *To:* `{state['data']['to']}`\n\nEnter the Subject:", parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(kb))
        
        elif state["step"] == "subject":
            state["data"]["subject"] = text
            state["step"] = "body"
            await update.message.reply_text("📝 Enter the Email Body:", reply_markup=InlineKeyboardMarkup(kb))
            
        elif state["step"] == "body":
            state["data"]["body"] = text
            await update.message.reply_text("🚀 Transmitting Email to Google Servers...")
            res = await self.gmail.send_email(user_id, state["data"]["to"], state["data"]["subject"], state["data"]["body"], attachments=self.user_attachments.get(user_id))
            
            self.compose_states.pop(user_id, None)
            if user_id in self.user_attachments:
                for f in self.user_attachments[user_id]:
                    if os.path.exists(f): os.remove(f)
                self.user_attachments.pop(user_id, None)
                
            await update.message.reply_text(res, reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Dashboard", callback_data="menu_main")]]))

    async def process_manual_search(self, update: Update, user_id: int, text: str):
        self.search_states.pop(user_id, None)
        await update.message.reply_text(f"🔍 Searching Inbox for `{text}`...")
        
        query = await self.ai_engine.get_search_query(text)
        emails = await self.gmail.get_emails(user_id, query=query, max_results=5)
        
        if not emails:
            return await update.message.reply_text("📭 No results found in your workspace.", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Dashboard", callback_data="menu_main")]]))
            
        response = f"🔍 *Results for:* `{text}`\n\n"
        kb = []
        for i, email in enumerate(emails):
            meta = await self.gmail.get_email_metadata(user_id, email['id'])
            if "error" not in meta:
                safe_sender = meta.get('sender', '')[:25]
                safe_subj = meta.get('subject', '')[:30]
                response += f"*{i+1}.* {safe_sender}\n_{safe_subj}_\n\n"
                kb.append([InlineKeyboardButton(f"📖 Read #{i+1}", callback_data=f"read_{email['id']}")])
                
        kb.append([InlineKeyboardButton("🔙 Main Menu", callback_data="menu_main")])
        await update.message.reply_text(response, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(kb))

    # --- BACKGROUND WORKERS ---
    async def auto_ping(self, context: ContextTypes.DEFAULT_TYPE):
        """Keeps Render Free Tier instances awake."""
        try:
            import httpx
            async with httpx.AsyncClient() as client:
                await client.get(f"{settings.RENDER_WEB_SERVICE_URL}/health")
        except Exception: pass

    async def check_new_emails(self, context: ContextTypes.DEFAULT_TYPE):
        """Background worker tracking unread emails and providing proactive summaries."""
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
                                    kb = [
                                        [InlineKeyboardButton("🤖 AI Summary", callback_data=f"sum_{msg_id}")],
                                        [InlineKeyboardButton("📖 Read Full", callback_data=f"read_{msg_id}")]
                                    ]
                                    await context.bot.send_message(chat_id=uid, text=text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(kb))
            except Exception as e:
                logger.error(f"Email Check Error: {e}")

# Global Singleton Instance
telegram_handler = TelegramBotManager()
