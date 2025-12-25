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
from ai_service import summarize_email, generate_draft_reply

# --- LOGGING ---
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', 
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# --- CONVERSATION STATES ---
# 1. Manual Send
RECIPIENT, SUBJECT, BODY = range(3)
# 2. Search Email
ASK_SENDER_EMAIL = range(3, 4)
# 3. AI Reply Agent
WAITING_FOR_INSTRUCTION = range(4, 5)

# --- GLOBAL MEMORY ---
last_checked_email_id = None 

# ==============================================================================
#   HELPER FUNCTIONS (UI & AUTH)
# ==============================================================================

def is_user_authenticated():
    """Checks if valid credentials exist."""
    creds = get_credentials()
    return creds is not None and creds.valid

def get_dashboard_keyboard():
    """Main Menu Buttons"""
    keyboard = [
        [InlineKeyboardButton("📩 Inbox Overview", callback_data="menu_read")],
        [InlineKeyboardButton("✍️ Compose Email", callback_data="menu_send")]
    ]
    return InlineKeyboardMarkup(keyboard)

def get_login_keyboard(auth_link):
    """Login Button"""
    keyboard = [[InlineKeyboardButton("🔗 Connect Gmail Account", url=auth_link)]]
    return InlineKeyboardMarkup(keyboard)

# ==============================================================================
#   AUTO-CHECKER JOB (The Heartbeat 💓)
# ==============================================================================

async def check_new_emails_job(context: ContextTypes.DEFAULT_TYPE):
    global last_checked_email_id
    
    # --- 1. AUTHENTICATION CHECK ---
    if not is_user_authenticated():
        # Check agar humne pehle hi warning bhej di hai (taake spam na ho)
        if not context.bot_data.get('auth_warning_sent'):
            link = get_login_link()
            if link:
                try:
                    await context.bot.send_message(
                        chat_id=OWNER_TELEGRAM_ID,
                        text="⚠️ **Session Expired!**\nYour Gmail access has triggered a security logout. Please login again to receive emails.",
                        reply_markup=get_login_keyboard(link),
                        parse_mode="Markdown"
                    )
                    # Flag set karo taake agle minute dubara msg na jaye
                    context.bot_data['auth_warning_sent'] = True
                except Exception as e:
                    logger.error(f"Failed to send auth warning: {e}")
        return
    else:
        # Agar login sahi hai, to warning flag reset kar do
        context.bot_data['auth_warning_sent'] = False

    # --- 2. NEW EMAIL CHECK ---
    try:
        latest_id = get_latest_message_id()
        
        # First Run (Initialize)
        if last_checked_email_id is None:
            last_checked_email_id = latest_id
            return

        # Compare IDs
        if latest_id and latest_id != last_checked_email_id:
            last_checked_email_id = latest_id
            
            details = get_email_details(latest_id)
            if not details: return

            # Save Data for AI Context
            context.bot_data['last_email_id'] = latest_id
            context.bot_data['last_email_body'] = details['snippet']
            context.bot_data['last_sender'] = details['sender_email']

            # --- WORD COUNT LOGIC ---
            word_count = len(details['snippet'].split())
            msg_text = ""
            keyboard = []

            if word_count > 100:
                # > 100 Words: Show AI Summary + Read Full Button
                summary = summarize_email(details['snippet'])
                msg_text = (
                    f"🚨 **NEW EMAIL (AI Summary)**\n\n"
                    f"👤 **From:** `{details['sender_view']}`\n"
                    f"📌 **Subject:** `{details['subject']}`\n\n"
                    f"✨ **Summary:**\n{summary}"
                )
                keyboard.append([InlineKeyboardButton("📄 Read Full Email", callback_data="read_full_auto")])
            else:
                # < 100 Words: Show Full Body directly
                msg_text = (
                    f"🚨 **NEW EMAIL**\n\n"
                    f"👤 **From:** `{details['sender_view']}`\n"
                    f"📌 **Subject:** `{details['subject']}`\n\n"
                    f"📝 **Body:**\n{details['snippet']}"
                )

            # Common Buttons (Draft Reply & Ignore)
            keyboard.append([InlineKeyboardButton("✍️ Draft Reply (AI)", callback_data="start_ai_reply")])
            keyboard.append([InlineKeyboardButton("🚫 Ignore", callback_data="ignore_notification")])

            await context.bot.send_message(
                chat_id=OWNER_TELEGRAM_ID, 
                text=msg_text, 
                parse_mode="Markdown",
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
            
    except Exception as e:
        logger.error(f"Auto-Check Error: {e}")

# ==============================================================================
#   COMMAND HANDLERS
# ==============================================================================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Entry Point: Checks Auth First"""
    if str(update.message.from_user.id) != str(OWNER_TELEGRAM_ID): return

    if is_user_authenticated():
        await update.message.reply_text(
            "👋 **Welcome Boss!**\n\nAI Agent is online and monitoring your inbox. 🕵️", 
            reply_markup=get_dashboard_keyboard(),
            parse_mode="Markdown"
        )
    else:
        link = get_login_link()
        if link:
            await update.message.reply_text(
                "👋 **Welcome!**\nTo start using the Agent, please connect your Gmail account.",
                reply_markup=get_login_keyboard(link),
                parse_mode="Markdown"
            )

async def login_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if str(update.message.from_user.id) != str(OWNER_TELEGRAM_ID): return
    link = get_login_link()
    if link:
        await update.message.reply_text(
            "👇 **Click below to Login:**", 
            reply_markup=get_login_keyboard(link),
            parse_mode="Markdown"
        )

# ==============================================================================
#   CALLBACKS: NOTIFICATION ACTIONS
# ==============================================================================

async def ignore_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer("Dismissed.")
    await query.delete_message()

async def read_full_auto_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Shows full email when requested"""
    query = update.callback_query
    await query.answer()
    
    email_id = context.bot_data.get('last_email_id')
    details = get_email_details(email_id)
    
    if details:
        text = (
            f"📄 **FULL EMAIL**\n\n"
            f"👤 **From:** `{details['sender_view']}`\n"
            f"📝 **Body:**\n{details['snippet']}"
        )
        keyboard = [
            [InlineKeyboardButton("✍️ Draft Reply (AI)", callback_data="start_ai_reply")],
            [InlineKeyboardButton("🚫 Ignore", callback_data="ignore_notification")]
        ]
        await query.edit_message_text(text=text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(keyboard))
    else:
        await query.edit_message_text("❌ Error: Email not found.")

# ==============================================================================
#   🤖 AI REPLY CONVERSATION
# ==============================================================================

async def start_ai_reply(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    sender = context.bot_data.get('last_sender')
    if not sender:
        await query.edit_message_text("⚠️ Context lost. Please use manual send.")
        return ConversationHandler.END

    context.user_data['reply_to'] = sender
    
    await query.edit_message_text(
        f"🤖 **AI Agent Active**\nReplying to: `{sender}`\n\n"
        f"🗣️ **What should I say?**\n(e.g., 'Say thanks', 'Decline politely', 'Ask for meeting')",
        parse_mode="Markdown"
    )
    return WAITING_FOR_INSTRUCTION

async def generate_draft(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_instruction = update.message.text
    original_email = context.bot_data.get('last_email_body', '')
    
    await update.message.reply_text("⏳ **Drafting Reply...**")
    
    # AI Magic 🪄
    draft = generate_draft_reply(original_email, user_instruction)
    
    context.user_data['draft_body'] = draft
    context.user_data['draft_sub'] = "Re: (AI Reply)"

    msg = (
        f"🧐 **REVIEW DRAFT**\n"
        f"-------------------\n"
        f"{draft}\n"
        f"-------------------\n"
        f"Choose action:"
    )
    
    keyboard = [
        [InlineKeyboardButton("🚀 Send Now", callback_data="send_draft_now")],
        [InlineKeyboardButton("✏️ Edit Manual", callback_data="edit_draft_manual")],
        [InlineKeyboardButton("🔄 Try Again", callback_data="retry_ai_draft")]
    ]
    
    await update.message.reply_text(msg, reply_markup=InlineKeyboardMarkup(keyboard))
    return WAITING_FOR_INSTRUCTION

async def handle_draft_actions(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    action = query.data

    if action == "send_draft_now":
        to = context.user_data.get('reply_to')
        sub = context.user_data.get('draft_sub')
        body = context.user_data.get('draft_body')
        
        await query.edit_message_text(f"🚀 **Sending...**")
        result = create_and_send_email(to, sub, body)
        await query.edit_message_text(f"{result}\n\n✅ **Done!**")
        return ConversationHandler.END

    elif action == "edit_draft_manual":
        # Jump to manual body input
        await query.edit_message_text("✏️ **Type the full email body below:**")
        return BODY 

    elif action == "retry_ai_draft":
        await query.edit_message_text("🗣️ **Give me new instructions:**")
        return WAITING_FOR_INSTRUCTION

# ==============================================================================
#   STANDARD HANDLERS (Read/Send)
# ==============================================================================

async def read_menu_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    keyboard = [
        [InlineKeyboardButton("🕒 Last Email", callback_data="read_latest")],
        [InlineKeyboardButton("🔍 Specific Sender", callback_data="read_specific")]
    ]
    await query.edit_message_text("📂 **Inbox Options:**", reply_markup=InlineKeyboardMarkup(keyboard))

async def fetch_latest_email(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    if not is_user_authenticated():
        link = get_login_link()
        await query.edit_message_text("⚠️ **Session Expired.**", reply_markup=get_login_keyboard(link))
        return

    content = get_last_email()
    if content and content != "AUTH_ERROR":
        # Add AI context
        context.bot_data['last_email_id'] = get_latest_message_id()
        
        keyboard = [
            [InlineKeyboardButton("✍️ Draft Reply (AI)", callback_data="start_ai_reply")],
            [InlineKeyboardButton("🔙 Menu", callback_data="menu_read")]
        ]
        await query.edit_message_text(content, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(keyboard))
    else:
        await query.edit_message_text("📭 Empty or Error.")

# --- MANUAL SEND FLOW ---
async def start_sending_manual(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if not is_user_authenticated():
        link = get_login_link()
        await query.edit_message_text("⚠️ Please Login.", reply_markup=get_login_keyboard(link))
        return ConversationHandler.END
    await query.edit_message_text("✍️ **Recipient:**")
    return RECIPIENT

async def get_recipient(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['to'] = update.message.text
    await update.message.reply_text("📝 **Subject:**")
    return SUBJECT

async def get_subject(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['sub'] = update.message.text
    await update.message.reply_text("💬 **Body:**")
    return BODY

async def send_email_final(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # This handles both Manual Send AND 'Edit Draft'
    to = context.user_data.get('to') or context.user_data.get('reply_to')
    sub = context.user_data.get('sub') or context.user_data.get('draft_sub', 'No Subject')
    body = update.message.text
    
    await update.message.reply_text("🚀 **Sending...**")
    result = create_and_send_email(to, sub, body)
    await update.message.reply_text(result, reply_markup=get_dashboard_keyboard())
    return ConversationHandler.END

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("❌ Cancelled.", reply_markup=get_dashboard_keyboard())
    return ConversationHandler.END

# --- SEARCH FLOW (Stub for Specific Sender) ---
async def ask_sender(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.edit_message_text("🔍 **Enter Sender Email:**")
    return ASK_SENDER_EMAIL

async def fetch_specific(update: Update, context: ContextTypes.DEFAULT_TYPE):
    sender = update.message.text
    content = get_last_email(query=f"from:{sender}")
    if content:
        await update.message.reply_text(content, parse_mode="Markdown")
    else:
        await update.message.reply_text("❌ Not found.")
    return ConversationHandler.END

# ==============================================================================
#   MAIN
# ==============================================================================
if __name__ == "__main__":
    if sys.platform.startswith("win"):
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    
    threading.Thread(target=run_flask_server, daemon=True).start()
    
    print("✅ Bot Started (Agentic + Secure Mode)...")
    app = ApplicationBuilder().token(BOT_TOKEN).request(HTTPXRequest(connect_timeout=60, read_timeout=60)).build()

    if app.job_queue:
        app.job_queue.run_repeating(check_new_emails_job, interval=60, first=10)

    # Handlers
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("login", login_command))
    
    # AI Conversation
    ai_handler = ConversationHandler(
        entry_points=[CallbackQueryHandler(start_ai_reply, pattern="^start_ai_reply$")],
        states={
            WAITING_FOR_INSTRUCTION: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, generate_draft),
                CallbackQueryHandler(handle_draft_actions, pattern="^(send_draft_now|edit_draft_manual|retry_ai_draft)$")
            ],
            BODY: [MessageHandler(filters.TEXT & ~filters.COMMAND, send_email_final)]
        },
        fallbacks=[CommandHandler("cancel", cancel)]
    )
    app.add_handler(ai_handler)

    # Manual Send Conversation
    send_handler = ConversationHandler(
        entry_points=[CallbackQueryHandler(start_sending_manual, pattern="^menu_send$")],
        states={
            RECIPIENT: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_recipient)],
            SUBJECT: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_subject)],
            BODY: [MessageHandler(filters.TEXT & ~filters.COMMAND, send_email_final)],
        },
        fallbacks=[CommandHandler("cancel", cancel)]
    )
    app.add_handler(send_handler)

    # Read Handlers
    app.add_handler(ConversationHandler(
        entry_points=[CallbackQueryHandler(ask_sender, pattern="^read_specific$")],
        states={ASK_SENDER_EMAIL: [MessageHandler(filters.TEXT & ~filters.COMMAND, fetch_specific)]},
        fallbacks=[CommandHandler("cancel", cancel)]
    ))
    
    app.add_handler(CallbackQueryHandler(read_menu_handler, pattern="^menu_read$"))
    app.add_handler(CallbackQueryHandler(fetch_latest_email, pattern="^read_latest$"))
    app.add_handler(CallbackQueryHandler(read_full_auto_handler, pattern="^read_full_auto$"))
    app.add_handler(CallbackQueryHandler(ignore_handler, pattern="^ignore_notification$"))

    app.run_polling()