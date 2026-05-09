import asyncio
import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, filters, ContextTypes
from bot.ai_engine import AIEngine
from bot.contact_manager import ContactManager
from db.models import db_manager
from db.memory import memory_manager
from config import config
import uuid

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class TelegramHandler:
    def __init__(self):
        self.ai_engine = AIEngine()
        self.contact_manager = ContactManager()
        self.db = db_manager
        self.memory = memory_manager
        self.pending_actions = {}  # For undo functionality

    async def start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        user = update.effective_user
        telegram_id = user.id

        # Check if blocked
        if await self.db.is_blocked(telegram_id):
            await update.message.reply_text("You are blocked from using this service.")
            return

        # Get or create user
        db_user = await self.db.get_user(telegram_id)
        if not db_user:
            db_user = await self.db.create_user(telegram_id, user.username, user.first_name, user.last_name)

        await update.message.reply_text(
            f"Welcome {user.first_name}! I'm your Smart Email Assistant.\n\n"
            "You can chat naturally about your emails. Try:\n"
            "- 'Show me my recent emails'\n"
            "- 'Email my boss about the project'\n"
            "- 'Reply to the last email'\n\n"
            "Use /settings for preferences."
        )

    async def handle_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        user = update.effective_user
        telegram_id = user.id
        message_text = update.message.text

        # Check auth
        db_user = await self.db.get_user(telegram_id)
        if not db_user:
            await update.message.reply_text("Please start with /start")
            return

        auth_session = await self.db.get_auth_session(str(db_user["id"]))
        if not auth_session:
            login_url = f"{config.FRONTEND_URL}/login?token={uuid.uuid4()}"
            await update.message.reply_text(
                "Please connect your Gmail account first:",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Login", url=login_url)]])
            )
            return

        # Process with AI
        try:
            response, action = await self.ai_engine.process_message(str(db_user["id"]), message_text, db_user["ai_mode"])
            
            # Save to memory
            await self.memory.save_conversation_history(str(db_user["id"]), message_text, response, action)

            # Handle voice preference
            if db_user["voice_preference"] == "voice":
                await self.send_voice_response(update, response)
            else:
                await update.message.reply_text(response, parse_mode='Markdown')

            # Add undo button if action taken
            if action in ["send", "delete", "reply"]:
                action_id = str(uuid.uuid4())
                self.pending_actions[action_id] = {"user_id": str(db_user["id"]), "action": action, "timestamp": asyncio.get_event_loop().time()}
                keyboard = [[InlineKeyboardButton("Undo", callback_data=f"undo_{action_id}")]]
                await update.message.reply_text("Action completed.", reply_markup=InlineKeyboardMarkup(keyboard))

                # Auto-remove undo after 4 seconds
                asyncio.create_task(self.remove_undo(action_id, update.message.chat_id, update.message.message_id + 1))

        except Exception as e:
            logger.error(f"Error processing message: {e}")
            await update.message.reply_text("Sorry, I encountered an error. Please try again.")

    async def handle_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        query = update.callback_query
        await query.answer()

        if query.data.startswith("undo_"):
            action_id = query.data[5:]
            if action_id in self.pending_actions:
                action_data = self.pending_actions.pop(action_id)
                # Implement undo logic here
                await query.edit_message_text("Action undone.")
            else:
                await query.edit_message_text("Undo option expired.")

    async def settings(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        user = update.effective_user
        db_user = await self.db.get_user(user.id)
        if not db_user:
            await update.message.reply_text("Please start with /start")
            return

        keyboard = [
            [InlineKeyboardButton(f"AI Mode: {'ON' if db_user['ai_mode'] else 'OFF'}", callback_data="toggle_ai")],
            [InlineKeyboardButton(f"Voice: {'ON' if db_user['voice_preference'] == 'voice' else 'OFF'}", callback_data="toggle_voice")],
            [InlineKeyboardButton("Logout", callback_data="logout")]
        ]
        await update.message.reply_text("Settings:", reply_markup=InlineKeyboardMarkup(keyboard))

    async def toggle_ai(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        # Implementation for toggling AI mode
        pass  # Simplified for brevity

    async def send_voice_response(self, update: Update, text: str):
        # Implement voice synthesis with fallback
        pass  # Will implement in full

    async def remove_undo(self, action_id: str, chat_id: int, message_id: int):
        await asyncio.sleep(4)
        if action_id in self.pending_actions:
            # Edit message to remove undo button
            pass

async def setup_bot():
    application = Application.builder().token(config.BOT_TOKEN).build()

    handler = TelegramHandler()

    application.add_handler(CommandHandler("start", handler.start))
    application.add_handler(CommandHandler("settings", handler.settings))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handler.handle_message))
    application.add_handler(CallbackQueryHandler(handler.handle_callback))

    # Set webhook
    await application.bot.set_webhook(url=f"{config.RENDER_WEB_SERVICE_URL}/webhook")

    # Start polling for development (comment out for production)
    # await application.run_polling()

telegram_handler = TelegramHandler()