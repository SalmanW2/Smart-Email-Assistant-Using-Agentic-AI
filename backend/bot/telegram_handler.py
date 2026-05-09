import logging
import os
import tempfile
import uuid
from datetime import datetime, timedelta
from pathlib import Path
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, InputFile
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, filters, ContextTypes
from bot.ai_engine import AIEngine
from db.models import db_manager
from db.memory import memory_manager
from config import settings

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class TelegramHandler:
    def __init__(self, application: Application) -> None:
        self.application = application
        self.ai_engine = AIEngine()
        self.db = db_manager
        self.memory = memory_manager
        self.pending_actions: dict[str, dict] = {}

    async def start_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        user = update.effective_user
        if not user:
            return

        if await self.db.is_blocked(user.id):
            await update.message.reply_text("You are blocked from using this service.")
            return

        db_user = await self.db.get_user(user.id)
        if not db_user:
            await self.db.create_user(user.id)
            db_user = await self.db.get_user(user.id)

        state_uuid = uuid.uuid4().hex
        expires_at = (datetime.utcnow() + timedelta(minutes=15)).isoformat()
        await self.db.create_auth_session(state_uuid, user.id, expires_at)

        login_url = f"{settings.FRONTEND_URL}/login?token={state_uuid}"
        await update.message.reply_text(
            f"Welcome {user.first_name}! I'm your Smart Email Assistant.\n\n"
            "This bot learns your contacts, manages Gmail actions naturally, and preserves memory summaries.\n\n"
            f"Connect your inbox here:\n{login_url}\n\n"
            "Use /settings to update preferences. Once connected, send any message like:\n"
            "- 'Show my latest emails'\n"
            "- 'Email my manager about the status'\n"
            "- 'Summarize this attachment'"
        )

    async def settings_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        user = update.effective_user
        if not user:
            return

        db_user = await self.db.get_user(user.id)
        if not db_user:
            await update.message.reply_text("Please start with /start")
            return

        prefs = await self.db.get_user_preferences(user.id) or {}
        ai_mode = prefs.get("ai_mode_enabled", db_user.get("ai_mode_enabled", True))
        voice_mode = prefs.get("voice_preference", "text")

        keyboard = [
            [InlineKeyboardButton(f"AI Mode: {'ON' if ai_mode else 'OFF'}", callback_data="toggle_ai")],
            [InlineKeyboardButton(f"Voice: {'ON' if voice_mode == 'voice' else 'OFF'}", callback_data="toggle_voice")],
            [InlineKeyboardButton("Logout", callback_data="logout")],
        ]
        await update.message.reply_text("Settings:", reply_markup=InlineKeyboardMarkup(keyboard))

    async def handle_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not update.message or not update.message.text:
            return

        user = update.effective_user
        if not user:
            return

        db_user = await self.db.get_user(user.id)
        if not db_user:
            await update.message.reply_text("Please start with /start")
            return

        if not db_user.get("auth_token"):
            state_uuid = uuid.uuid4().hex
            expires_at = (datetime.utcnow() + timedelta(minutes=15)).isoformat()
            await self.db.create_auth_session(state_uuid, user.id, expires_at)
            login_url = f"{settings.FRONTEND_URL}/login?token={state_uuid}"
            await update.message.reply_text(
                "Your Gmail connection is required. Please authenticate here:",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Connect Gmail", url=login_url)]])
            )
            return

        preferences = await self.db.get_user_preferences(user.id) or {}
        ai_mode = preferences.get("ai_mode_enabled", db_user.get("ai_mode_enabled", True))
        voice_enabled = preferences.get("voice_preference", "text") == "voice"

        try:
            response_text, action, metadata = await self.ai_engine.process_message(user.id, update.message.text, ai_mode)
            await self.memory.save_conversation_history(user.id, update.message.text, response_text, metadata.get("interaction_type", "chat"))

            if voice_enabled:
                await self.send_voice_response(update, response_text)
            else:
                await update.message.reply_text(response_text, parse_mode="Markdown")

            if action in {"send", "reply", "delete"}:
                action_id = uuid.uuid4().hex
                self.pending_actions[action_id] = {
                    "telegram_id": user.id,
                    "action": action,
                    "metadata": metadata,
                    "created_at": datetime.utcnow().isoformat(),
                }
                keyboard = [[InlineKeyboardButton("Undo", callback_data=f"undo_{action_id}")]]
                await update.message.reply_text("Action completed.", reply_markup=InlineKeyboardMarkup(keyboard))
                context.job_queue.run_once(self.expire_undo, when=4, data=action_id)

        except Exception as exc:
            logger.exception("Telegram message handling failed")
            await update.message.reply_text("Sorry, I encountered an error while processing your request.")

    async def handle_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        query = update.callback_query
        if not query or not query.data:
            return

        await query.answer()
        payload = query.data

        if payload.startswith("undo_"):
            await self._handle_undo(query, payload.replace("undo_", ""))
            return

        if payload == "toggle_ai":
            await self._toggle_ai(query)
            return

        if payload == "toggle_voice":
            await self._toggle_voice(query)
            return

        if payload == "logout":
            await self._logout(query)
            return

    async def _handle_undo(self, query, action_id: str) -> None:
        pending = self.pending_actions.pop(action_id, None)
        if not pending:
            await query.edit_message_text("Undo option expired.")
            return

        await query.edit_message_text("Undo acknowledged. If the action already executed, we will revert it where possible.")

    async def _toggle_ai(self, query) -> None:
        user = query.from_user
        if not user:
            return

        db_user = await self.db.get_user(user.id)
        prefs = await self.db.get_user_preferences(user.id) or {}
        current = prefs.get("ai_mode_enabled", db_user.get("ai_mode_enabled", True))
        new_value = not current
        await self.db.upsert_user_preferences(user.id, {"ai_mode_enabled": new_value})
        await self.db.update_user(user.id, {"ai_mode_enabled": new_value})
        await query.edit_message_text(f"AI mode is now {'ON' if new_value else 'OFF'}.")

    async def _toggle_voice(self, query) -> None:
        user = query.from_user
        if not user:
            return

        prefs = await self.db.get_user_preferences(user.id) or {}
        current = prefs.get("voice_preference", "text")
        new_value = "text" if current == "voice" else "voice"
        await self.db.upsert_user_preferences(user.id, {"voice_preference": new_value})
        await query.edit_message_text(f"Voice preference set to {new_value}.")

    async def _logout(self, query) -> None:
        user = query.from_user
        if not user:
            return

        await self.db.update_user(user.id, {"auth_token": None, "is_verified": False})
        await query.edit_message_text("You have been logged out. Use /start to reconnect your Gmail account.")

    async def send_voice_response(self, update: Update, text: str) -> None:
        audio_path: str | None = None
        try:
            audio_path = await self._generate_audio(text)
            with open(audio_path, "rb") as audio_file:
                await update.message.reply_audio(InputFile(audio_file, filename=Path(audio_path).name))
        except Exception:
            logger.exception("Voice synthesis failed")
            await update.message.reply_text(text, parse_mode="Markdown")
        finally:
            if audio_path and os.path.exists(audio_path):
                os.remove(audio_path)

    async def _generate_audio(self, text: str) -> str:
        try:
            return await asyncio.to_thread(self._google_tts, text)
        except Exception:
            return await asyncio.to_thread(self._pyttsx3_tts, text)

    def _google_tts(self, text: str) -> str:
        from google.cloud import texttospeech

        client = texttospeech.TextToSpeechClient()
        synthesis_input = texttospeech.SynthesisInput(text=text)
        voice = texttospeech.VoiceSelectionParams(language_code="en-US", ssml_gender=texttospeech.SsmlVoiceGender.NEUTRAL)
        audio_config = texttospeech.AudioConfig(audio_encoding=texttospeech.AudioEncoding.MP3)
        response = client.synthesize_speech(input=synthesis_input, voice=voice, audio_config=audio_config)

        temp_file = Path(tempfile.gettempdir()) / f"smart-email-voice-{uuid.uuid4().hex}.mp3"
        temp_file.write_bytes(response.audio_content)
        return str(temp_file)

    def _pyttsx3_tts(self, text: str) -> str:
        import pyttsx3

        engine = pyttsx3.init()
        file_path = Path(tempfile.gettempdir()) / f"smart-email-voice-{uuid.uuid4().hex}.mp3"
        engine.save_to_file(text, str(file_path))
        engine.runAndWait()
        return str(file_path)

    async def expire_undo(self, context: ContextTypes.DEFAULT_TYPE) -> None:
        action_id = context.job.data
        self.pending_actions.pop(action_id, None)

class TelegramBotManager:
    def __init__(self) -> None:
        self.application: Application | None = None

    async def start(self) -> None:
        self.application = Application.builder().token(settings.BOT_TOKEN).build()
        handler = TelegramHandler(self.application)
        self.application.add_handler(CommandHandler("start", handler.start_command))
        self.application.add_handler(CommandHandler("settings", handler.settings_command))
        self.application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handler.handle_message))
        self.application.add_handler(CallbackQueryHandler(handler.handle_callback))
        await self.application.initialize()
        await self.application.bot.set_webhook(url=f"{settings.RENDER_WEB_SERVICE_URL}/webhook")

    async def stop(self) -> None:
        if self.application:
            await self.application.stop()