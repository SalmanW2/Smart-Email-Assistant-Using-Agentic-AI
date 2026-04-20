import os
import time
import uvicorn
from fastapi import Request
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (ApplicationBuilder, CommandHandler, CallbackQueryHandler,
                           MessageHandler, filters, ContextTypes)
from config_env import BOT_TOKEN, OWNER_TELEGRAM_ID, WEBHOOK_URL
from auth_manager import auth_manager_instance, app as fastapi_app
from gmail_client import GmailClient
from ai_engine import AI_Engine
 
 
class BotHandler:
    def __init__(self):
        self.auth = auth_manager_instance
        self.gmail = GmailClient(self.auth)
        self.ai = AI_Engine(self.gmail)
        self.last_checked_email_id = None
        self.boot_time = int(time.time() * 1000)
 
        self.ptb_app = ApplicationBuilder().token(BOT_TOKEN).build()
        self._register_handlers()
 
    def _register_handlers(self):
        self.ptb_app.add_handler(CommandHandler("start", self.start))
        self.ptb_app.add_handler(CallbackQueryHandler(self.handle_button_actions))
        self.ptb_app.add_handler(MessageHandler(filters.VOICE, self.handle_voice))
        self.ptb_app.add_handler(MessageHandler(
            filters.Document.ALL | filters.PHOTO | filters.VIDEO | filters.AUDIO,
            self.handle_attachment
        ))
        self.ptb_app.add_handler(MessageHandler(
            filters.TEXT & ~filters.COMMAND, self.handle_text
        ))
 
    # ---------------------------------------------------------------
    # Background job: new email check every 60s
    # ---------------------------------------------------------------
    async def check_new_emails(self, context: ContextTypes.DEFAULT_TYPE):
        service = self.gmail.get_service()
        if not service:
            return
        try:
            results = service.users().messages().list(
                userId='me', q='is:unread', maxResults=1
            ).execute()
            messages = results.get('messages', [])
 
            if messages:
                m_id = messages[0]['id']
                if self.last_checked_email_id != m_id:
                    msg_data = service.users().messages().get(
                        userId='me', id=m_id, format='minimal'
                    ).execute()
                    internal_date = int(msg_data.get('internalDate', 0))
 
                    if internal_date > self.boot_time:
                        self.last_checked_email_id = m_id
                        meta = self.gmail.get_email_metadata(m_id)
                        text = (
                            f"New Email!\n"
                            f"From: {meta['sender']}\n"
                            f"Subject: {meta['subject']}"
                        )
                        kb = [
                            [InlineKeyboardButton("Read Summary", callback_data=f"sum_{m_id}")],
                            [InlineKeyboardButton("Read Full",    callback_data=f"full_{m_id}")],
                            [InlineKeyboardButton("Delete",       callback_data=f"del_{m_id}")]
                        ]
                        await context.bot.send_message(
                            chat_id=OWNER_TELEGRAM_ID,
                            text=text,
                            reply_markup=InlineKeyboardMarkup(kb)
                        )
        except Exception:
            pass
 
    # ---------------------------------------------------------------
    # /start command
    # ---------------------------------------------------------------
    async def start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if str(update.effective_user.id) != str(OWNER_TELEGRAM_ID):
            await self.handle_guest_interaction(update, context)
            return
 
        if not self.gmail.get_service():
            link = self.auth.get_login_link()
            kb = [[InlineKeyboardButton("Connect Google Account", url=link)]]
            if update.message:
                await update.message.reply_text(
                    "Authentication Required. Please connect your Gmail account.",
                    reply_markup=InlineKeyboardMarkup(kb)
                )
            return
 
        kb = [
            [InlineKeyboardButton("Read Inbox",    callback_data="menu_read")],
            [InlineKeyboardButton("Compose Email", callback_data="menu_compose")]
        ]
        text = "Workspace Dashboard. What would you like to do?"
        if update.callback_query:
            await update.callback_query.edit_message_text(
                text, reply_markup=InlineKeyboardMarkup(kb)
            )
        else:
            await update.message.reply_text(text, reply_markup=InlineKeyboardMarkup(kb))
 
    # ---------------------------------------------------------------
    # Inline button handler
    # ---------------------------------------------------------------
    async def handle_button_actions(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        query = update.callback_query
        await query.answer()
        data = query.data
 
        if data == "menu_read":
            await query.edit_message_text(
                "Type what you want to read.\n"
                "Examples:\n"
                "- Show last 5 emails\n"
                "- Search emails from Ghous\n"
                "- Any unread emails today?"
            )
        elif data == "menu_compose":
            await query.edit_message_text(
                "Type your intent.\n"
                "Examples:\n"
                "- Draft an email to HR for sick leave\n"
                "- Email Kashan about meeting tomorrow"
            )
        else:
            # data format: "sum_<id>" / "full_<id>" / "del_<id>"
            parts = data.split("_", 1)
            if len(parts) != 2:
                return
            action, m_id = parts
 
            if action == "sum":
                await query.edit_message_text("Generating summary, please wait...")
                body = self.gmail.get_full_body(m_id)
                summary = self.ai.get_summary(body)
                await query.edit_message_text(f"Summary:\n\n{summary}")
 
            elif action == "full":
                body = self.gmail.get_full_body(m_id)
                # Telegram message limit 4096 chars
                if len(body) > 4000:
                    body = body[:4000] + "\n\n[Truncated]"
                await query.edit_message_text(f"Full Email:\n\n{body}")
 
            elif action == "del":
                self.gmail.delete_email(m_id)
                await query.edit_message_text("Email moved to trash.")
 
    # ---------------------------------------------------------------
    # File/attachment handler
    # ---------------------------------------------------------------
    async def handle_attachment(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if str(update.effective_user.id) != str(OWNER_TELEGRAM_ID):
            await self.handle_guest_interaction(update, context)
            return
 
        attachment = (
            update.message.document
            or (update.message.photo[-1] if update.message.photo else None)
            or update.message.audio
            or update.message.video
        )
        if not attachment:
            return
 
        if attachment.file_size > 20 * 1024 * 1024:
            await update.message.reply_text(
                "File is larger than 20MB. Telegram restricts bot downloads.\n"
                "Please upload to Google Drive and share the link in chat instead."
            )
            return
 
        msg = await update.message.reply_text("Downloading attachment...")
        file = await context.bot.get_file(attachment.file_id)
 
        file_name = getattr(attachment, 'file_name', f"file_{int(time.time())}")
        file_path = f"/tmp/{file_name}"
        await file.download_to_drive(file_path)
 
        self.gmail.current_attachment = file_path
        await msg.edit_text(
            f"Attachment '{file_name}' received and ready to send.\n"
            f"Now tell me what to do with it.\n"
            f"Example: Draft an email to sir Affan and attach this file"
        )
 
    # ---------------------------------------------------------------
    # Text message handler
    # ---------------------------------------------------------------
    async def handle_text(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if str(update.effective_user.id) != str(OWNER_TELEGRAM_ID):
            await self.handle_guest_interaction(update, context)
            return
 
        await context.bot.send_chat_action(
            chat_id=update.effective_chat.id, action='typing'
        )
        res = self.ai.agent_chat(
            update.message.text, str(update.effective_user.id)
        )
        await update.message.reply_text(res)
 
    # ---------------------------------------------------------------
    # Voice message handler  <-- YEH WALA ADHOORA THA, AB COMPLETE HAI
    # ---------------------------------------------------------------
    async def handle_voice(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if str(update.effective_user.id) != str(OWNER_TELEGRAM_ID):
            await self.handle_guest_interaction(update, context)
            return
 
        msg = await update.message.reply_text("Processing voice note...")
 
        try:
            voice = update.message.voice
            file = await context.bot.get_file(voice.file_id)
            file_path = f"/tmp/voice_{int(time.time())}.ogg"
            await file.download_to_drive(file_path)
 
            # Gemini Flash se transcribe karo (Whisper ki zaroorat nahi)
            transcribed_text = self.ai.transcribe_audio(file_path)
 
            # Cleanup temp file
            if os.path.exists(file_path):
                os.remove(file_path)
 
            if not transcribed_text:
                await msg.edit_text("Could not understand the voice note. Please try again.")
                return
 
            await msg.edit_text(f"You said: {transcribed_text}\n\nProcessing...")
 
            # Transcribed text ko normal agent chat mein bhejo
            response = self.ai.agent_chat(transcribed_text, str(update.effective_user.id))
            await update.message.reply_text(response)
 
        except Exception as e:
            await msg.edit_text(f"Voice processing error: {str(e)}")
 
    # ---------------------------------------------------------------
    # Guest user handler
    # ---------------------------------------------------------------
    async def handle_guest_interaction(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        user_id = str(update.effective_user.id)
        text = ""
 
        if update.message and update.message.text:
            text = update.message.text
        elif update.message and update.message.voice:
            text = "Hello"
        elif update.callback_query:
            text = "Hello"
            await update.callback_query.answer()
        else:
            text = "Hello"
 
        response = self.ai.guest_chat(text, user_id)
        if update.message:
            await update.message.reply_text(response)
        elif update.callback_query:
            await update.callback_query.message.reply_text(response)
 
 
# ---------------------------------------------------------------
# FastAPI webhook endpoint
# ---------------------------------------------------------------
bot_handler_instance = BotHandler()
 
 
@fastapi_app.post("/webhook")
async def webhook(request: Request):
    data = await request.json()
    update = Update.de_json(data, bot_handler_instance.ptb_app.bot)
    await bot_handler_instance.ptb_app.process_update(update)
    return {"ok": True}
 
 
@fastapi_app.on_event("startup")
async def on_startup():
    await bot_handler_instance.ptb_app.initialize()
    await bot_handler_instance.ptb_app.bot.set_webhook(url=f"{WEBHOOK_URL}/webhook")
 
    # Background email checker har 60 second
    bot_handler_instance.ptb_app.job_queue.run_repeating(
        bot_handler_instance.check_new_emails, interval=60, first=10
    )
    await bot_handler_instance.ptb_app.start()
 
 
@fastapi_app.on_event("shutdown")
async def on_shutdown():
    await bot_handler_instance.ptb_app.stop()
 
 
if __name__ == "__main__":
    uvicorn.run("bot_handler:fastapi_app", host="0.0.0.0", port=int(os.getenv("PORT", 8080)))
