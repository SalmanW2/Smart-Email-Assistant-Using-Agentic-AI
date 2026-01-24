import sys
import asyncio
import logging
import threading
import os
import functools  # <--- Added for Speed Optimization
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.request import HTTPXRequest
from telegram.ext import (
    ApplicationBuilder, CommandHandler, CallbackQueryHandler, 
    ContextTypes, ConversationHandler, MessageHandler, filters
)
from config_env import BOT_TOKEN, OWNER_TELEGRAM_ID

# Importing our new OOP Modules
from gmail_client import GmailClient
from auth_manager import AuthManager, run_flask_server
from ai_engine import AIEngine

# --- LOGGING ---
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', 
    level=logging.INFO
)
logger = logging.getLogger("BotHandler")

# --- STATES ---
RECIPIENT, SUBJECT, BODY = range(3)
ASK_SENDER_EMAIL = range(3, 4)
WAITING_FOR_INSTRUCTION = range(4, 5)

class BotHandler:
    """
    Main Controller Class.
    Manages Telegram Updates and connects Email, AI, and Auth modules.
    Ref: Section 5.4 of Project Report.
    """
    def __init__(self):
        # Initialize Helper Classes
        self.gmail = GmailClient()
        self.ai = AIEngine()
        
        # State Memory
        self.last_checked_email_id = None
        
        # Initialize Bot App
        self.app = ApplicationBuilder().token(BOT_TOKEN).request(HTTPXRequest(connect_timeout=60, read_timeout=60)).build()

    # --- HELPER METHODS ---
    def is_user_authenticated(self):
        creds = self.gmail.get_credentials()
        return creds is not None and creds.valid

    def get_dashboard_keyboard(self):
        keyboard = [
            [InlineKeyboardButton("📩 Inbox Overview", callback_data="menu_read")],
            [InlineKeyboardButton("✍️ Compose Email", callback_data="menu_send")]
        ]
        return InlineKeyboardMarkup(keyboard)

    def get_login_keyboard(self, auth_link):
        keyboard = [[InlineKeyboardButton("🔗 Connect Gmail Account", url=auth_link)]]
        return InlineKeyboardMarkup(keyboard)

    # --- AUTO-CHECKER JOB (OPTIMIZED ⚡) ---
    async def check_new_emails_job(self, context: ContextTypes.DEFAULT_TYPE):
        # 1. AUTH CHECK
        if not self.is_user_authenticated():
            if not context.bot_data.get('auth_warning_sent'):
                link = AuthManager.get_login_link()
                if link:
                    try:
                        await context.bot.send_message(
                            chat_id=OWNER_TELEGRAM_ID,
                            text="⚠️ **Session Expired!**\nPlease login again.",
                            reply_markup=self.get_login_keyboard(link),
                            parse_mode="Markdown"
                        )
                        context.bot_data['auth_warning_sent'] = True
                    except Exception as e:
                        logger.error(f"Auth warning error: {e}")
            return
        else:
            context.bot_data['auth_warning_sent'] = False

        # 2. NEW EMAIL CHECK (NON-BLOCKING)
        try:
            # Get the running event loop
            loop = asyncio.get_running_loop()
            
            # Step A: Get ID (Run in background thread to avoid blocking Telegram)
            latest_id = await loop.run_in_executor(None, self.gmail.get_latest_message_id)
            
            if self.last_checked_email_id is None:
                self.last_checked_email_id = latest_id
                return

            if latest_id and latest_id != self.last_checked_email_id:
                self.last_checked_email_id = latest_id
                
                # Step B: Fetch Full Details (Run in background)
                details = await loop.run_in_executor(None, self.gmail.get_latest_email_details)
                if not details: return

                context.bot_data['last_email_id'] = latest_id
                context.bot_data['last_email_body'] = details['body']
                context.bot_data['last_sender'] = details['sender_email']

                word_count = len(details['body'].split())
                msg_text = ""
                keyboard = []

                # Threshold: 50 Words
                if word_count > 50:
                    # Step C: AI Summary (Run in background)
                    summary = await loop.run_in_executor(
                        None, 
                        functools.partial(self.ai.summarize_email, details['body'])
                    )
                    
                    msg_text = (
                        f"🚨 **NEW EMAIL (AI Summary)**\n\n"
                        f"👤 **From:** `{details['sender_view']}`\n"
                        f"📌 **Subject:** `{details['subject']}`\n\n"
                        f"✨ **Summary:**\n{summary}"
                    )
                    keyboard.append([InlineKeyboardButton("📄 Read Full Email", callback_data="read_full_auto")])
                else:
                    msg_text = (
                        f"🚨 **NEW EMAIL**\n\n"
                        f"👤 **From:** `{details['sender_view']}`\n"
                        f"📌 **Subject:** `{details['subject']}`\n\n"
                        f"📝 **Body:**\n{details['body']}"
                    )

                keyboard.append([InlineKeyboardButton("✍️ Draft Reply (AI)", callback_data="start_ai_reply")])
                keyboard.append([InlineKeyboardButton("🚫 Ignore", callback_data="ignore_notification")])

                await context.bot.send_message(
                    chat_id=OWNER_TELEGRAM_ID, 
                    text=msg_text, 
                    parse_mode="Markdown",
                    reply_markup=InlineKeyboardMarkup(keyboard)
                )
                
        except Exception as e:
            logger.error(f"Auto-Check Error: {e}")

    # --- TELEGRAM HANDLERS ---
    async def start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if str(update.message.from_user.id) != str(OWNER_TELEGRAM_ID): return
        if self.is_user_authenticated():
            await update.message.reply_text("👋 **Boss! System Online.** 🕵️", reply_markup=self.get_dashboard_keyboard(), parse_mode="Markdown")
        else:
            link = AuthManager.get_login_link()
            if link: await update.message.reply_text("👋 **Welcome!** Please login.", reply_markup=self.get_login_keyboard(link))

    async def login_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if str(update.message.from_user.id) != str(OWNER_TELEGRAM_ID): return
        link = AuthManager.get_login_link()
        if link: await update.message.reply_text("👇 **Login:**", reply_markup=self.get_login_keyboard(link))

    async def ignore_handler(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        query = update.callback_query
        await query.answer("Dismissed.")
        await query.delete_message()

    async def read_full_auto_handler(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        query = update.callback_query
        await query.answer()
        email_id = context.bot_data.get('last_email_id')
        # Re-fetch using class method
        details = self.gmail.get_latest_email_details()
        
        if details:
            text = f"📄 **FULL EMAIL**\n\n👤 **From:** `{details['sender_view']}`\n📝 **Body:**\n{details['body']}"
            keyboard = [[InlineKeyboardButton("✍️ Draft Reply (AI)", callback_data="start_ai_reply")], [InlineKeyboardButton("🚫 Ignore", callback_data="ignore_notification")]]
            await query.edit_message_text(text=text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(keyboard))
        else:
            await query.edit_message_text("❌ Error: Email not found.")

    # --- AI REPLY FLOW ---
    async def start_ai_reply(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        query = update.callback_query
        await query.answer()
        sender = context.bot_data.get('last_sender')
        if not sender:
            await query.edit_message_text("⚠️ Context lost.")
            return ConversationHandler.END
        context.user_data['reply_to'] = sender
        await query.edit_message_text(f"🤖 **AI Agent Active**\nReplying to: `{sender}`\n\n🗣️ **What should I say?**", parse_mode="Markdown")
        return WAITING_FOR_INSTRUCTION

    async def generate_draft(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        user_instruction = update.message.text
        original_email = context.bot_data.get('last_email_body', '')
        await update.message.reply_text("⏳ **Drafting...**")
        
        # Use AI Class
        draft = self.ai.generate_draft_reply(original_email, user_instruction)
        
        context.user_data['draft_body'] = draft
        context.user_data['draft_sub'] = "Re: (AI Reply)"
        msg = f"🧐 **REVIEW DRAFT**\n-------------------\n{draft}\n-------------------\nChoose action:"
        keyboard = [[InlineKeyboardButton("🚀 Send Now", callback_data="send_draft_now")], [InlineKeyboardButton("✏️ Edit Manual", callback_data="edit_draft_manual")], [InlineKeyboardButton("🔄 Try Again", callback_data="retry_ai_draft")]]
        await update.message.reply_text(msg, reply_markup=InlineKeyboardMarkup(keyboard))
        return WAITING_FOR_INSTRUCTION

    async def handle_draft_actions(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        query = update.callback_query
        await query.answer()
        action = query.data
        if action == "send_draft_now":
            to = context.user_data.get('reply_to')
            sub = context.user_data.get('draft_sub')
            body = context.user_data.get('draft_body')
            await query.edit_message_text(f"🚀 **Sending...**")
            # Use Gmail Class
            result = self.gmail.send_email(to, sub, body)
            await query.edit_message_text(f"{result}\n\n✅ **Done!**")
            return ConversationHandler.END
        elif action == "edit_draft_manual":
            await query.edit_message_text("✏️ **Type full email body:**")
            return BODY 
        elif action == "retry_ai_draft":
            await query.edit_message_text("🗣️ **New instructions:**")
            return WAITING_FOR_INSTRUCTION

    # --- STANDARD & MANUAL FLOWS ---
    async def read_menu_handler(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        query = update.callback_query
        await query.answer()
        keyboard = [[InlineKeyboardButton("🕒 Last Email", callback_data="read_latest")]]
        await query.edit_message_text("📂 **Options:**", reply_markup=InlineKeyboardMarkup(keyboard))

    async def fetch_latest_email(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        query = update.callback_query
        await query.answer()
        if not self.is_user_authenticated():
            await query.edit_message_text("⚠️ Session Expired.")
            return
        
        details = self.gmail.get_latest_email_details()
        if details:
            context.bot_data['last_email_id'] = details['id']
            context.bot_data['last_email_body'] = details['body']
            context.bot_data['last_sender'] = details['sender_email']
            text_display = details['body'][:500] + "..." if len(details['body']) > 500 else details['body']
            keyboard = [[InlineKeyboardButton("✍️ Draft Reply (AI)", callback_data="start_ai_reply")], [InlineKeyboardButton("🔙 Menu", callback_data="menu_read")]]
            display_text = f"📩 **Latest Email**\n👤 **From:** `{details['sender_view']}`\n📌 **Subject:** `{details['subject']}`\n\n{text_display}"
            await query.edit_message_text(display_text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(keyboard))
        else:
            await query.edit_message_text("📭 Empty.")

    async def start_sending_manual(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        query = update.callback_query
        await query.answer()
        if not self.is_user_authenticated():
            await query.edit_message_text("⚠️ Please Login.")
            return ConversationHandler.END
        await query.edit_message_text("✍️ **Recipient:**")
        return RECIPIENT

    async def get_recipient(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        context.user_data['to'] = update.message.text
        await update.message.reply_text("📝 **Subject:**")
        return SUBJECT

    async def get_subject(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        context.user_data['sub'] = update.message.text
        await update.message.reply_text("💬 **Body:**")
        return BODY

    async def send_email_final(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        to = context.user_data.get('to') or context.user_data.get('reply_to')
        sub = context.user_data.get('sub') or context.user_data.get('draft_sub', 'No Subject')
        body = update.message.text
        await update.message.reply_text("🚀 **Sending...**")
        result = self.gmail.send_email(to, sub, body)
        await update.message.reply_text(result, reply_markup=self.get_dashboard_keyboard())
        return ConversationHandler.END

    async def cancel(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        await update.message.reply_text("❌ Cancelled.", reply_markup=self.get_dashboard_keyboard())
        return ConversationHandler.END

    def run(self):
        """Setup and Start the Bot"""
        if self.app.job_queue:
            self.app.job_queue.run_repeating(self.check_new_emails_job, interval=60, first=10)

        # Handlers
        self.app.add_handler(CommandHandler("start", self.start))
        self.app.add_handler(CommandHandler("login", self.login_command))

        ai_handler = ConversationHandler(
            entry_points=[CallbackQueryHandler(self.start_ai_reply, pattern="^start_ai_reply$")],
            states={
                WAITING_FOR_INSTRUCTION: [
                    MessageHandler(filters.TEXT & ~filters.COMMAND, self.generate_draft),
                    CallbackQueryHandler(self.handle_draft_actions, pattern="^(send_draft_now|edit_draft_manual|retry_ai_draft)$")
                ],
                BODY: [MessageHandler(filters.TEXT & ~filters.COMMAND, self.send_email_final)]
            },
            fallbacks=[CommandHandler("cancel", self.cancel)]
        )
        self.app.add_handler(ai_handler)

        send_handler = ConversationHandler(
            entry_points=[CallbackQueryHandler(self.start_sending_manual, pattern="^menu_send$")],
            states={
                RECIPIENT: [MessageHandler(filters.TEXT & ~filters.COMMAND, self.get_recipient)],
                SUBJECT: [MessageHandler(filters.TEXT & ~filters.COMMAND, self.get_subject)],
                BODY: [MessageHandler(filters.TEXT & ~filters.COMMAND, self.send_email_final)],
            },
            fallbacks=[CommandHandler("cancel", self.cancel)]
        )
        self.app.add_handler(send_handler)

        self.app.add_handler(CallbackQueryHandler(self.read_menu_handler, pattern="^menu_read$"))
        self.app.add_handler(CallbackQueryHandler(self.fetch_latest_email, pattern="^read_latest$"))
        self.app.add_handler(CallbackQueryHandler(self.read_full_auto_handler, pattern="^read_full_auto$"))
        self.app.add_handler(CallbackQueryHandler(self.ignore_handler, pattern="^ignore_notification$"))

        logger.info("✅ BotHandler is Running Polling...")
        self.app.run_polling()

# --- MAIN EXECUTION ---
if __name__ == "__main__":
    if sys.platform.startswith("win"):
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    
    # Start Auth Server (Keep-Alive)
    threading.Thread(target=run_flask_server, daemon=True).start()
    
    # Start Bot
    bot = BotHandler()
    bot.run()