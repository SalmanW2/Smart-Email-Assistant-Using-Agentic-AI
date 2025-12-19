import sys
import asyncio
import logging
import threading
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.request import HTTPXRequest
from telegram.ext import (
    ApplicationBuilder, CommandHandler, CallbackQueryHandler, 
    ContextTypes, ConversationHandler, MessageHandler, filters
)
from config_env import BOT_TOKEN, OWNER_TELEGRAM_ID
from gmail_service import get_last_email, create_and_send_email, get_latest_message_id, get_email_details
from auth_server import run_flask_server, get_login_link

# --- LOGGING ---
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)

# --- STATES ---
RECIPIENT, SUBJECT, BODY = range(3)
ASK_SENDER_EMAIL = range(3, 4)

# --- GLOBAL MEMORY ---
# (Bot ko yaad dilane ke liye ke last email konsi thi)
last_checked_email_id = None 

# --- AUTO CHECKER JOB (The Heartbeat) 💓 ---
async def check_new_emails_job(context: ContextTypes.DEFAULT_TYPE):
    global last_checked_email_id
    
    # 1. Latest ID fetch karo
    latest_id = get_latest_message_id()
    
    # Agar pehli baar chal raha hai to current ID set kar lo (Notification mat bhejo)
    if last_checked_email_id is None:
        last_checked_email_id = latest_id
        return

    # 2. Compare: Agar ID change hui hai to matlab NEW EMAIL!
    if latest_id and latest_id != last_checked_email_id:
        last_checked_email_id = latest_id # Memory update karo
        
        # Details mangwao
        details = get_email_details(latest_id)
        if details:
            # Sender ko save karo taake Reply kar sakein
            context.bot_data['last_reply_email'] = details['sender_email']
            
            msg_text = (
                f"🚨 **NEW EMAIL RECEIVED!**\n\n"
                f"👤 **From:** `{details['sender_view']}`\n"
                f"📌 **Subject:** `{details['subject']}`\n"
                f"📝 **Snippet:** {details['snippet']}..."
            )
            
            # REPLY BUTTON
            keyboard = [[InlineKeyboardButton("↩️ Reply Quickly", callback_data="reply_last_email")]]
            
            await context.bot.send_message(
                chat_id=OWNER_TELEGRAM_ID, 
                text=msg_text, 
                parse_mode="Markdown",
                reply_markup=InlineKeyboardMarkup(keyboard)
            )

# --- STANDARD FUNCTIONS ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if str(update.message.from_user.id) != str(OWNER_TELEGRAM_ID): return

    keyboard = [
        [InlineKeyboardButton("📤 Send Email", callback_data="menu_send")],
        [InlineKeyboardButton("📩 Read Email", callback_data="menu_read")]
    ]
    await update.message.reply_text("👋 **Welcome Boss!**\nMonitoring emails automatically... 🕵️", reply_markup=InlineKeyboardMarkup(keyboard))

async def login_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if str(update.message.from_user.id) != str(OWNER_TELEGRAM_ID): return
    link = get_login_link()
    if link:
        keyboard = [[InlineKeyboardButton("🔗 Login via Google", url=link)]]
        await update.message.reply_text("👇 **Click to Login:**", reply_markup=InlineKeyboardMarkup(keyboard))
    else:
        await update.message.reply_text("❌ Error: Credentials missing.")

# --- REPLY LOGIC (Direct Button) ---
async def reply_button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    # Auto-saved sender email uthao
    target_email = context.bot_data.get('last_reply_email')
    
    if not target_email:
        await query.edit_message_text("⚠️ **Error:** Cannot find email address to reply.")
        return ConversationHandler.END
    
    # Context set karo
    context.user_data['to'] = target_email
    context.user_data['sub'] = "Re: (No Subject)" # Default subject
    
    await query.edit_message_text(f"↩️ **Replying to:** `{target_email}`\n\n📝 **Type your message body:**", parse_mode="Markdown")
    return BODY  # Seedha Body wale step par jump kiya

# --- SEND FLOW (Normal) ---
async def start_sending(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.edit_message_text("✍️ **Recipient's Email Address:**\n(/cancel to stop)")
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
    sub = context.user_data.get('sub', 'No Subject')
    body = update.message.text
    
    await update.message.reply_text(f"🚀 **Sending to {to}...**")
    result = create_and_send_email(to, sub, body)
    await update.message.reply_text(result)
    return ConversationHandler.END

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("❌ Cancelled.")
    return ConversationHandler.END

# --- READ FLOW ---
async def read_menu_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    keyboard = [
        [InlineKeyboardButton("🕒 Last Email", callback_data="read_latest")],
        [InlineKeyboardButton("🔍 Specific Sender", callback_data="read_specific")]
    ]
    await query.edit_message_text("🧐 **Choose:**", reply_markup=InlineKeyboardMarkup(keyboard))

async def fetch_latest_email(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.edit_message_text("⏳ **Fetching...**")
    content = get_last_email()
    if content == "AUTH_ERROR":
        await query.edit_message_text("⚠️ Login Required (/login)")
    elif content:
        await query.edit_message_text(content, parse_mode="Markdown")
    else:
        await query.edit_message_text("📭 Empty.")

async def ask_sender_email(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.edit_message_text("👤 **Type Sender's Email:**")
    return ASK_SENDER_EMAIL

async def fetch_specific_email(update: Update, context: ContextTypes.DEFAULT_TYPE):
    sender = update.message.text.strip()
    await update.message.reply_text(f"🔍 Searching: {sender}...")
    content = get_last_email(query=f"from:{sender}")
    if content and content != "AUTH_ERROR":
        await update.message.reply_text(content, parse_mode="Markdown")
    else:
        await update.message.reply_text("❌ Not found or Auth Error.")
    return ConversationHandler.END

# --- MAIN ---
if __name__ == "__main__":
    if sys.platform.startswith("win"):
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    
    # 1. Start Auth Server
    threading.Thread(target=run_flask_server, daemon=True).start()
    
    print("✅ Bot Started with Auto-Checker...")
    app = ApplicationBuilder().token(BOT_TOKEN).request(HTTPXRequest(connect_timeout=60, read_timeout=60)).build()

    # 2. JOB QUEUE START (Email Checker)
    # execute after every 1 min
    if app.job_queue:
        app.job_queue.run_repeating(check_new_emails_job, interval=60, first=10)

    # Handlers
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("login", login_command))
    
    # Conversation: Send Email (Updated to handle Reply Button)
    send_handler = ConversationHandler(
        entry_points=[
            CallbackQueryHandler(start_sending, pattern="^menu_send$"),
            CallbackQueryHandler(reply_button_handler, pattern="^reply_last_email$") # <-- New Entry Point
        ],
        states={
            RECIPIENT: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_recipient)],
            SUBJECT: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_subject)],
            BODY: [MessageHandler(filters.TEXT & ~filters.COMMAND, send_email_final)],
        },
        fallbacks=[CommandHandler("cancel", cancel)]
    )
    app.add_handler(send_handler)

    # Conversation: Read Specific
    app.add_handler(ConversationHandler(
        entry_points=[CallbackQueryHandler(ask_sender_email, pattern="^read_specific$")],
        states={ASK_SENDER_EMAIL: [MessageHandler(filters.TEXT & ~filters.COMMAND, fetch_specific_email)]},
        fallbacks=[CommandHandler("cancel", cancel)]
    ))

    app.add_handler(CallbackQueryHandler(read_menu_handler, pattern="^menu_read$"))
    app.add_handler(CallbackQueryHandler(fetch_latest_email, pattern="^read_latest$"))

    app.run_polling()