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
        self.ai = AI_Engine(self.gmail)
        self.last_checked_email_id = None
        
        self.app = ApplicationBuilder().token(BOT_TOKEN).build()
        self._register_handlers()
        self.auth.run_server()

    def _register_handlers(self):
        self.app.add_handler(CommandHandler("start", self.start))
        self.app.add_handler(CommandHandler("menu", self.start))
        self.app.add_handler(CallbackQueryHandler(self.start, pattern="^menu$"))
        
        # Read Inbox Flow
        self.app.add_handler(CallbackQueryHandler(self.show_read_options, pattern="^menu_read$"))
        self.app.add_handler(CallbackQueryHandler(self.read_last_five, pattern="^read_5$"))
        self.app.add_handler(CallbackQueryHandler(self.read_last_one, pattern="^read_1$"))
        
        # Dynamic Buttons for Reading
        self.app.add_handler(CallbackQueryHandler(self.handle_delete_email, pattern="^delete_"))
        
        read_specific_conv = ConversationHandler(
            entry_points=[CallbackQueryHandler(self.ask_specific_sender, pattern="^read_specific$")],
            states={ASK_SENDER: [MessageHandler(filters.TEXT & ~filters.COMMAND, self.fetch_specific_email)]},
            fallbacks=[CommandHandler("cancel", self.cancel_flow)]
        )
        self.app.add_handler(read_specific_conv)

        # Compose Email Flow
        compose_conv = ConversationHandler(
            entry_points=[CallbackQueryHandler(self.start_compose, pattern="^menu_compose$"), CallbackQueryHandler(self.start_reply, pattern="^reply_")],
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
        self.app.add_handler(CallbackQueryHandler(self.handle_read_email, pattern="^open_email_"))
        
        # Smart Agent Text Handler
        self.app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, self.handle_general_text))
        
        # Auto Email Checker (60s)
        self.app.job_queue.run_repeating(self.check_new_emails, interval=60, first=10)

    # --- AUTO CHECKER (Clean Text) ---
    async def check_new_emails(self, context: ContextTypes.DEFAULT_TYPE):
        if not self.gmail.get_service(): return
        try:
            emails = self.gmail.list_emails(query='is:unread', max_results=1)
            if emails:
                latest_id = emails[0]['id']
                if self.last_checked_email_id != latest_id:
                    self.last_checked_email_id = latest_id
                    details = self.gmail.get_email_content(latest_id)
                    summary = self.ai.get_summary(details['body'])
                    
                    text = f"🚨 New Email Arrived!\n\n📩 Subject: {details['subject']}\n👤 From: {details['sender']}\n\n✨ Summary:\n{summary}"
                    kb = [[InlineKeyboardButton("📖 Read & Reply", callback_data=f"open_email_{latest_id}")], [InlineKeyboardButton("🔙 Workspace", callback_data="menu")]]
                    await context.bot.send_message(chat_id=OWNER_TELEGRAM_ID, text=text, reply_markup=InlineKeyboardMarkup(kb))
        except Exception as e: print(f"Check error: {e}")

    # --- MAIN DASHBOARD ---
    async def start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        is_callback = update.callback_query is not None
        if is_callback: await update.callback_query.answer()
        
        if str(update.effective_user.id) != str(OWNER_TELEGRAM_ID):
            await self.handle_guest_interaction(update, context)
            return
        
        if not self.gmail.get_service():
            link = self.auth.get_login_link()
            kb = [[InlineKeyboardButton("🔗 Connect Google Account", url=link)]]
            text = "Authentication Required. Please authorize access."
            if is_callback: await update.callback_query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(kb))
            else: await update.message.reply_text(text, reply_markup=InlineKeyboardMarkup(kb))
            return

        kb = [[InlineKeyboardButton("📖 Read Inbox", callback_data="menu_read")], [InlineKeyboardButton("✍️ Compose Email", callback_data="menu_compose")]]
        text = "Workspace Dashboard. What would you like to do?"
        if is_callback: await update.callback_query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(kb))
        else: await update.message.reply_text(text, reply_markup=InlineKeyboardMarkup(kb))

    # --- GENERAL TEXT (AGENTIC) ---
    async def handle_general_text(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        user_id = str(update.effective_user.id)
        if user_id != str(OWNER_TELEGRAM_ID):
            await self.handle_guest_interaction(update, context)
            return

        await context.bot.send_chat_action(chat_id=update.effective_chat.id, action='typing')
        ai_response = self.ai.agent_chat(update.message.text, user_id)
        await update.message.reply_text(ai_response)

    async def handle_guest_interaction(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        await context.bot.send_chat_action(chat_id=update.effective_chat.id, action='typing')
        ai_response = self.ai.guest_chat(update.message.text if update.message else "Hi", str(update.effective_user.id))
        if update.message: await update.message.reply_text(ai_response)

    # --- READING FLOW & DYNAMIC BUTTONS ---
    async def show_read_options(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        query = update.callback_query
        await query.answer()
        if not self.gmail.get_service():
            await query.edit_message_text("Login Required. Type /start to authenticate.")
            return
        kb = [
            [InlineKeyboardButton("📑 Recent 5", callback_data="read_5"), InlineKeyboardButton("📄 Latest", callback_data="read_1")],
            [InlineKeyboardButton("🔍 Search Sender", callback_data="read_specific")],
            [InlineKeyboardButton("🔙 Return", callback_data="menu")]
        ]
        await query.edit_message_text("Inbox Retrieval Menu:", reply_markup=InlineKeyboardMarkup(kb))

    async def read_last_five(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        query = update.callback_query
        await query.answer()
        emails = self.gmail.list_emails(max_results=5)
        if not emails:
            await query.edit_message_text("Inbox empty.", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back", callback_data="menu")]]))
            return
        await query.edit_message_text("Fetching records...")
        for email in emails:
            details = self.gmail.get_email_content(email['id'])
            kb = [[InlineKeyboardButton("📖 Open", callback_data=f"open_email_{email['id']}")]]
            await context.bot.send_message(chat_id=OWNER_TELEGRAM_ID, text=f"From: {details['sender']}\nSubject: {details['subject']}", reply_markup=InlineKeyboardMarkup(kb))

    async def read_last_one(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        query = update.callback_query
        await query.answer()
        emails = self.gmail.list_emails(max_results=1)
        if emails: await self.display_email_content(update, context, emails[0]['id'])
        else: await query.edit_message_text("Inbox empty.", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back", callback_data="menu")]]))

    async def ask_specific_sender(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        query = update.callback_query
        await query.answer()
        await query.edit_message_text("Provide the exact email address to search:")
        return ASK_SENDER

    async def fetch_specific_email(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        msg = await update.message.reply_text("Scanning...")
        details = self.gmail.get_last_email_from_sender(update.message.text)
        if not details:
            await msg.edit_text("No records found.", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back", callback_data="menu")]]))
            return ConversationHandler.END
        await msg.delete()
        await self.display_email_content(update, context, details['id'], is_message=True)
        return ConversationHandler.END

    async def handle_read_email(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        query = update.callback_query
        await query.answer()
        await self.display_email_content(update, context, query.data.split("_")[2])

    async def handle_delete_email(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        query = update.callback_query
        await query.answer()
        msg_id = query.data.split("_")[1]
        success = self.gmail.delete_email(msg_id)
        text = "Email Trashed successfully." if success else "Failed to delete."
        await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Menu", callback_data="menu")]]))

    async def display_email_content(self, update, context, msg_id, is_message=False):
        details = self.gmail.get_email_content(msg_id)
        summary = self.ai.get_summary(details['body'])
        text = f"📩 Subject: {details['subject']}\n👤 From: {details['sender']}\n\n✨ Summary:\n{summary}"
        
        # Dynamic Buttons for Read Flow
        kb = [
            [InlineKeyboardButton("↩️ Reply", callback_data=f"reply_{details['sender']}"), InlineKeyboardButton("🗑️ Delete", callback_data=f"delete_{msg_id}")],
            [InlineKeyboardButton("🔙 Workspace", callback_data="menu")]
        ]
        if is_message: await update.message.reply_text(text, reply_markup=InlineKeyboardMarkup(kb))
        else: await update.callback_query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(kb))

    # --- COMPOSE FLOW ---
    async def start_compose(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        query = update.callback_query
        await query.answer()
        if not self.gmail.get_service():
            await query.edit_message_text("Login Required.")
            return ConversationHandler.END
        await query.edit_message_text("Enter recipient's email address:")
        return ASK_RECIPIENT

    async def start_reply(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        query = update.callback_query
        await query.answer()
        sender_email = query.data.replace("reply_", "")
        context.user_data['draft_to'] = sender_email
        await query.edit_message_text(f"Replying to: {sender_email}\nState your message intent:")
        return ASK_INTENT

    async def get_recipient(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        context.user_data['draft_to'] = update.message.text
        await update.message.reply_text("State the objective of this email:")
        return ASK_INTENT

    async def generate_initial_draft(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        context.user_data['draft_intent'] = update.message.text
        msg = await update.message.reply_text("Drafting...")
        context.user_data['current_draft'] = self.ai.generate_draft(context.user_data['draft_intent'])
        await self.send_draft_review(msg, context)
        return CONFIRM_DRAFT

    async def ask_for_adjustments(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        query = update.callback_query
        await query.answer()
        await query.edit_message_text("Outline adjustments:")
        return ASK_FEEDBACK

    async def regenerate_draft(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        msg = await update.message.reply_text("Applying revisions...")
        context.user_data['current_draft'] = self.ai.modify_draft(context.user_data['current_draft'], update.message.text)
        await self.send_draft_review(msg, context)
        return CONFIRM_DRAFT

    async def send_draft_review(self, message, context):
        draft = context.user_data['current_draft']
        to_email = context.user_data['draft_to']
        text = f"Recipient: {to_email}\n\nDraft Preview:\n\n{draft}"
        
        # Dynamic Buttons for Drafting
        kb = [
            [InlineKeyboardButton("✅ Send", callback_data="send_draft"), InlineKeyboardButton("✍️ Edit", callback_data="recreate_draft")],
            [InlineKeyboardButton("❌ Discard", callback_data="cancel_draft")]
        ]
        await message.edit_text(text, reply_markup=InlineKeyboardMarkup(kb))

    async def send_draft(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        query = update.callback_query
        await query.answer()
        await query.edit_message_text("Transmitting...")
        subject = context.user_data.get('draft_intent', 'Update')[:40]
        result = self.gmail.send_email(context.user_data['draft_to'], subject, context.user_data['current_draft'])
        await query.edit_message_text(f"{result}", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Workspace", callback_data="menu")]]))
        return ConversationHandler.END

    async def cancel_flow(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        text = "Operation canceled."
        kb = [[InlineKeyboardButton("🔙 Workspace", callback_data="menu")]]
        if update.callback_query:
            await update.callback_query.answer()
            await update.callback_query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(kb))
        else: await update.message.reply_text(text, reply_markup=InlineKeyboardMarkup(kb))
        return ConversationHandler.END

    def run(self):
        print("System Online: Polling active...")
        self.app.run_polling()

if __name__ == "__main__":
    BotHandler().run()
