import threading
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, CallbackQueryHandler, MessageHandler, filters, ContextTypes, ConversationHandler
from config_env import BOT_TOKEN, OWNER_TELEGRAM_ID
from gmail_service import list_messages, get_email_details, send_email_api
from auth_server import run_flask_server
from ai_service import summarize_email, generate_draft_reply

WAITING_FOR_INSTRUCTION = 0

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_TELEGRAM_ID: return
    text = (
        "👋 **Boss! System Online.**\n\n"
        "📜 **/inbox** - Show latest 5 emails\n"
        "🔍 **/search <keyword>** - Search emails\n"
        "(Example: `/search job offer`)"
    )
    await update.message.reply_text(text, parse_mode="Markdown")

async def cmd_inbox(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await show_email_list(update, query='label:INBOX')

async def cmd_search(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("🔍 Likhna bhool gaye! Use: `/search your_keyword`")
        return
    query = " ".join(context.args)
    await show_email_list(update, query=query)

async def show_email_list(update: Update, query):
    emails = list_messages(query=query, max_results=5)
    if not emails:
        await update.message.reply_text("📭 Nothing found.")
        return

    # List dikhao Buttons ke sath
    for email in emails:
        btn = [[InlineKeyboardButton(f"📖 Read: {email['subject'][:20]}...", callback_data=f"read_{email['id']}")]]
        txt = f"👤 **{email['sender']}**\n📌 {email['subject']}"
        await update.message.reply_text(txt, reply_markup=InlineKeyboardMarkup(btn))

async def handle_read(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    msg_id = query.data.split("_")[1]
    
    details = get_email_details(msg_id)
    context.user_data['last_details'] = details
    
    msg = f"📩 **{details['subject']}**\n👤 {details['sender']}\n\n"
    if len(details['body'].split()) > 50:
        msg += f"✨ **AI Summary:**\n{summarize_email(details['body'])}"
    else:
        msg += f"📝 **Body:**\n{details['body']}"

    kb = [[InlineKeyboardButton("✍️ AI Reply", callback_data="start_reply")]]
    await query.edit_message_text(msg, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(kb))

# --- AI REPLY FLOW (SAME AS BEFORE) ---
async def start_reply_flow(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.edit_message_text("🤖 **AI Active.** Reply mein kya bolna hai?")
    return WAITING_FOR_INSTRUCTION

async def process_ai_draft(update: Update, context: ContextTypes.DEFAULT_TYPE):
    draft = generate_draft_reply(context.user_data['last_details']['body'], update.message.text)
    context.user_data['final_draft'] = draft
    kb = [[InlineKeyboardButton("🚀 Send", callback_data="send_final"), InlineKeyboardButton("❌ Cancel", callback_data="cancel")]]
    await update.message.reply_text(f"🧐 **Draft:**\n\n{draft}", reply_markup=InlineKeyboardMarkup(kb))
    return WAITING_FOR_INSTRUCTION

async def send_final_email(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    d = context.user_data['last_details']
    res = send_email_api(d['sender'], f"Re: {d['subject']}", context.user_data['final_draft'])
    await query.edit_message_text(res)
    return ConversationHandler.END

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.callback_query.edit_message_text("❌ Cancelled.")
    return ConversationHandler.END

if __name__ == "__main__":
    threading.Thread(target=run_flask_server, daemon=True).start()
    app = ApplicationBuilder().token(BOT_TOKEN).build()
    
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("inbox", cmd_inbox))
    app.add_handler(CommandHandler("search", cmd_search))
    app.add_handler(CallbackQueryHandler(handle_read, pattern="^read_"))
    
    reply_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(start_reply_flow, pattern="start_reply")],
        states={WAITING_FOR_INSTRUCTION: [MessageHandler(filters.TEXT, process_ai_draft), CallbackQueryHandler(send_final_email, pattern="send_final"), CallbackQueryHandler(cancel, pattern="cancel")]},
        fallbacks=[]
    )
    app.add_handler(reply_conv)
    app.run_polling()