from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, CallbackQueryHandler, MessageHandler, filters, ContextTypes, ConversationHandler
from config_env import BOT_TOKEN, OWNER_TELEGRAM_ID
from auth_manager import AuthManager
from gmail_client import GmailClient
from ai_engine import AI_Engine

# Conversation States
WAITING_FOR_INSTRUCTION = 1
CONFIRM_DRAFT = 2

class BotHandler:
    def __init__(self):
        self.auth = AuthManager()
        self.gmail = GmailClient(self.auth)
        self.ai = AI_Engine()
        
        # Init Bot
        self.app = ApplicationBuilder().token(BOT_TOKEN).build()
        self._register_handlers()
        
        # Start Auth Server
        self.auth.run_server()
        
        # ✅ OLD FEATURE RESTORED: Background Job (Har 60 sec baad check karega)
        if self.app.job_queue:
            self.app.job_queue.run_repeating(self.auto_check_mail, interval=60, first=10)

    def _register_handlers(self):
        self.app.add_handler(CommandHandler("start", self.start))
        self.app.add_handler(CommandHandler("inbox", self.cmd_inbox))
        self.app.add_handler(CallbackQueryHandler(self.handle_read, pattern="^read_"))
        
        reply_conv = ConversationHandler(
            entry_points=[CallbackQueryHandler(self.start_reply_flow, pattern="start_reply")],
            states={
                WAITING_FOR_INSTRUCTION: [MessageHandler(filters.TEXT & ~filters.COMMAND, self.process_ai_draft)],
                CONFIRM_DRAFT: [
                    CallbackQueryHandler(self.send_final, pattern="send_final"),
                    CallbackQueryHandler(self.cancel, pattern="cancel")
                ]
            },
            fallbacks=[CallbackQueryHandler(self.cancel, pattern="cancel")]
        )
        self.app.add_handler(reply_conv)

    async def auto_check_mail(self, context: ContextTypes.DEFAULT_TYPE):
        """Ye purana feature wapis aa gaya: Auto Check"""
        emails = self.gmail.list_emails(max_results=1)
        if emails:
            last_id = context.bot_data.get('last_seen_id')
            current_id = emails[0]['id']
            
            if current_id != last_id:
                context.bot_data['last_seen_id'] = current_id
                details = self.gmail.get_email_content(current_id)
                
                # Notify User
                btn = [[InlineKeyboardButton(f"📖 Read Now", callback_data=f"read_{current_id}")]]
                await context.bot.send_message(
                    chat_id=OWNER_TELEGRAM_ID,
                    text=f"🚨 **New Email Received!**\n\n👤 {details['sender']}\n📌 {details['subject']}",
                    reply_markup=InlineKeyboardMarkup(btn)
                )

    async def start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if str(update.effective_user.id) != str(OWNER_TELEGRAM_ID): return
        
        if not self.gmail.get_service():
            link = self.auth.get_login_link()
            kb = [[InlineKeyboardButton("🔗 Login Gmail", url=link)]]
            await update.message.reply_text("⚠️ **Authentication Required**", reply_markup=InlineKeyboardMarkup(kb))
            return

        await update.message.reply_text("🤖 **System Online**\nI will notify you of new emails automatically.")

    async def cmd_inbox(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        emails = self.gmail.list_emails()
        if not emails:
            await update.message.reply_text("📭 No emails found.")
            return

        for email in emails:
            details = self.gmail.get_email_content(email['id']) 
            btn = [[InlineKeyboardButton(f"📖 Read", callback_data=f"read_{email['id']}")]]
            await update.message.reply_text(f"👤 {details['sender']}\n📌 {details['subject']}", reply_markup=InlineKeyboardMarkup(btn))

    async def handle_read(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        query = update.callback_query
        await query.answer()
        msg_id = query.data.split("_")[1]
        
        details = self.gmail.get_email_content(msg_id)
        context.user_data['last_details'] = details
        
        summary = self.ai.get_summary(details['body'])
        
        text = f"📩 **{details['subject']}**\n\n✨ **Summary:**\n{summary}"
        kb = [[InlineKeyboardButton("✍️ Draft Reply", callback_data="start_reply")]]
        await query.edit_message_text(text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(kb))

    async def start_reply_flow(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        query = update.callback_query
        await query.answer()
        await query.edit_message_text("🎤 **Instruction:** Reply mein kya bolna hai?")
        return WAITING_FOR_INSTRUCTION

    async def process_ai_draft(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        instruction = update.message.text
        original_body = context.user_data['last_details']['body']
        
        await update.message.reply_text("⏳ Generating Draft...")
        draft = self.ai.generate_draft(original_body, instruction)
        context.user_data['final_draft'] = draft
        
        kb = [[InlineKeyboardButton("🚀 Send Now", callback_data="send_final"), InlineKeyboardButton("❌ Cancel", callback_data="cancel")]]
        await update.message.reply_text(f"📝 **Draft Preview:**\n\n{draft}", reply_markup=InlineKeyboardMarkup(kb))
        return CONFIRM_DRAFT

    async def send_final(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        query = update.callback_query
        details = context.user_data['last_details']
        result = self.gmail.send_email(details['sender'], f"Re: {details['subject']}", context.user_data['final_draft'])
        await query.edit_message_text(result)
        return ConversationHandler.END

    async def cancel(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        await update.callback_query.edit_message_text("❌ Action Cancelled")
        return ConversationHandler.END

    def run(self):
        print("🚀 Bot is Polling...")
        self.app.run_polling()

if __name__ == "__main__":
    bot = BotHandler()
    bot.run()