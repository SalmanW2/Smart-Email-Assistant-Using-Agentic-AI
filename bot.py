import sys
import asyncio
import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.request import HTTPXRequest  # <--- NAYA IMPORT
from telegram.ext import (
    ApplicationBuilder, 
    CommandHandler, 
    CallbackQueryHandler, 
    ContextTypes, 
    ConversationHandler, 
    MessageHandler, 
    filters
)
from config_env import BOT_TOKEN, OWNER_TELEGRAM_ID
from gmail_service import get_last_email, create_and_send_email

# --- LOGGING SETUP ---
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)

# --- STATES ---
RECIPIENT, SUBJECT, BODY = range(3)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message: return
    user_id = update.message.from_user.id

    if user_id == OWNER_TELEGRAM_ID:
        keyboard = [
            [InlineKeyboardButton("📩 Read Last Email", callback_data="read_email")],
            [InlineKeyboardButton("📤 Send New Email", callback_data="start_sending_process")]
        ]
        await update.message.reply_text(
            "👋 **Smart Email Assistant Services has Enabled for your Gmail**",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode="Markdown"
        )
    else:
        await update.message.reply_text("🚫 **This Email Assistant is currently serving with its owner**", parse_mode="Markdown")

async def read_email_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if query.from_user.id != OWNER_TELEGRAM_ID: return
    
    await query.edit_message_text("⏳ Fetching your last email...")
    email_text = get_last_email()
    
    keyboard = [[InlineKeyboardButton("📩 Read Last Email", callback_data="read_email")], [InlineKeyboardButton("📤 Send New Email", callback_data="start_sending_process")]]
    await query.message.reply_text(email_text, reply_markup=InlineKeyboardMarkup(keyboard))

async def start_sending(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if query.from_user.id != OWNER_TELEGRAM_ID: return ConversationHandler.END

    await query.edit_message_text("Step 1/3: 📤 **Kisko email bhejna hai?**\n\n(Email address type karein ya /cancel likhein)", parse_mode="Markdown")
    return RECIPIENT

async def get_recipient(update: Update, context: ContextTypes.DEFAULT_TYPE):
    email_address = update.message.text
    context.user_data['to_email'] = email_address
    await update.message.reply_text(f"✅ To: `{email_address}`\n\nStep 2/3: 📝 **Subject kya rakhna hai?**", parse_mode="Markdown")
    return SUBJECT

async def get_subject(update: Update, context: ContextTypes.DEFAULT_TYPE):
    subject_text = update.message.text
    context.user_data['subject'] = subject_text
    await update.message.reply_text(f"✅ Subject: `{subject_text}`\n\nStep 3/3: 💬 **Message (Body) kya hai?**", parse_mode="Markdown")
    return BODY

async def get_body_and_send(update: Update, context: ContextTypes.DEFAULT_TYPE):
    body_text = update.message.text
    to_email = context.user_data['to_email']
    subject = context.user_data['subject']

    await update.message.reply_text("🚀 Sending email, please wait...")
    status_message = create_and_send_email(to_email, subject, body_text)
    
    keyboard = [[InlineKeyboardButton("📩 Read Last Email", callback_data="read_email")], [InlineKeyboardButton("📤 Send New Email", callback_data="start_sending_process")]]
    await update.message.reply_text(status_message, reply_markup=InlineKeyboardMarkup(keyboard))
    return ConversationHandler.END

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("❌ Process Cancelled.")
    return ConversationHandler.END

if __name__ == "__main__":
    if sys.platform.startswith("win"):
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

    print("✅ Bot is Starting...")
    
    # --- TIMEOUT FIX (Main Change Yahan Hai) ---
    # Hum bot ko bol rahe hain ke 60 second tak connection ka wait kare
    t_request = HTTPXRequest(connect_timeout=60.0, read_timeout=60.0)
    
    app = ApplicationBuilder().token(BOT_TOKEN).request(t_request).build()
    # -------------------------------------------

    email_conversation = ConversationHandler(
        entry_points=[CallbackQueryHandler(start_sending, pattern="^start_sending_process$")],
        states={
            RECIPIENT: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_recipient)],
            SUBJECT: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_subject)],
            BODY: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_body_and_send)],
        },
        fallbacks=[CommandHandler("cancel", cancel)]
    )

    app.add_handler(CommandHandler("start", start))
    app.add_handler(email_conversation)
    app.add_handler(CallbackQueryHandler(read_email_handler, pattern="^read_email$"))

    print("✅ Bot is Running with EXTENDED TIMEOUT! Press Ctrl+C to stop.")
    app.run_polling()