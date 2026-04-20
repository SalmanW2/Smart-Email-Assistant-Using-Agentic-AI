import os
import time
import uvicorn
from fastapi import Request
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, CallbackQueryHandler, MessageHandler, filters, ContextTypes
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
        # Naya handler: Har qisam ki file receive karne ke liye
        self.ptb_app.add_handler(MessageHandler(filters.Document.ALL | filters.PHOTO | filters.VIDEO | filters.AUDIO, self.handle_attachment))
        self.ptb_app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, self.handle_text))

    async def check_new_emails(self, context: ContextTypes.DEFAULT_TYPE):
        service = self.gmail.get_service()
        if not service: return
        try:
            results = service.users().messages().list(userId='me', q='is:unread', maxResults=1).execute()
            messages = results.get('messages', [])
            
            if messages:
                m_id = messages[0]['id']
                if self.last_checked_email_id != m_id:
                    msg_data = service.users().messages().get(userId='me', id=m_id, format='minimal').execute()
                    internal_date = int(msg_data.get('internalDate', 0))
                    
                    if internal_date > self.boot_time:
                        self.last_checked_email_id = m_id
                        meta = self.gmail.get_email_metadata(m_id)
                        text = f"New Email!\nFrom: {meta['sender']}\nSubject: {meta['subject']}"
                        
                        kb = [
                            [InlineKeyboardButton("Read Summary", callback_data=f"sum_{m_id}")],
                            [InlineKeyboardButton("Read Full", callback_data=f"full_{m_id}")],
                            [InlineKeyboardButton("Delete", callback_data=f"del_{m_id}")]
                        ]
                        await context.bot.send_message(chat_id=OWNER_TELEGRAM_ID, text=text, reply_markup=InlineKeyboardMarkup(kb))
        except Exception: pass

    async def start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if str(update.effective_user.id) != str(OWNER_TELEGRAM_ID):
            await self.handle_guest_interaction(update, context)
            return
        
        if not self.gmail.get_service():
            link = self.auth.get_login_link()
            kb = [[InlineKeyboardButton("Connect Google Account", url=link)]]
            if update.message:
                await update.message.reply_text("Authentication Required.", reply_markup=InlineKeyboardMarkup(kb))
            return

        # Faltu buttons remove kar diye, sirf basic dashboard
        kb = [[InlineKeyboardButton("Read Inbox", callback_data="menu_read")], [InlineKeyboardButton("Compose Email", callback_data="menu_compose")]]
        text = "Workspace Dashboard. What would you like to do?"
        if update.callback_query:
            await update.callback_query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(kb))
        else:
            await update.message.reply_text(text, reply_markup=InlineKeyboardMarkup(kb))

    async def handle_button_actions(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        query = update.callback_query
        await query.answer()
        data = query.data

        if data == "menu_read":
            await query.edit_message_text("Please type or send a voice note stating what you want to read (e.g., 'Show me the last 5 emails' or 'Search emails from Ghous').")
        elif data == "menu_compose":
            await query.edit_message_text("Please type or send a voice note stating your intent (e.g., 'Draft an email to HR for sick leave').")
        else:
            action, m_id = data.split("_")[0], data.split("_")[1]

            if action == "sum":
                await query.edit_message_text("Generating summary...")
                body = self.gmail.get_full_body(m_id)
                summary = self.ai.get_summary(body)
                await query.edit_message_text(f"Summary:\n{summary}")
            elif action == "full":
                body = self.gmail.get_full_body(m_id)
                await query.edit_message_text(f"Full Body:\n{body}")
            elif action == "del":
                self.gmail.delete_email(m_id)
                await query.edit_message_text("Email trashed.")

    async def handle_attachment(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        # Guest mode restriction on files
        if str(update.effective_user.id) != str(OWNER_TELEGRAM_ID):
            await self.handle_guest_interaction(update, context)
            return
            
        attachment = update.message.document or (update.message.photo[-1] if update.message.photo else None) or update.message.audio or update.message.video
        if not attachment: return

        # 20MB limit constraint as per FYP report
        if attachment.file_size > 20 * 1024 * 1024:
            await update.message.reply_text("File is larger than 20MB. Telegram restricts bot downloads. Please upload to Google Drive and share the link in the chat instead.")
            return
            
        msg = await update.message.reply_text("Downloading attachment...")
        file = await context.bot.get_file(attachment.file_id)
        
        file_name = getattr(attachment, 'file_name', f"file_{int(time.time())}")
        file_path = f"/tmp/{file_name}"
        await file.download_to_drive(file_path)
        
        # Attachment ko RAM mein save kar diya taake agle step (AI draft) mein attach ho jaye
        self.gmail.current_attachment = file_path
        await msg.edit_text(f"Attachment '{file_name}' received and cached. What do you want to do with it? (e.g., 'Draft an email to sir Affan and attach this file')")

    async def handle_text(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if str(update.effective_user.id) != str(OWNER_TELEGRAM_ID):
            await self.handle_guest_interaction(update, context)
            return
        await context.bot.send_chat_action(chat_id=update.effective_chat.id, action='typing')
        res = self.ai.agent_chat(update.message.text, str(update.effective_user.id))
        await update.message.reply_text(res)

    async def handle_voice(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if str(update.effective_user.id) != str(OWNER_TELEGRAM_ID):
            await self.handle_guest_interaction(update, context)
            return
        
        msg = await update.
