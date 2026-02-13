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
        # Initialize Modules
        self.auth = AuthManager()
        self.gmail = GmailClient(self.auth)
        self.ai = AI_Engine()
        
        # Initialize Bot
        self.app = ApplicationBuilder().token(BOT_TOKEN).build()
        self._register_handlers()
        
        # Start Auth Server
        self.auth.run_server()
        
        # Background Job: Auto-Check Emails every 60 seconds
        if self.app.job_queue:
            self.app.job_queue.run_repeating(self.auto_check_mail, interval=60, first=10)

    def _register_handlers(self):
        # Commands
        self.app.add_handler(CommandHandler("start", self.start))
        self.app.add_handler(CommandHandler("menu", self.start)) # Alias for start
        
        # Main Menu Buttons
        self.app.add_handler(CallbackQueryHandler(self.cmd_inbox, pattern="^menu_inbox$"))
        self.app.add_handler(CallbackQueryHandler(self.start_draft_mode, pattern="^menu_compose$"))
        
        # Email Actions
        self.app.add_handler(CallbackQueryHandler(self.handle_read, pattern="^read_"))
        self.app.add_handler(CallbackQueryHandler(self.dismiss_notification, pattern="^dismiss$"))
        
        # Text Handler (Router for Natural Language)
        self.app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, self.central_router))
        
        # Draft Conversation Flow
        reply_conv = ConversationHandler(
            entry_points=[CallbackQueryHandler(self.start_reply_flow, pattern="^start_reply$")],
            states={
                WAITING_FOR_INSTRUCTION: [MessageHandler(filters.TEXT & ~filters.COMMAND, self.process_ai_draft)],
                CONFIRM_DRAFT: [
                    CallbackQueryHandler(self.send_final, pattern="^send_final$"),
                    CallbackQueryHandler(self.cancel, pattern="^cancel$")
                ]
            },
            fallbacks=[CallbackQueryHandler(self.cancel, pattern="^cancel$")]
        )
        self.app.add_handler(reply_conv)

    # --- 1. DASHBOARD & START (User Interface) ---
    async def start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if str(update.effective_user.id) != str(OWNER_TELEGRAM_ID): return
        
        # Login Check
        if not self.gmail.get_service():
            link = self.auth.get_login_link()
            kb = [[InlineKeyboardButton("🔗 Connect Gmail Account", url=link)]]
            await update.message.reply_text("⚠️ **Authentication Required**\nPlease log in to access your emails.", reply_markup=InlineKeyboardMarkup(kb))
            return

        # Dashboard Buttons (Restored from Old Code)
        kb = [
            [InlineKeyboardButton("📩 Inbox Overview", callback_data="menu_inbox")],
            [InlineKeyboardButton("✍️ Compose Email", callback_data="menu_compose")]
        ]
        
        welcome_text = (
            "🤖 **Smart Email Assistant Online**\n"
            "How may I assist you today?\n\n"
            "You can use the buttons below or type commands like:\n"
            "• _'Summarize latest emails'_\n"
            "• _'Draft an email to HR about leave'_"
        )
        
        # Handle both Command and Callback (Menu button)
        if update.message:
            await update.message.reply_text(welcome_text, reply_markup=InlineKeyboardMarkup(kb), parse_mode="Markdown")
        else:
            await update.callback_query.message.edit_text(welcome_text, reply_markup=InlineKeyboardMarkup(kb), parse_mode="Markdown")

    # --- 2. INBOX & READING ---
    async def cmd_inbox(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        query = update.callback_query
        if query: await query.answer()
        
        emails = self.gmail.list_emails()
        if not emails:
            msg = "📭 **Your Inbox is empty.**"
            if query: await query.edit_message_text(msg)
            else: await update.message.reply_text(msg)
            return

        # List Emails with Read Buttons
        for email in emails:
            details = self.gmail.get_email_content(email['id'])
            kb = [[InlineKeyboardButton("📖 Read Email", callback_data=f"read_{email['id']}")]]
            text = f"👤 **From:** {details['sender']}\n📌 **Subject:** {details['subject']}"
            
            if query: await context.bot.send_message(chat_id=OWNER_TELEGRAM_ID, text=text, reply_markup=InlineKeyboardMarkup(kb))
            else: await update.message.reply_text(text, reply_markup=InlineKeyboardMarkup(kb))

    async def handle_read(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        query = update.callback_query
        await query.answer()
        
        msg_id = query.data.split("_")[1]
        await query.edit_message_text("⏳ **Fetching & Summarizing...**")
        
        details = self.gmail.get_email_content(msg_id)
        context.user_data['last_details'] = details
        
        # Generate AI Summary
        summary = self.ai.get_summary(details['body'])
        
        display_text = (
            f"📩 **{details['subject']}**\n"
            f"👤 **From:** {details['sender']}\n\n"
            f"✨ **AI Summary:**\n{summary}\n\n"
            f"────────────────"
        )
        
        # Action Buttons (Workflow: "Send Summary + Buttons")
        kb = [
            [InlineKeyboardButton("✍️ Draft Reply", callback_data="start_reply")],
            [InlineKeyboardButton("🔙 Main Menu", callback_data="menu_inbox")]
        ]
        await query.edit_message_text(display_text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(kb))

    # --- 3. AUTO-CHECK (Background Job) ---
    async def auto_check_mail(self, context: ContextTypes.DEFAULT_TYPE):
        """Checks for new emails and sends a notification with buttons."""
        emails = self.gmail.list_emails(max_results=1)
        if emails:
            last_id = context.bot_data.get('last_seen_id')
            current_id = emails[0]['id']
            
            if current_id != last_id:
                context.bot_data['last_seen_id'] = current_id
                details = self.gmail.get_email_content(current_id)
                
                # Notification UI
                text = (
                    f"🚨 **New Email Received**\n"
                    f"👤 **From:** {details['sender']}\n"
                    f"📌 **Subject:** {details['subject']}"
                )
                kb = [
                    [InlineKeyboardButton("📖 Read Now", callback_data=f"read_{current_id}")],
                    [InlineKeyboardButton("❌ Dismiss", callback_data="dismiss")]
                ]
                await context.bot.send_message(
                    chat_id=OWNER_TELEGRAM_ID,
                    text=text,
                    reply_markup=InlineKeyboardMarkup(kb)
                )

    async def dismiss_notification(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        await update.callback_query.delete_message()

    # --- 4. CENTRAL ROUTER (Text Intent) ---
    async def central_router(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handles text inputs using AI Intent Detection."""
        if str(update.effective_user.id) != str(OWNER_TELEGRAM_ID): return

        user_text = update.message.text
        intent = self.ai.detect_intent(user_text)
        
        if intent == "READ":
            await update.message.reply_text(f"🔍 **Searching Inbox...**")
            await self.cmd_inbox(update, context)
            
        elif intent == "DRAFT":
            await update.message.reply_text(f"✍️ **Drafting Mode Detected.**\nPlease use the button below to start.", 
                                            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("✍️ Start Drafting", callback_data="menu_compose")]]))
        else:
            # General Chat / Help
            await update.message.reply_text(
                "🤖 **AI Assistant:**\n"
                "I am not sure I understood. Please use the **Menu** or try commands like:\n"
                "• 'Show unread emails'\n"
                "• 'Compose email'",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Open Menu", callback_data="menu")]])
            )

    # --- 5. DRAFTING & SENDING FLOW ---
    async def start_draft_mode(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        query = update.callback_query
        await query.answer()
        # Clean state for fresh email
        context.user_data['last_details'] = {'sender': '', 'subject': 'New Email', 'body': ''}
        await query.edit_message_text("✍️ **Compose Email**\n\nPlease type your instructions. \n(e.g., _'Email HR asking for a sick leave for tomorrow'_)", parse_mode="Markdown")
        return WAITING_FOR_INSTRUCTION

    async def start_reply_flow(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        query = update.callback_query
        await query.answer()
        await query.edit_message_text("🎤 **Reply Instruction:**\nWhat should I say in the reply?", parse_mode="Markdown")
        return WAITING_FOR_INSTRUCTION

    async def process_ai_draft(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        instruction = update.message.text
        original_body = context.user_data.get('last_details', {}).get('body', '')
        
        msg = await update.message.reply_text("⏳ **Generating Professional Draft...**")
        draft = self.ai.generate_draft(original_body, instruction)
        context.user_data['final_draft'] = draft
        
        kb = [
            [InlineKeyboardButton("🚀 Send Email", callback_data="send_final")],
            [InlineKeyboardButton("❌ Cancel", callback_data="cancel")]
        ]
        await context.bot.edit_message_text(
            chat_id=update.effective_chat.id,
            message_id=msg.message_id,
            text=f"📝 **Draft Preview:**\n────────────────\n{draft}\n────────────────",
            reply_markup=InlineKeyboardMarkup(kb)
        )
        return CONFIRM_DRAFT

    async def send_final(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        query = update.callback_query
        details = context.user_data.get('last_details', {})
        
        # If new email (not reply), ask for recipient (Simplified for now, assumes Reply)
        recipient = details.get('sender', '')
        if not recipient or recipient == '':
             await query.edit_message_text("⚠️ **Error:** Recipient not found. This version supports Replies primarily.")
             return ConversationHandler.END

        subject = f"Re: {details.get('subject', 'No Subject')}"
        body = context.user_data['final_draft']
        
        await query.edit_message_text("🚀 **Sending Email...**")
        result = self.gmail.send_email(recipient, subject, body)
        
        await context.bot.send_message(
            chat_id=OWNER_TELEGRAM_ID,
            text=f"{result}\n\n Returning to menu...",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Main Menu", callback_data="menu_inbox")]])
        )
        return ConversationHandler.END

    async def cancel(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        await update.callback_query.edit_message_text("❌ **Operation Cancelled.**", 
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Main Menu", callback_data="menu")]]))
        return ConversationHandler.END

    def run(self):
        print("🚀 Bot is Polling...")
        self.app.run_polling()

if __name__ == "__main__":
    bot = BotHandler()
    bot.run()