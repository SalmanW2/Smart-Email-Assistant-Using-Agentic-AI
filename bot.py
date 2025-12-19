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
from config_env import BOT_TOKEN, OWNER_TELEGRAM_ID # .env se ID layega
from gmail_service import get_last_email, create_and_send_email
from auth_server import run_flask_server, get_redirect_uri, get_credentials_path # Import from File 1
from google_auth_oauthlib.flow import Flow

# --- LOGGING ---
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)

# --- STATES ---
# Sending States
RECIPIENT, SUBJECT, BODY = range(3)
# Reading States
ASK_SENDER_EMAIL = range(3, 4)

# --- AUTH HELPER ---
def get_login_link():
    """Generates the Google Login Link"""
    creds_file = get_credentials_path()
    if not creds_file: return None
    
    flow = Flow.from_client_secrets_file(
        creds_file,
        scopes=['https://www.googleapis.com/auth/gmail.modify'],
        redirect_uri=get_redirect_uri()
    )
    auth_url, _ = flow.authorization_url(prompt='consent')
    return auth_url

# --- MAIN MENU ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    
    # 🔒 SECURITY CHECK (Sirf Owner use kar sake)
    if str(user_id) != str(OWNER_TELEGRAM_ID):
        await update.message.reply_text("🚫 **Access Denied!** You are not the owner.")
        return

    keyboard = [
        [InlineKeyboardButton("📤 Send Email", callback_data="menu_send")],
        [InlineKeyboardButton("📩 Read Email", callback_data="menu_read")]
    ]
    await update.message.reply_text(
        "👋 **Welcome Boss!**\nHow can I help you with your emails today?",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode="Markdown"
    )

async def login_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if str(update.message.from_user.id) != str(OWNER_TELEGRAM_ID): return
    
    link = get_login_link()
    if link:
        keyboard = [[InlineKeyboardButton("🔗 Login via Google", url=link)]]
        await update.message.reply_text("👇 **Click below to login:**", reply_markup=InlineKeyboardMarkup(keyboard))
    else:
        await update.message.reply_text("❌ Error: credentials.json not found.")

# --- READ FLOW ---
async def read_menu_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    keyboard = [
        [InlineKeyboardButton("🕒 Read Last Email (Inbox)", callback_data="read_latest")],
        [InlineKeyboardButton("🔍 Specific Sender", callback_data="read_specific")]
    ]
    await query.edit_message_text("🧐 **What would you like to read?**", reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")

async def fetch_latest_email(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.edit_message_text("⏳ **Checking Inbox...**")
    
    email_content = get_last_email() # Default logic
    
    if email_content == "AUTH_ERROR":
         await query.edit_message_text("⚠️ **Login Required.** Use /login")
    elif email_content:
        await query.edit_message_text(f"📩 **Latest Email:**\n\n{email_content}", parse_mode="Markdown")
    else:
        await query.edit_message_text("📭 **Inbox is Empty.**")

# -- Specific Sender Logic --
async def ask_sender_email(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.edit_message_text("👤 **Please type the Sender's Email Address:**\n(e.g., hr@company.com)")
    return ASK_SENDER_EMAIL

async def fetch_specific_email(update: Update, context: ContextTypes.DEFAULT_TYPE):
    sender_email = update.message.text.strip()
    await update.message.reply_text(f"🔍 **Searching emails from:** `{sender_email}`...", parse_mode="Markdown")
    
    # Updated Service Call
    email_content = get_last_email(query=f"from:{sender_email}")
    
    if email_content == "AUTH_ERROR":
        await update.message.reply_text("⚠️ **Session Expired.** Please /login again.")
    elif email_content:
        await update.message.reply_text(f"📩 **Latest Email from {sender_email}:**\n\n{email_content}", parse_mode="Markdown")
    else:
        await update.message.reply_text(f"❌ **No emails found** from `{sender_email}`.")
    
    return ConversationHandler.END

# --- SEND FLOW ---
async def start_sending(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.edit_message_text("✍️ **Recipient's Email Address:**\n(Type /cancel to stop)")
    return RECIPIENT

async def get_recipient(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['to'] = update.message.text
    await update.message.reply_text("📝 **Subject:**")
    return SUBJECT

async def get_subject(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['sub'] = update.message.text
    await update.message.reply_text("💬 **Message Body:**")
    return BODY

async def send_email_final(update: Update, context: ContextTypes.DEFAULT_TYPE):
    to = context.user_data['to']
    sub = context.user_data['sub']
    body = update.message.text
    
    await update.message.reply_text("🚀 **Sending...**")
    result = create_and_send_email(to, sub, body)
    await update.message.reply_text(result)
    return ConversationHandler.END

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("❌ Operation Cancelled.")
    return ConversationHandler.END

# --- RUNNER ---
if __name__ == "__main__":
    if sys.platform.startswith("win"):
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    
    # 1. Start Flask Auth Server in Background
    threading.Thread(target=run_flask_server, daemon=True).start()
    
    # 2. Start Telegram Bot
    print("✅ Bot Started...")
    app = ApplicationBuilder().token(BOT_TOKEN).request(HTTPXRequest(connect_timeout=60, read_timeout=60)).build()

    # Handlers
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("login", login_command))
    
    # Conversation: Send Email
    app.add_handler(ConversationHandler(
        entry_points=[CallbackQueryHandler(start_sending, pattern="^menu_send$")],
        states={
            RECIPIENT: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_recipient)],
            SUBJECT: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_subject)],
            BODY: [MessageHandler(filters.TEXT & ~filters.COMMAND, send_email_final)],
        },
        fallbacks=[CommandHandler("cancel", cancel)]
    ))

    # Conversation: Read Specific Email
    app.add_handler(ConversationHandler(
        entry_points=[CallbackQueryHandler(ask_sender_email, pattern="^read_specific$")],
        states={
            ASK_SENDER_EMAIL: [MessageHandler(filters.TEXT & ~filters.COMMAND, fetch_specific_email)]
        },
        fallbacks=[CommandHandler("cancel", cancel)]
    ))

    # Simple Handlers
    app.add_handler(CallbackQueryHandler(read_menu_handler, pattern="^menu_read$"))
    app.add_handler(CallbackQueryHandler(fetch_latest_email, pattern="^read_latest$"))

    app.run_polling()