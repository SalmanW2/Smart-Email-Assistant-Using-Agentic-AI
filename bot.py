from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, CallbackQueryHandler, ContextTypes

from config_env import BOT_TOKEN, OWNER_TELEGRAM_ID
from gmail_service import get_last_email


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message:
        return

    user_id = update.message.from_user.id

    if user_id != OWNER_TELEGRAM_ID:
        await update.message.reply_text(
            "🤖 This email assistant is currently serving its main owner.\n"
            "Access is limited.\nThank you for understanding."
        )
        return

    keyboard = [
        [InlineKeyboardButton("📩 Read Last Email", callback_data="read_email")]
    ]

    await update.message.reply_text(
        "Welcome 👋\nChoose an option:",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )


async def buttons(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query

    if not query:
        return

    await query.answer()

    user_id = query.from_user.id

    if user_id != OWNER_TELEGRAM_ID:
        await query.edit_message_text("❌ Not authorized.")
        return

    if query.data == "read_email":
        email_text = get_last_email()
        await query.edit_message_text(email_text[:4000])  # Telegram limit safe


app = ApplicationBuilder().token(BOT_TOKEN).build()
app.add_handler(CommandHandler("start", start))
app.add_handler(CallbackQueryHandler(buttons))

print("✅ Bot is running...")
app.run_polling()