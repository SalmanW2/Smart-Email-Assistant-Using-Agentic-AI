import sys
import asyncio
import threading
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, CallbackQueryHandler, MessageHandler, filters, ContextTypes, ConversationHandler
from config_env import BOT_TOKEN, OWNER_TELEGRAM_ID
from gmail_service import get_latest_id, get_email_details, send_email_api, get_credentials
from auth_server import run_flask_server, get_login_link
from ai_service import summarize_email, generate_draft_reply

WAITING_FOR_INSTRUCTION = 0

def is_authenticated():
    creds = get_credentials()
    return creds is not None and creds.valid

# --- HANDLERS ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_TELEGRAM_ID: return
    if is_authenticated():
        kb = [
            [InlineKeyboardButton("🕒 Last Email", callback_data="fetch_last")],
            [InlineKeyboardButton("📩 Last Unread", callback_data="fetch_unread")]
        ]
        await update.message.reply_text("👋 Boss! System Online. Choose option:", reply_markup=InlineKeyboardMarkup(kb))
    else:
        link = get_login_link()
        kb = [[InlineKeyboardButton("🔗 Login Gmail", url=link)]]
        await update.message.reply_text("⚠️ Session Expired. Please login:", reply_markup=InlineKeyboardMarkup(kb))

async def handle_fetch(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    # Check for unread if requested
    is_unread = True if query.data == "fetch_unread" else False
    msg_id = get_latest_id(filter_unread=is_unread)
    
    if not msg_id:
        await query.edit_message_text("📭 No emails found.")
        return

    details = get_email_details(msg_id)
    context.user_data['last_details'] = details
    
    msg = f"📩 **Email Found**\n👤 From: `{details['sender']}`\n📌 Subject: `{details['subject']}`\n\n"
    
    # Summarize if long
    if len(details['body'].split()) > 50:
        summary = summarize_email(details['body'])
        msg += f"✨ **AI Summary:**\n{summary}"
    else:
        msg += f"📝 **Body:**\n{details['body']}"

    kb = [[InlineKeyboardButton("✍️ Reply (AI Agent)", callback_data="start_reply")], [InlineKeyboardButton("🔙 Menu", callback_data="main_menu")]]
    await query.edit_message_text(msg, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(kb))

# --- AI REPLY FLOW ---
async def start_reply_flow(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.edit_message_text("🤖 **AI Agent Active.** What should I say in the reply?")
    return WAITING_FOR_INSTRUCTION

async def process_ai_draft(update: Update, context: ContextTypes.DEFAULT_TYPE):
    instruction = update.message.text
    details = context.user_data.get('last_details')
    
    await update.message.reply_text("⏳ Drafting with Gemini...")
    draft = generate_draft_reply(details['body'], instruction)
    context.user_data['final_draft'] = draft
    
    kb = [[InlineKeyboardButton("🚀 Send Now", callback_data="send_final")], [InlineKeyboardButton("❌ Cancel", callback_data="main_menu")]]
    await update.message.reply_text(f"🧐 **Review Draft:**\n\n{draft}", reply_markup=InlineKeyboardMarkup(kb))
    return WAITING_FOR_INSTRUCTION

async def send_final_email(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    details = context.user_data.get('last_details')
    draft = context.user_data.get('final_draft')
    
    result = send_email_api(details['sender'], f"Re: {details['subject']}", draft)
    await query.edit_message_text(result)
    return ConversationHandler.END

if __name__ == "__main__":
    threading.Thread(target=run_flask_server, daemon=True).start()
    app = ApplicationBuilder().token(BOT_TOKEN).build()
    
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(start, pattern="main_menu"))
    app.add_handler(CallbackQueryHandler(handle_fetch, pattern="^fetch_"))
    
    reply_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(start_reply_flow, pattern="start_reply")],
        states={
            WAITING_FOR_INSTRUCTION: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, process_ai_draft),
                CallbackQueryHandler(send_final_email, pattern="send_final")
            ]
        },
        fallbacks=[CallbackQueryHandler(start, pattern="main_menu")]
    )
    app.add_handler(reply_conv)
    
    print("🚀 Bot is running...")
    app.run_polling()