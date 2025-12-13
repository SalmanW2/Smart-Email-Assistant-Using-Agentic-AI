from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
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

# --- STATES (Conversation Steps) ---
RECIPIENT, SUBJECT, BODY = range(3)

# --- START COMMAND (Authentication Check) ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message:
        return

    user_id = update.message.from_user.id

    if user_id == OWNER_TELEGRAM_ID:
        # Agar Owner hai to Menu dikhao
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
        # Agar Stranger hai to Access Denied
        await update.message.reply_text(
            "🚫 **This Email Assistant is currently serving with its owner**",
            parse_mode="Markdown"
        )

# --- READ EMAIL HANDLER (Single Action) ---
async def read_email_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if query.from_user.id != OWNER_TELEGRAM_ID:
        return

    await query.edit_message_text("⏳ Fetching your last email...")

    # Backend se email mangwayi
    email_text = get_last_email()
    
    # Wapas menu dikhana zaroori hai
    keyboard = [
        [InlineKeyboardButton("📩 Read Last Email", callback_data="read_email")],
        [InlineKeyboardButton("📤 Send New Email", callback_data="start_sending_process")]
    ]
    await query.message.reply_text(email_text, reply_markup=InlineKeyboardMarkup(keyboard))

# --- SEND EMAIL PROCESS (Entry Point) ---
async def start_sending(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    if query.from_user.id != OWNER_TELEGRAM_ID:
        return ConversationHandler.END

    await query.edit_message_text(
        "Step 1/3: 📤 **Kisko email bhejna hai?**\n\n(Email address type karein ya /cancel likhein)",
        parse_mode="Markdown"
    )
    return RECIPIENT

# --- STEP 1: Get Email Address ---
async def get_recipient(update: Update, context: ContextTypes.DEFAULT_TYPE):
    email_address = update.message.text
    context.user_data['to_email'] = email_address # Save in memory

    await update.message.reply_text(
        f"✅ To: `{email_address}`\n\nStep 2/3: 📝 **Subject kya rakhna hai?**",
        parse_mode="Markdown"
    )
    return SUBJECT

# --- STEP 2: Get Subject ---
async def get_subject(update: Update, context: ContextTypes.DEFAULT_TYPE):
    subject_text = update.message.text
    context.user_data['subject'] = subject_text # Save in memory

    await update.message.reply_text(
        f"✅ Subject: `{subject_text}`\n\nStep 3/3: 💬 **Message (Body) kya hai?**",
        parse_mode="Markdown"
    )
    return BODY

# --- STEP 3: Get Body & Send ---
async def get_body_and_send(update: Update, context: ContextTypes.DEFAULT_TYPE):
    body_text = update.message.text
    
    # Purana data wapas nikala
    to_email = context.user_data['to_email']
    subject = context.user_data['subject']

    await update.message.reply_text("🚀 Sending email, please wait...")

    # FINAL ACTION: Email Bhejo
    status_message = create_and_send_email(to_email, subject, body_text)

    # Result dikhao aur wapas Menu do
    keyboard = [
            [InlineKeyboardButton("📩 Read Last Email", callback_data="read_email")],
            [InlineKeyboardButton("📤 Send New Email", callback_data="start_sending_process")]
    ]
    await update.message.reply_text(status_message, reply_markup=InlineKeyboardMarkup(keyboard))
    
    return ConversationHandler.END

# --- CANCEL OPTION ---
async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("❌ Process Cancelled.")
    return ConversationHandler.END

# --- MAIN RUNNER ---
if __name__ == "__main__":
    print("✅ Bot is Starting...")
    app = ApplicationBuilder().token(BOT_TOKEN).build()

    # Conversation Handler (Send Flow)
    email_conversation = ConversationHandler(
        entry_points=[CallbackQueryHandler(start_sending, pattern="^start_sending_process$")],
        states={
            RECIPIENT: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_recipient)],
            SUBJECT: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_subject)],
            BODY: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_body_and_send)],
        },
        fallbacks=[CommandHandler("cancel", cancel)]
    )

    # Handlers Add kiye
    app.add_handler(CommandHandler("start", start))
    app.add_handler(email_conversation)
    app.add_handler(CallbackQueryHandler(read_email_handler, pattern="^read_email$"))

    print("✅ Bot is Running! Press Ctrl+C to stop.")
    app.run_polling()