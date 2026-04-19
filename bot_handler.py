import time
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, CallbackQueryHandler, MessageHandler, filters, ContextTypes, ConversationHandler
from config_env import BOT_TOKEN, OWNER_TELEGRAM_ID
from auth_manager import auth_manager_instance
from gmail_client import GmailClient
from ai_engine import AI_Engine

ASK_SENDER, ASK_RECIPIENT, ASK_INTENT, CONFIRM_DRAFT, ASK_FEEDBACK = range(5)

class BotHandler:
    def __init__(self):
        self.auth = auth_manager_instance
        self.gmail = GmailClient(self.auth)
        self.ai = AI_Engine(self.gmail)
        self.last_checked_email_id = None
        # Bot start hote waqt ka time (Unix Timestamp in milliseconds)
        self.boot_time = int(time.time() * 1000)
        
        self.app = ApplicationBuilder().token(BOT_TOKEN).build()
        self._register_handlers()
        self.auth.run_server()

    def _register_handlers(self):
        self.app.add_handler(CommandHandler("start", self.start))
        self.app.add_handler(CommandHandler("menu", self.start))
        self.app.add_handler(CallbackQueryHandler(self.start, pattern="^menu$"))
        self.app.add_handler(CallbackQueryHandler(self.show_read_options, pattern="^menu_read$"))
        self.app.add_handler(CallbackQueryHandler(self.read_last_five, pattern="^read_5$"))
        self.app.add_handler(CallbackQueryHandler(self.read_last_one, pattern="^read_1$"))
        self.app.add_handler(CallbackQueryHandler(self.handle_delete_email, pattern="^delete_"))
        
        read_specific_conv = ConversationHandler(
            entry_points=[CallbackQueryHandler(self.ask_specific_sender, pattern="^read_specific$")],
            states={ASK_SENDER: [MessageHandler(filters.TEXT & ~filters.COMMAND, self.fetch_specific_email)]},
            fallbacks=[CommandHandler("cancel", self.cancel_flow)]
        )
        self.app.add_handler(read_specific_conv)

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
        self.app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, self.handle_general_text))
        
        # Checking every 5 minutes (300s) to save quota
        self.app.job_queue.run_repeating(self.check_new_emails, interval=300, first=10)

    async def check_new_emails(self, context: ContextTypes.DEFAULT_TYPE):
        service = self.gmail.get_service()
        if not service: return
        try:
            # Sirf unread emails dekhein
            results = service.users().messages().list(userId='me', q='is:unread', maxResults=1).execute()
            messages = results.get('messages', [])
            
            if messages:
                m_id = messages[0]['id']
                if self.last_checked_email_id != m_id:
                    # Email ke details lein taake waqt check ho sake
                    msg_data = service.users().messages().get(userId='me', id=m_id, format='minimal').execute()
                    internal_date = int(msg_data.get('internalDate', 0))
                    
                    # Agar email bot start hone ke BAAD aayi hai
                    if internal_date > self.boot_time:
                        self.last_checked_email_id = m_id
                        details = self.gmail.get_email_content(m_id)
                        summary = self.ai.get_summary(details['body'])
                        
                        text = f"New Email Arrived!\n\nSubject: {details['subject']}\nFrom: {details['sender']}\n\nSummary:\n{summary}"
                        kb = [[InlineKeyboardButton("Read and Reply", callback_data=f"open_email_{m_id}")], [InlineKeyboardButton("Workspace", callback_data="menu")]]
                        await context.bot.send_message(chat_id=OWNER_TELEGRAM_ID, text=text, reply_markup=InlineKeyboardMarkup(kb))
        except Exception: pass

    async def start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        is_cb = update.callback_query is not None
        if is_cb: await update.callback_query.answer()
        
        if str(update.effective_user.id) != str(OWNER_TELEGRAM_ID):
            await self.handle_guest_interaction(update, context)
            return
        
        if not self.gmail.get_service():
            link = self.auth.get_login_link()
            kb = [[InlineKeyboardButton("Connect Google Account", url=link)]]
            text = "Authentication Required. Please authorize access."
            if is_cb: await update.callback_query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(kb))
            else: await update.message.reply_text(text, reply_markup=InlineKeyboardMarkup(kb))
            return

        kb = [[InlineKeyboardButton("Read Inbox", callback_data="menu_read")], [InlineKeyboardButton("Compose Email", callback_data="menu_compose")]]
        text = "Workspace Dashboard. What would you like to do?"
        if is_cb: await update.callback_query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(kb))
        else: await update.message.reply_text(text, reply_markup=InlineKeyboardMarkup(kb))

    async def handle_general_text(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if str(update.effective_user.id) != str(OWNER_TELEGRAM_ID):
            await self.handle_guest_interaction(update, context)
            return
        await context.bot.send_chat_action(chat_id=update.effective_chat.id, action='typing')
        res = self.ai.agent_chat(update.message.text, str(update.effective_user.id))
        await update.message.reply_text(res)

    async def handle_guest_interaction(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        await context.bot.send_chat_action(chat_id=update.effective_chat.id, action='typing')
        res = self.ai.guest_chat(update.message.text if update.message else "Hi", str(update.effective_user.id))
        if update.message: await update.message.reply_text(res)

    async def show_read_options(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        query = update.callback_query
        await query.answer()
        kb = [
            [InlineKeyboardButton("Recent 5", callback_data="read_5"), InlineKeyboardButton("Latest", callback_data="read_1")],
            [InlineKeyboardButton("Search Sender", callback_data="read_specific")],
            [InlineKeyboardButton("Return", callback_data="menu")]
        ]
        await query.edit_message_text("Inbox Retrieval Menu:", reply_markup=InlineKeyboardMarkup(kb))

    async def read_last_five(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        query = update.callback_query
        await query.answer()
        emails = self.gmail.list_emails(max_results=5)
        if not emails:
            await query.edit_message_text("Inbox empty.", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Back", callback_data="menu")]]))
            return
        await query.edit_message_text("Fetching records...")
        for e in emails:
            d = self.gmail.get_email_content(e['id'])
            kb = [[InlineKeyboardButton("Open", callback_data=f"open_email_{e['id']}")]]
            await context.bot.send_message(chat_id=OWNER_TELEGRAM_ID, text=f"From: {d['sender']}\nSubject: {d['subject']}", reply_markup=InlineKeyboardMarkup(kb))

    async def read_last_one(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        query = update.callback_query
        await query.answer()
        emails = self.gmail.list_emails(max_results=1)
        if emails: await self.display_email_content(update, context, emails[0]['id'])
        else: await query.edit_message_text("Inbox empty.", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Back", callback_data="menu")]]))

    async def ask_specific_sender(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        await update.callback_query.answer()
        await update.callback_query.edit_message_text("Provide the exact email address to search:")
        return ASK_SENDER

    async def fetch_specific_email(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        msg = await update.message.reply_text("Scanning...")
        d = self.gmail.get_last_email_from_sender(update.message.text)
        if not d:
            await msg.edit_text("No records found.", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Back", callback_data="menu")]]))
            return ConversationHandler.END
        await msg.delete()
        await self.display_email_content(update, context, d['id'], is_message=True)
        return ConversationHandler.END

    async def handle_read_email(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        await update.callback_query.answer()
        await self.display_email_content(update, context, update.callback_query.data.split("_")[2])

    async def handle_delete_email(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        query = update.callback_query
        await query.answer()
        m_id = query.data.split("_")[1]
        success = self.gmail.delete_email(m_id)
        txt = "Email Trashed successfully." if success else "Failed to delete."
        await query.edit_message_text(txt, reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Menu", callback_data="menu")]]))

    async def display_email_content(self, update, context, m_id, is_message=False):
        d = self.gmail.get_email_content(m_id)
        sum_txt = self.ai.get_summary(d['body'])
        txt = f"Subject: {d['subject']}\nFrom: {d['sender']}\n\nSummary:\n{sum_txt}"
        kb = [
            [InlineKeyboardButton("Reply", callback_data=f"reply_{d['sender']}"), InlineKeyboardButton("Delete", callback_data=f"delete_{m_id}")],
            [InlineKeyboardButton("Workspace", callback_data="menu")]
        ]
        if is_message: await update.message.reply_text(txt, reply_markup=InlineKeyboardMarkup(kb))
        else: await update.callback_query.edit_message_text(txt, reply_markup=InlineKeyboardMarkup(kb))

    async def start_compose(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        await update.callback_query.answer()
        await update.callback_query.edit_message_text("Enter recipient's email address:")
        return ASK_RECIPIENT

    async def start_reply(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        await update.callback_query.answer()
        to_email = update.callback_query.data.replace("reply_", "")
        context.user_data['draft_to'] = to_email
        await update.callback_query.edit_message_text(f"Replying to: {to_email}\nState intent:")
        return ASK_INTENT

    async def get_recipient(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        context.user_data['draft_to'] = update.message.text
        await update.message.reply_text("State the objective of this email:")
        return ASK_INTENT

    async def generate_initial_draft(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        context.user_data['draft_intent'] = update.message.text
        msg = await update.message.reply_text("Drafting...")
        context.user_data['current_draft'] = self.ai.generate_draft(update.message.text)
        await self.send_draft_review(msg, context)
        return CONFIRM_DRAFT

    async def ask_for_adjustments(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        await update.callback_query.answer()
        await update.callback_query.edit_message_text("Outline adjustments:")
        return ASK_FEEDBACK

    async def regenerate_draft(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        msg = await update.message.reply_text("Applying revisions...")
        context.user_data['current_draft'] = self.ai.modify_draft(context.user_data['current_draft'], update.message.text)
        await self.send_draft_review(msg, context)
        return CONFIRM_DRAFT

    async def send_draft_review(self, message, context):
        txt = f"Recipient: {context.user_data['draft_to']}\n\nDraft Preview:\n\n{context.user_data['current_draft']}"
        kb = [
            [InlineKeyboardButton("Send", callback_data="send_draft"), InlineKeyboardButton("Edit", callback_data="recreate_draft")],
            [InlineKeyboardButton("Discard", callback_data="cancel_draft")]
        ]
        await message.edit_text(txt, reply_markup=InlineKeyboardMarkup(kb))

    async def send_draft(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        await update.callback_query.answer()
        await update.callback_query.edit_message_text("Transmitting...")
        subj = context.user_data.get('draft_intent', 'Update')[:40]
        res = self.gmail.send_email(context.user_data['draft_to'], subj, context.user_data['current_draft'])
        await update.callback_query.edit_message_text(f"{res}", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Workspace", callback_data="menu")]]))
        return ConversationHandler.END

    async def cancel_flow(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        kb = [[InlineKeyboardButton("Workspace", callback_data="menu")]]
        if update.callback_query:
            await update.callback_query.answer()
            await update.callback_query.edit_message_text("Operation canceled.", reply_markup=InlineKeyboardMarkup(kb))
        else: await update.message.reply_text("Operation canceled.", reply_markup=InlineKeyboardMarkup(kb))
        return ConversationHandler.END

    def run(self):
        self.app.run_polling()

if __name__ == "__main__":
    BotHandler().run()
