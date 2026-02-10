import threading
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, CallbackQueryHandler, MessageHandler, filters, ContextTypes, ConversationHandler
from config_env import BOT_TOKEN, OWNER_TELEGRAM_ID
from gmail_service import list_messages, get_email_details, send_email_api, is_user_authenticated
from auth_server import run_flask_server, get_login_link
from ai_service import summarize_email, generate_draft_reply

# States for Conversation
WAITING_FOR_INSTRUCTION = 1
WAITING_FOR_EDIT = 2

# --- AUTH & START ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_TELEGRAM_ID: return

    if not is_user_authenticated():
        link = get_login_link()
        kb = [[InlineKeyboardButton("🔐 Authenticate Gmail", url=link)]]
        await update.message.reply_text(
            "⚠️ **Authorization Required**\n\n"
            "Please authorize the bot to access your Gmail account to proceed.",
            reply_markup=InlineKeyboardMarkup(kb),
            parse_mode="Markdown"
        )
    else:
        await update.message.reply_text(
            "✅ **System Operational**\n\n"
            "Background polling is active. You will be notified of new emails.\n"
            "Commands:\n"
            "📜 `/inbox` - View recent emails\n"
            "🔍 `/search <keyword>` - Search emails",
            parse_mode="Markdown"
        )

# --- BACKGROUND POLLING (1 Minute Interval) ---
async def check_new_emails(context: ContextTypes.DEFAULT_TYPE):
    if not is_user_authenticated(): return

    # Check for latest email
    emails = list_messages(max_results=1)
    if not emails: return

    latest_id = emails[0]['id']
    last_known_id = context.bot_data.get('last_email_id')

    if latest_id != last_known_id:
        context.bot_data['last_email_id'] = latest_id
        details = get_email_details(latest_id)
        
        # Determine Summary
        summary = "No content."
        if details and len(details['body'].split()) > 30:
            summary = summarize_email(details['body'])
        elif details:
            summary = details['body'][:200] + "..."

        text = (
            f"📨 **New Email Received**\n"
            f"**From:** `{details['sender']}`\n"
            f"**Subject:** `{details['subject']}`\n\n"
            f"**Summary:**\n{summary}"
        )
        
        kb = [
            [InlineKeyboardButton("📖 Read Full", callback_data=f"read_{latest_id}")],
            [InlineKeyboardButton("✍️ Reply", callback_data=f"reply_{latest_id}")],
            [InlineKeyboardButton("🚫 Ignore", callback_data="ignore")]
        ]
        await context.bot.send_message(
            chat_id=OWNER_TELEGRAM_ID, 
            text=text, 
            parse_mode="Markdown", 
            reply_markup=InlineKeyboardMarkup(kb)
        )

# --- INBOX & SEARCH ---
async def cmd_inbox(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_user_authenticated():
        await update.message.reply_text("⚠️ Please login first using /start")
        return
    await show_email_list(update, query='label:INBOX', title="Recent Inbox")

async def cmd_search(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_user_authenticated():
        await update.message.reply_text("⚠️ Please login first using /start")
        return
    if not context.args:
        await update.message.reply_text("ℹ️ Usage: `/search <keyword>`", parse_mode="Markdown")
        return
    query = " ".join(context.args)
    await show_email_list(update, query=query, title=f"Search: {query}")

async def show_email_list(update: Update, query, title):
    emails = list_messages(query=query, max_results=5)
    if not emails:
        await update.message.reply_text(f"📭 No emails found for: {title}")
        return

    await update.message.reply_text(f"📂 **{title}**", parse_mode="Markdown")
    for email in emails:
        kb = [[InlineKeyboardButton("📖 Read", callback_data=f"read_{email['id']}"), InlineKeyboardButton("✍️ Reply", callback_data=f"reply_{email['id']}")]]
        text = f"👤 **{email['sender']}**\n📌 {email['subject']}"
        await update.message.reply_text(text, reply_markup=InlineKeyboardMarkup(kb))

# --- ACTION HANDLERS ---
async def handle_read(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    msg_id = query.data.split("_")[1]
    
    details = get_email_details(msg_id)
    text = f"📩 **Full Email**\n\n**From:** {details['sender']}\n**Subject:** {details['subject']}\n\n{details['body']}"
    
    # Split message if too long for Telegram (Limit 4096)
    if len(text) > 4000:
        text = text[:4000] + "... (Truncated)"
        
    await query.message.reply_text(text, parse_mode="Markdown")

async def handle_ignore(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.callback_query.answer("Email Ignored.")
    await update.callback_query.message.delete()

# --- REPLY WORKFLOW (CONVERSATION) ---
async def start_reply_flow(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    msg_id = query.data.split("_")[1]
    
    details = get_email_details(msg_id)
    context.user_data['active_email'] = details
    
    await query.message.reply_text(
        f"🤖 **AI Assistant**\n"
        f"Drafting reply to: {details['sender']}\n\n"
        f"Please provide instructions for the reply (e.g., 'Accept the offer', 'Ask for rescheduling')."
    )
    return WAITING_FOR_INSTRUCTION

async def generate_draft(update: Update, context: ContextTypes.DEFAULT_TYPE):
    instruction = update.message.text
    email_data = context.user_data.get('active_email')
    
    await update.message.reply_text("⏳ Generating professional draft...")
    draft = generate_draft_reply(email_data['body'], instruction)
    context.user_data['current_draft'] = draft
    
    await send_draft_options(update, draft)
    return WAITING_FOR_EDIT

async def send_draft_options(update, draft):
    kb = [
        [InlineKeyboardButton("🚀 Send Now", callback_data="send_now")],
        [InlineKeyboardButton("✏️ Edit / Refine", callback_data="edit_draft")],
        [InlineKeyboardButton("❌ Cancel", callback_data="cancel_flow")]
    ]
    await update.message.reply_text(f"📝 **Review Draft**\n\n{draft}", reply_markup=InlineKeyboardMarkup(kb))

async def handle_edit_request(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.message.reply_text("Please enter your feedback to refine the draft:")
    return WAITING_FOR_INSTRUCTION # Loop back to generation with new input

async def finalize_send(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    email_data = context.user_data.get('active_email')
    draft = context.user_data.get('current_draft')
    
    status = send_email_api(email_data['sender'], f"Re: {email_data['subject']}", draft)
    await query.edit_message_text(status)
    return ConversationHandler.END

async def cancel_flow(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.callback_query.edit_message_text("❌ Action Cancelled.")
    return ConversationHandler.END

# --- MAIN EXECUTION ---
if __name__ == "__main__":
    threading.Thread(target=run_flask_server, daemon=True).start()
    app = ApplicationBuilder().token(BOT_TOKEN).build()
    
    # Commands
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("inbox", cmd_inbox))
    app.add_handler(CommandHandler("search", cmd_search))
    
    # Callbacks (Read/Ignore)
    app.add_handler(CallbackQueryHandler(handle_read, pattern="^read_"))
    app.add_handler(CallbackQueryHandler(handle_ignore, pattern="^ignore$"))
    
    # Conversation (Reply -> Draft -> Edit -> Send)
    reply_handler = ConversationHandler(
        entry_points=[CallbackQueryHandler(start_reply_flow, pattern="^reply_")],
        states={
            WAITING_FOR_INSTRUCTION: [MessageHandler(filters.TEXT & ~filters.COMMAND, generate_draft)],
            WAITING_FOR_EDIT: [
                CallbackQueryHandler(finalize_send, pattern="^send_now$"),
                CallbackQueryHandler(handle_edit_request, pattern="^edit_draft$"),
                CallbackQueryHandler(cancel_flow, pattern="^cancel_flow$")
            ]
        },
        fallbacks=[CommandHandler("start", start)]
    )
    app.add_handler(reply_handler)
    
    # Background Job (Polling)
    if app.job_queue:
        app.job_queue.run_repeating(check_new_emails, interval=60, first=10)
    
    print("System Online. Polling started...")
    app.run_polling()