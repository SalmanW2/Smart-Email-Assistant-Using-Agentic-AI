import sys
import asyncio
import logging
import threading
import os
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.request import HTTPXRequest
from telegram.ext import (
    ApplicationBuilder, CommandHandler, CallbackQueryHandler, 
    ContextTypes, ConversationHandler, MessageHandler, filters
)
from config_env import BOT_TOKEN, OWNER_TELEGRAM_ID
from gmail_service import get_last_email, create_and_send_email, get_latest_message_id, get_email_details, get_credentials
from auth_server import run_flask_server, get_login_link

# --- LOGGING CONFIGURATION ---
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', 
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# --- CONVERSATION STATES ---
RECIPIENT, SUBJECT, BODY = range(3)
ASK_SENDER_EMAIL = range(3, 4)

# --- GLOBAL VARIABLES ---
# To track the last email ID for auto-notifications
last_checked_email_id = None 

# ==============================================================================
#   HELPER FUNCTIONS (UI & AUTH CHECK)
# ==============================================================================

def is_user_authenticated():
    """Checks if valid credentials exist locally or in secrets."""
    creds = get_credentials()
    return creds is not None and creds.valid

def get_dashboard_keyboard():
    """Returns the main menu keyboard."""
    keyboard = [
        [InlineKeyboardButton("📩 Inbox Overview", callback_data="menu_read")],
        [InlineKeyboardButton("✍️ Compose Email", callback_data="menu_send")]
    ]
    return InlineKeyboardMarkup(keyboard)

def get_login_keyboard(auth_link):
    """Returns the login button."""
    keyboard = [[InlineKeyboardButton("🔗 Connect Gmail Account", url=auth_link)]]
    return InlineKeyboardMarkup(keyboard)

# ==============================================================================
#   BACKGROUND JOBS (AUTO-CHECKER)
# ==============================================================================

async def check_new_emails_job(context: ContextTypes.DEFAULT_TYPE):
    """
    Background job to check for new emails every minute.
    Only runs if the user is authenticated.
    """
    global last_checked_email_id
    
    # 1. Check Authentication first to avoid errors
    if not is_user_authenticated():
        return

    # 2. Fetch Latest Email ID
    latest_id = get_latest_message_id()
    
    # Initialize memory on first run
    if last_checked_email_id is None:
        last_checked_email_id = latest_id
        return

    # 3. Compare IDs: If different, a new email has arrived
    if latest_id and latest_id != last_checked_email_id:
        last_checked_email_id = latest_id 
        
        details = get_email_details(latest_id)
        if details:
            # Save sender email for the "Quick Reply" feature
            context.bot_data['last_reply_email'] = details['sender_email']
            
            msg_text = (
                f"🔔 **New Email Received**\n\n"
                f"👤 **From:** `{details['sender_view']}`\n"
                f"📌 **Subject:** `{details['subject']}`\n"
                f"📝 **Preview:** {details['snippet']}..."
            )
            
            keyboard = [[InlineKeyboardButton("↩️ Quick Reply", callback_data="reply_last_email")]]
            
            await context.bot.send_message(
                chat_id=OWNER_TELEGRAM_ID, 
                text=msg_text, 
                parse_mode="Markdown",
                reply_markup=InlineKeyboardMarkup(keyboard)
            )

# ==============================================================================
#   COMMAND HANDLERS
# ==============================================================================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Entry point of the bot. 
    Checks authentication status and serves the appropriate menu.
    """
    if not update.message: return
    user_id = update.message.from_user.id

    # Security Check
    if str(user_id) != str(OWNER_TELEGRAM_ID):
        await update.message.reply_text("⛔ **Access Denied:** You are not authorized to use this assistant.", parse_mode="Markdown")
        return

    # Check if user is already logged in
    if is_user_authenticated():
        await update.message.reply_text(
            "👋 **Welcome Back!**\n\nYour Email Assistant is online and ready. How may I assist you today?",
            reply_markup=get_dashboard_keyboard(),
            parse_mode="Markdown"
        )
    else:
        # Generate Login Link if not authenticated
        link = get_login_link()
        if link:
            await update.message.reply_text(
                "👋 **Welcome to Smart Email Assistant**\n\n"
                "To get started, please authorize the bot to access your Gmail account securely.",
                reply_markup=get_login_keyboard(link),
                parse_mode="Markdown"
            )
        else:
            await update.message.reply_text("❌ **System Error:** Credentials file is missing on the server.")

async def login_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Manual login command handler."""
    if str(update.message.from_user.id) != str(OWNER_TELEGRAM_ID): return
    
    link = get_login_link()
    if link:
        await update.message.reply_text(
            "🔑 **Authentication Required**\nClick below to sign in via Google:", 
            reply_markup=get_login_keyboard(link),
            parse_mode="Markdown"
        )
    else:
        await update.message.reply_text("❌ **Error:** Unable to generate login link. Check server logs.")

# ==============================================================================
#   READ EMAILS FLOW
# ==============================================================================

async def read_menu_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    keyboard = [
        [InlineKeyboardButton("🕒 Latest Email", callback_data="read_latest")],
        [InlineKeyboardButton("🔍 Search Specific Sender", callback_data="read_specific")]
    ]
    await query.edit_message_text(
        "📂 **Inbox Options**\nPlease select an option below:", 
        reply_markup=InlineKeyboardMarkup(keyboard), 
        parse_mode="Markdown"
    )

async def fetch_latest_email(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    # Pre-check Auth
    if not is_user_authenticated():
        link = get_login_link()
        await query.edit_message_text("⚠️ **Session Expired.** Please login again.", reply_markup=get_login_keyboard(link))
        return

    await query.edit_message_text("🔄 **Syncing with Gmail...**")
    
    content = get_last_email()
    
    if content == "AUTH_ERROR":
        link = get_login_link()
        await query.edit_message_text("⚠️ **Authentication Failed.** Please reconnect.", reply_markup=get_login_keyboard(link))
    elif content:
        # Show email and provide Back to Menu option
        back_kb = [[InlineKeyboardButton("🔙 Main Menu", callback_data="back_to_main")]]
        await query.edit_message_text(content, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(back_kb))
    else:
        await query.edit_message_text("📭 **Inbox is Empty.** No new emails found.")

# --- SPECIFIC SENDER SEARCH ---
async def ask_sender_email(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.edit_message_text("🔍 **Search Filter**\nPlease type the **Sender's Email Address**:")
    return ASK_SENDER_EMAIL

async def fetch_specific_email(update: Update, context: ContextTypes.DEFAULT_TYPE):
    sender = update.message.text.strip()
    await update.message.reply_text(f"🔎 Searching emails from: `{sender}`...", parse_mode="Markdown")
    
    content = get_last_email(query=f"from:{sender}")
    
    if content and content != "AUTH_ERROR":
        await update.message.reply_text(content, parse_mode="Markdown")
    else:
        await update.message.reply_text(f"❌ No emails found from `{sender}` or authentication failed.")
    
    return ConversationHandler.END

# ==============================================================================
#   SEND EMAILS FLOW (Compose & Reply)
# ==============================================================================

async def reply_button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handles the 'Reply Quickly' button from notifications."""
    query = update.callback_query
    await query.answer()
    
    target_email = context.bot_data.get('last_reply_email')
    
    if not target_email:
        await query.edit_message_text("⚠️ **Error:** Could not determine the recipient address.")
        return ConversationHandler.END
    
    context.user_data['to'] = target_email
    context.user_data['sub'] = "Re: Previous Email" 
    
    await query.edit_message_text(
        f"↩️ **Replying to:** `{target_email}`\n\n📝 **Please type your message body:**", 
        parse_mode="Markdown"
    )
    return BODY

async def start_sending(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Starts the normal email composition flow."""
    query = update.callback_query
    await query.answer()
    
    if not is_user_authenticated():
        link = get_login_link()
        await query.edit_message_text("⚠️ Please login first.", reply_markup=get_login_keyboard(link))
        return ConversationHandler.END

    await query.edit_message_text("✍️ **Compose Email**\nPlease enter the **Recipient's Email Address**:\n(Or type /cancel to stop)", parse_mode="Markdown")
    return RECIPIENT

async def get_recipient(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['to'] = update.message.text.strip()
    await update.message.reply_text("📝 **Subject Line:**")
    return SUBJECT

async def get_subject(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['sub'] = update.message.text.strip()
    await update.message.reply_text("💬 **Message Body:**")
    return BODY

async def send_email_final(update: Update, context: ContextTypes.DEFAULT_TYPE):
    to = context.user_data['to']
    sub = context.user_data.get('sub', '(No Subject)')
    body = update.message.text
    
    await update.message.reply_text(f"🚀 **Dispatching email to:** `{to}`...", parse_mode="Markdown")
    
    result = create_and_send_email(to, sub, body)
    
    # Return to dashboard after sending
    await update.message.reply_text(result, reply_markup=get_dashboard_keyboard())
    return ConversationHandler.END

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("❌ **Operation Cancelled.**", reply_markup=get_dashboard_keyboard())
    return ConversationHandler.END

# --- UTILITY: Back to Main Menu ---
async def back_to_main_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.edit_message_text(
        "👋 **Welcome Back!**\nHow may I assist you?",
        reply_markup=get_dashboard_keyboard(),
        parse_mode="Markdown"
    )

# ==============================================================================
#   MAIN EXECUTION
# ==============================================================================

if __name__ == "__main__":
    # Fix for Windows Event Loop
    if sys.platform.startswith("win"):
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    
    # 1. Start Flask Auth Server (Background Thread)
    threading.Thread(target=run_flask_server, daemon=True).start()
    
    print("✅ System: Bot is initializing...")
    
    # 2. Configure Bot with Extended Timeout
    t_request = HTTPXRequest(connect_timeout=60.0, read_timeout=60.0)
    app = ApplicationBuilder().token(BOT_TOKEN).request(t_request).build()

    # 3. Setup Background Job (Email Checker)
    if app.job_queue:
        app.job_queue.run_repeating(check_new_emails_job, interval=60, first=10)

    # 4. Register Handlers
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("login", login_command))
    
    # Send Email Conversation
    send_handler = ConversationHandler(
        entry_points=[
            CallbackQueryHandler(start_sending, pattern="^menu_send$"),
            CallbackQueryHandler(reply_button_handler, pattern="^reply_last_email$")
        ],
        states={
            RECIPIENT: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_recipient)],
            SUBJECT: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_subject)],
            BODY: [MessageHandler(filters.TEXT & ~filters.COMMAND, send_email_final)],
        },
        fallbacks=[CommandHandler("cancel", cancel)]
    )
    app.add_handler(send_handler)

    # Read Email Conversation
    app.add_handler(ConversationHandler(
        entry_points=[CallbackQueryHandler(ask_sender_email, pattern="^read_specific$")],
        states={ASK_SENDER_EMAIL: [MessageHandler(filters.TEXT & ~filters.COMMAND, fetch_specific_email)]},
        fallbacks=[CommandHandler("cancel", cancel)]
    ))

    # General Callbacks
    app.add_handler(CallbackQueryHandler(read_menu_handler, pattern="^menu_read$"))
    app.add_handler(CallbackQueryHandler(fetch_latest_email, pattern="^read_latest$"))
    app.add_handler(CallbackQueryHandler(back_to_main_handler, pattern="^back_to_main$"))

    print("✅ System: Bot is Live and Listening.")
    app.run_polling()