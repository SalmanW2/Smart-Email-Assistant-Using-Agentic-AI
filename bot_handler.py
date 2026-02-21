from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, CallbackQueryHandler, MessageHandler, filters, ContextTypes, ConversationHandler
from config_env import BOT_TOKEN, OWNER_TELEGRAM_ID
from auth_manager import AuthManager
from gmail_client import GmailClient
from ai_engine import AI_Engine

# Conversation States
ASK_SENDER, ASK_RECIPIENT, ASK_INTENT, CONFIRM_DRAFT, ASK_FEEDBACK = range(5)

class BotHandler:
    def __init__(self):
        self.auth = AuthManager()
        self.gmail = GmailClient(self.auth)
        self.ai = AI_Engine()
        
        self.app = ApplicationBuilder().token(BOT_TOKEN).build()
        self._register_handlers()
        self.auth.run_server()

    def _register_handlers(self):
        self.app.add_handler(CommandHandler("start", self.start))
        self.app.add_handler(CommandHandler("menu", self.start))
        
        # Read Inbox Flow
        self.app.add_handler(CallbackQueryHandler(self.show_read_options, pattern="^menu_read$"))
        self.app.add_handler(CallbackQueryHandler(self.read_last_five, pattern="^read_5$"))
        self.app.add_handler(CallbackQueryHandler(self.read_last_one, pattern="^read_1$"))
        
        read_specific_conv = ConversationHandler(
            entry_points=[CallbackQueryHandler(self.ask_specific_sender, pattern="^read_specific$")],
            states={
                ASK_SENDER: [MessageHandler(filters.TEXT & ~filters.COMMAND, self.fetch_specific_email)]
            },
            fallbacks=[CommandHandler("cancel", self.cancel_flow)]
        )
        self.app.add_handler(read_specific_conv)

        # Compose Email Flow (Looping)
        compose_conv = ConversationHandler(
            entry_points=[CallbackQueryHandler(self.start_compose, pattern="^menu_compose$")],
            states={
                ASK_RECIPIENT: [MessageHandler(filters.TEXT & ~filters.COMMAND, self.get_recipient)],
                ASK_INTENT: [MessageHandler(filters.TEXT & ~filters.COMMAND, self.generate_initial_draft)],
                CONFIRM_DRAFT: [
                    CallbackQueryHandler(self.send_draft, pattern="^send_draft$"),
                    CallbackQueryHandler(self.ask_for_adjustments, pattern="^recreate_draft$"),
                    CallbackQueryHandler(self.cancel_flow, pattern="^cancel_draft$")
                ],
                ASK_FEEDBACK: [MessageHandler(filters.TEXT & ~filters.COMMAND, self.regenerate_draft)]
            },
            fallbacks=[CommandHandler("cancel", self.cancel_flow)]
        )
        self.app.add_handler(compose_conv)

        # Handle Read button inside email list
        self.app.add_handler(CallbackQueryHandler(self.handle_read_email, pattern="^open_email_"))

    # --- MAIN DASHBOARD ---
    async def start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if str(update.effective_user.id) != str(OWNER_TELEGRAM_ID): return
        
        if not self.gmail.get_service():
            link = self.auth.get_login_link()
            kb = [[InlineKeyboardButton("🔗 Connect Google Account", url=link)]]
            await update.message.reply_text("⚠️ **Authentication Required**\nPlease authorize access to continue.", reply_markup=InlineKeyboardMarkup(kb))
            return

        kb = [
            [InlineKeyboardButton("📖 Read Inbox", callback_data="menu_read")],
            [InlineKeyboardButton("✍️ Compose Email", callback_data="menu_compose")]
        ]
        
        text = "⚙️ **Dashboard**\nSelect an operation below to proceed."
        if update.message:
            await update.message.reply_text(text, reply_markup=InlineKeyboardMarkup(kb))
        else:
            await update.callback_query.message.edit_text(text, reply_markup=InlineKeyboardMarkup(kb))

    # --- READING FLOW ---
    async def show_read_options(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        query = update.callback_query
        await query.answer()
        kb = [
            [InlineKeyboardButton("📑 Last 5 Emails", callback_data="read_5")],
            [InlineKeyboardButton("📄 Latest Email", callback_data="read_1")],
            [InlineKeyboardButton("🔍 Search by Sender", callback_data="read_specific")],
            [InlineKeyboardButton("🔙 Back", callback_data="menu")]
        ]
        await query.edit_message_text("📚 **Inbox Options**\nHow would you like to review your emails?", reply_markup=InlineKeyboardMarkup(kb))

    async def read_last_five(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        query = update.callback_query
        await query.answer()
        emails = self.gmail.list_emails(max_results=5)
        if not emails:
            await query.edit_message_text("📭 Your inbox is empty.")
            return
        
        await query.edit_message_text("📑 **Fetching Last 5 Emails...**")
        for email in emails:
            details = self.gmail.get_email_content(email['id'])
            kb = [[InlineKeyboardButton("📖 Read Email", callback_data=f"open_email_{email['id']}")]]
            await context.bot.send_message(chat_id=OWNER_TELEGRAM_ID, text=f"👤 **From:** {details['sender']}\n📌 **Subject:** {details['subject']}", reply_markup=InlineKeyboardMarkup(kb))

    async def read_last_one(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        query = update.callback_query
        await query.answer()
        emails = self.gmail.list_emails(max_results=1)
        if emails:
            await self.display_email_content(update, context, emails[0]['id'])
        else:
            await query.edit_message_text("📭 Your inbox is empty.")

    async def ask_specific_sender(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        query = update.callback_query
        await query.answer()
        await query.edit_message_text("🔍 Please enter the email address of the sender you want to search for:")
        return ASK_SENDER

    async def fetch_specific_email(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        sender_email = update.message.text
        msg = await update.message.reply_text("⏳ Searching...")
        details = self.gmail.get_last_email_from_sender(sender_email)
        
        if not details:
            await msg.edit_text(f"❌ No emails found from {sender_email}.")
            return ConversationHandler.END
            
        await msg.delete()
        await self.display_email_content(update, context, details['id'], is_message=True)
        return ConversationHandler.END

    async def handle_read_email(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        query = update.callback_query
        await query.answer()
        msg_id = query.data.split("_")[2]
        await self.display_email_content(update, context, msg_id)

    async def display_email_content(self, update, context, msg_id, is_message=False):
        details = self.gmail.get_email_content(msg_id)
        summary = self.ai.get_summary(details['body'])
        text = f"📩 **{details['subject']}**\n👤 **From:** {details['sender']}\n\n✨ **AI Summary:**\n{summary}"
        kb = [[InlineKeyboardButton("🔙 Menu", callback_data="menu")]]
        
        if is_message:
            await update.message.reply_text(text, reply_markup=InlineKeyboardMarkup(kb))
        else:
            await update.callback_query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(kb))

    # --- COMPOSE FLOW (LOOP) ---
    async def start_compose(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        query = update.callback_query
        await query.answer()
        await query.edit_message_text("✍️ **Compose Email**\nPlease provide the recipient's email address:")
        return ASK_RECIPIENT

    async def get_recipient(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        context.user_data['draft_to'] = update.message.text
        await update.message.reply_text("📝 What is the primary objective or message of this email? (e.g., 'Ask for a project update')")
        return ASK_INTENT

    async def generate_initial_draft(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        intent = update.message.text
        context.user_data['draft_intent'] = intent
        msg = await update.message.reply_text("⏳ Generating professional draft...")
        
        draft = self.ai.generate_draft(intent)
        context.user_data['current_draft'] = draft
        
        await self.send_draft_review(msg, context)
        return CONFIRM_DRAFT

    async def ask_for_adjustments(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        query = update.callback_query
        await query.answer()
        await query.edit_message_text("🔄 Please specify what changes you would like to make to the draft:")
        return ASK_FEEDBACK

    async def regenerate_draft(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        feedback = update.message.text
        msg = await update.message.reply_text("⏳ Adjusting draft based on your feedback...")
        
        current_draft = context.user_data['current_draft']
        new_draft = self.ai.modify_draft(current_draft, feedback)
        context.user_data['current_draft'] = new_draft
        
        await self.send_draft_review(msg, context)
        return CONFIRM_DRAFT

    async def send_draft_review(self, message, context):
        draft = context.user_data['current_draft']
        to_email = context.user_data['draft_to']
        text = f"✉️ **Recipient:** {to_email}\n\n📄 **Draft Preview:**\n────────────────\n{draft}\n────────────────\n\nPlease select an action:"
        
        kb = [
            [InlineKeyboardButton("✅ Send Email", callback_data="send_draft")],
            [InlineKeyboardButton("🔄 Recreate / Edit", callback_data="recreate_draft")],
            [InlineKeyboardButton("❌ Cancel", callback_data="cancel_draft")]
        ]
        await message.edit_text(text, reply_markup=InlineKeyboardMarkup(kb))

    async def send_draft(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        query = update.callback_query
        await query.answer()
        await query.edit_message_text("🚀 Sending email...")
        
        to = context.user_data['draft_to']
        body = context.user_data['current_draft']
        # Extract a basic subject from intent for manual compose
        subject = context.user_data.get('draft_intent', 'Update')[:30] + "..."
        
        result = self.gmail.send_email(to, subject, body)
        
        kb = [[InlineKeyboardButton("🔙 Return to Dashboard", callback_data="menu")]]
        await query.edit_message_text(f"{result}", reply_markup=InlineKeyboardMarkup(kb))
        return ConversationHandler.END

    async def cancel_flow(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if update.callback_query:
            await update.callback_query.answer()
            await update.callback_query.edit_message_text("❌ Operation cancelled.", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Dashboard", callback_data="menu")]]))
        else:
            await update.message.reply_text("❌ Operation cancelled.", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Dashboard", callback_data="menu")]]))
        return ConversationHandler.END

    def run(self):
        print("🚀 Bot is Polling via Telegram...")
        self.app.run_polling()

if __name__ == "__main__":
    bot = BotHandler()
    bot.run()