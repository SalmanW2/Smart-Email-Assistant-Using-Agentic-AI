import os
import time
import uvicorn
import asyncio
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
        self.notified_emails = set() # Multiple emails track karne ke liye
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
 
    # Background job: new email check every 60s
    async def check_new_emails(self, context: ContextTypes.DEFAULT_TYPE):
        service = self.gmail.get_service()
        if not service:
            return
        try:
            # Check up to 3 latest unread emails
            results = service.users().messages().list(
                userId='me', q='is:unread', maxResults=3
            ).execute()
            messages = results.get('messages', [])
 
            for msg in messages:
                m_id = msg['id']
                if m_id not in self.notified_emails:
                    msg_data = service.users().messages().get(
                        userId='me', id=m_id, format='minimal'
                    ).execute()
                    internal_date = int(msg_data.get('internalDate', 0))
 
                    if internal_date > self.boot_time:
                        self.notified_emails.add(m_id)
                        meta = self.gmail.get_email_metadata(m_id)
                        
                        # UI/UX Improved Notification
                        text = (
                            f"🔔 *New Email Received!*\n\n"
                            f"👤 *From:* {meta['sender']}\n"
                            f"📝 *Subject:* {meta['subject']}\n\n"
                            f"What would you like to do?"
                        )
                        kb = [
                            [InlineKeyboardButton("🤖 Generate Summary", callback_data=f"sum_{m_id}")],
                            [InlineKeyboardButton("📖 Read Full Email",    callback_data=f"full_{m_id}")],
                            [InlineKeyboardButton("🗑️ Delete",       callback_data=f"del_{m_id}")]
                        ]
                        await context.bot.send_message(
                            chat_id=OWNER_TELEGRAM_ID,
                            text=text,
                            parse_mode="Markdown",
                            reply_markup=InlineKeyboardMarkup(kb)
                        )
        except Exception:
            pass
 
    async def start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if str(update.effective_user.id) != str(OWNER_TELEGRAM_ID):
            await self.handle_guest_interaction(update, context)
            return
 
        if not self.gmail.get_service():
            link = self.auth.get_login_link()
            kb = [[InlineKeyboardButton("🔗 Connect Google Account", url=link)]]
            if update.message:
                await update.message.reply_text(
                    "⚠️ *Authentication Required.*\nPlease connect your Gmail account to proceed.",
                    parse_mode="Markdown",
                    reply_markup=InlineKeyboardMarkup(kb)
                )
            return
 
        kb = [
            [InlineKeyboardButton("📥 Read Inbox",    callback_data="menu_read")],
            [InlineKeyboardButton("✍️ Compose Email", callback_data="menu_compose")]
        ]
        text = "🎛️ *Workspace Dashboard*\nWelcome! What would you like to do today?"
        if update.callback_query:
            await update.callback_query.edit_message_text(text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(kb))
        else:
            await update.message.reply_text(text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(kb))
 
    async def handle_button_actions(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        query = update.callback_query
        await query.answer()
        data = query.data
 
        if data == "menu_read":
            await query.edit_message_text(
                "📥 *Inbox Mode*\nType what you want to read.\n\n"
                "_Examples:_\n"
                "- Show last 5 emails\n"
                "- Search emails from HR\n"
                "- Any unread emails today?",
                parse_mode="Markdown"
            )
        elif data == "menu_compose":
            await query.edit_message_text(
                "✍️ *Compose Mode*\nType your intent.\n\n"
                "_Examples:_\n"
                "- Draft an email to HR for sick leave\n"
                "- Email Ali about the meeting tomorrow",
                parse_mode="Markdown"
            )
        else:
            parts = data.split("_", 1)
            if len(parts) != 2: return
            action, m_id = parts
 
            if action == "sum":
                await query.edit_message_text("⏳ Generating AI Summary...")
                body = self.gmail.get_full_body(m_id)
                summary = await asyncio.to_thread(self.ai.get_summary, body)
                await query.edit_message_text(f"🤖 *AI Summary:*\n\n{summary}", parse_mode="Markdown")
 
            elif action == "full":
                await query.edit_message_text("⏳ Fetching...")
                body = self.gmail.get_full_body(m_id)
                if len(body) > 4000:
                    body = body[:4000] + "\n\n[Truncated]"
                await query.edit_message_text(f"📖 *Full Email:*\n\n{body}")
 
            elif action == "del":
                self.gmail.delete_email(m_id)
                await query.edit_message_text("🗑️ Email moved to trash.")
 
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
        if not attachment: return
 
        if attachment.file_size > 20 * 1024 * 1024:
            await update.message.reply_text(
                "❌ *File is larger than 20MB.*\nTelegram limits bots to 20MB downloads. Please upload to Google Drive and share the link.",
                parse_mode="Markdown"
            )
            return
 
        msg = await update.message.reply_text("⏳ Downloading attachment...")
        file = await context.bot.get_file(attachment.file_id)
 
        file_name = getattr(attachment, 'file_name', f"file_{int(time.time())}")
        file_path = f"/tmp/{file_name}"
        await file.download_to_drive(file_path)
 
        self.gmail.current_attachment = file_path
        await msg.edit_text(
            f"📎 *Attachment Ready:*\n`{file_name}`\n\nNow tell me what to do with it.\n_Example: Draft an email to Sir Affan and attach this file._",
            parse_mode="Markdown"
        )
 
    async def handle_text(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if str(update.effective_user.id) != str(OWNER_TELEGRAM_ID):
            await self.handle_guest_interaction(update, context)
            return
 
        await context.bot.send_chat_action(chat_id=update.effective_chat.id, action='typing')
        res = await asyncio.to_thread(self.ai.agent_chat, update.message.text, str(update.effective_user.id))
        await update.message.reply_text(res)
 
    async def handle_voice(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if str(update.effective_user.id) != str(OWNER_TELEGRAM_ID):
            await self.handle_guest_interaction(update, context)
            return
 
        msg = await update.message.reply_text("🎙️ Processing voice note...")
 
        try:
            voice = update.message.voice
            file = await context.bot.get_file(voice.file_id)
            file_path = f"/tmp/voice_{int(time.time())}.ogg"
            await file.download_to_drive(file_path)
 
            transcribed_text = await asyncio.to_thread(self.ai.transcribe_audio, file_path)
 
            if os.path.exists(file_path):
                os.remove(file_path)
 
            if not transcribed_text:
                await msg.edit_text("❌ Could not understand the voice note. Please try again.")
                return
 
            await msg.edit_text(f"🗣️ *You said:* {transcribed_text}\n\n⏳ Processing...", parse_mode="Markdown")
            response = await asyncio.to_thread(self.ai.agent_chat, transcribed_text, str(update.effective_user.id))
            await update.message.reply_text(response)
 
        except Exception as e:
            await msg.edit_text(f"❌ Voice processing error: {str(e)}")
 
    async def handle_guest_interaction(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        user_id = str(update.effective_user.id)
        response = self.ai.guest_chat("Hello", user_id)
        if update.message:
            await update.message.reply_text(response)
        elif update.callback_query:
            await update.callback_query.message.reply_text(response)
 
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
 
    bot_handler_instance.ptb_app.job_queue.run_repeating(
        bot_handler_instance.check_new_emails, interval=60, first=10
    )
    await bot_handler_instance.ptb_app.start()
 
@fastapi_app.on_event("shutdown")
async def on_shutdown():
    await bot_handler_instance.ptb_app.stop()
 
if __name__ == "__main__":
    uvicorn.run("bot_handler:fastapi_app", host="0.0.0.0", port=int(os.getenv("PORT", 8080)))   