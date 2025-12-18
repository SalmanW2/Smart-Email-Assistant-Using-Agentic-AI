import sys
import asyncio
import logging
import os
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.request import HTTPXRequest
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

# --- FAKE WEB SERVER FOR RENDER (KEEP ALIVE) ---
# Ye hissa Render ko "Dhoka" dene ke liye hai taake wo Port Error na de
class HealthCheckHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"Bot is Alive and Running!")

def start_fake_server():
    port = int(os.environ.get("PORT", 10000))  # Render ka diya hua Port uthayega
    server = HTTPServer(("0.0.0.0", port), HealthCheckHandler)
    print(f"🌍 Fake Server started on Port {port} to keep Render happy.")
    server.serve_forever()
# -----------------------------------------------

# --- STATES ---
RECIPIENT, SUBJECT, BODY = range(3)

# --- HELPER FUNCTION: MAIN MENU ---
def get_main_menu_keyboard():
    keyboard = [
        [InlineKeyboardButton("📩 Read Last Email", callback_data="read_email")],
        [InlineKeyboardButton("✍️ Compose New Email", callback_data="start_sending_process")]
    ]
    return InlineKeyboardMarkup(keyboard)

# --- COMMAND HANDLERS ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message: return
    user_id = update.message.from_user.id

    if user_id == OWNER_TELEGRAM_ID:
        await update.message.reply_text("Hello! I am your Email Assistant 2.0")
        await update.message.reply_text(
            "How can I assist you today, Sir?",
            reply_markup=get_main_menu_keyboard()
        )
    else:
        await update.message.reply_text("🚫 **Access Denied:** You are not authorized to use this assistant.", parse_mode="Markdown")

async def read_email_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if query.from_user.id != OWNER_TELEGRAM_ID: return
    
    await query.edit_message_text("🔄 **Accessing Gmail Server...**\nPlease wait while I fetch your latest email.", parse_mode="Markdown")
    
    try:
        email_text = get_last_email()
        await query.message.reply_text(
            email_text, 
            reply_markup=get_main_menu_keyboard(),
            parse_mode="Markdown"
        )
    except Exception as e:
        await query.message.reply_text(f"⚠️ **Error:** Could not fetch email.\n`{e}`", parse_mode="Markdown")

# --- CONVERSATION HANDLER (SENDING EMAIL) ---
async def start_sending(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if query.from_user.id != OWNER_TELEGRAM_ID: return ConversationHandler.END

    await query.edit_message_text(
        "📝 **New Email Composition**\n\n**Step 1/3:** Please enter the **Recipient's Email Address**:\n(Type /cancel to abort)", 
        parse_mode="Markdown"
    )
    return RECIPIENT

async def get_recipient(update: Update, context: ContextTypes.DEFAULT_TYPE):
    email_address = update.message.text.strip()
    context.user_data['to_email'] = email_address
    
    await update.message.reply_text(
        f"✅ **Recipient Set:** `{email_address}`\n\n**Step 2/3:** Please enter the **Subject** of the email:", 
        parse_mode="Markdown"
    )
    return SUBJECT

async def get_subject(update: Update, context: ContextTypes.DEFAULT_TYPE):
    subject_text = update.message.text
    context.user_data['subject'] = subject_text
    
    await update.message.reply_text(
        f"✅ **Subject Set:** `{subject_text}`\n\n**Step 3/3:** Please type the **Message Body**:", 
        parse_mode="Markdown"
    )
    return BODY

async def get_body_and_send(update: Update, context: ContextTypes.DEFAULT_TYPE):
    body_text = update.message.text
    to_email = context.user_data['to_email']
    subject = context.user_data['subject']

    await update.message.reply_text("🚀 **Sending your email via Gmail API...**")
    
    try:
        status_message = create_and_send_email(to_email, subject, body_text)
        final_msg = f"✅ **Success!**\n\n{status_message}"
    except Exception as e:
        final_msg = f"❌ **Failed to send email.**\nError: {str(e)}"

    await update.message.reply_text(final_msg, reply_markup=get_main_menu_keyboard(), parse_mode="Markdown")
    return ConversationHandler.END

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🚫 **Operation Cancelled.**", reply_markup=get_main_menu_keyboard())
    return ConversationHandler.END

# --- MAIN EXECUTION ---
if __name__ == "__main__":
    if sys.platform.startswith("win"):
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

    # --- 1. Fake Server Start Karna (Alag Thread mein) ---
    # Ye background mein chalta rahega taake Render khush rahe
    threading.Thread(target=start_fake_server, daemon=True).start()
    # -----------------------------------------------------

    print("✅ Professional Bot 2.0 is Starting...")
    
    t_request = HTTPXRequest(connect_timeout=60.0, read_timeout=60.0)
    app = ApplicationBuilder().token(BOT_TOKEN).request(t_request).build()

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

    print("✅ Bot is Running via Long Polling...")
    app.run_polling()