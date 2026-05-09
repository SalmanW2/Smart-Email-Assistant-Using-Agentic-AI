import os
import time
import asyncio
import tempfile
import pyttsx3
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, CallbackQueryHandler, MessageHandler, filters, ContextTypes
from google.cloud import texttospeech
from db.models import DBManager
from db.memory import MemoryManager
from bot.ai_engine import AI_Engine
from bot.gmail_client import GmailClient
from config import BOT_TOKEN, GOOGLE_TTS_API_KEY, UNDO_WINDOW_SECONDS

FRONTEND_URL = os.getenv("FRONTEND_URL", "http://localhost:5173")

async def generate_voice_file(text: str) -> str:
    """TTS Fallback Logic: Tries Google, falls back to local Pyttsx3."""
    temp_file = tempfile.NamedTemporaryFile(delete=False, suffix=".ogg")
    if GOOGLE_TTS_API_KEY:
        try:
            client = texttospeech.TextToSpeechClient(client_options={"api_key": GOOGLE_TTS_API_KEY})
            synthesis_input = texttospeech.SynthesisInput(text=text)
            voice = texttospeech.VoiceSelectionParams(language_code="en-US", name="en-US-Journey-F")
            audio_config = texttospeech.AudioConfig(audio_encoding=texttospeech.AudioEncoding.OGG_OPUS)
            response = client.synthesize_speech(input=synthesis_input, voice=voice, audio_config=audio_config)
            with open(temp_file.name, "wb") as out:
                out.write(response.audio_content)
            return temp_file.name
        except Exception as e:
            print(f"Google TTS Error: {e}. Falling back to local.")

    try:
        engine = pyttsx3.init()
        engine.save_to_file(text, temp_file.name)
        engine.runAndWait()
        return temp_file.name
    except: return None

class BotHandler:
    def __init__(self):
        self.gmail = GmailClient()
        self.ai = AI_Engine(self.gmail)
        self.ptb_app = ApplicationBuilder().token(BOT_TOKEN).build()
        self._register_handlers()

    def _register_handlers(self):
        self.ptb_app.add_handler(CommandHandler("start", self.start))
        self.ptb_app.add_handler(CommandHandler("settings", self.settings))
        self.ptb_app.add_handler(CallbackQueryHandler(self.handle_button_actions))
        self.ptb_app.add_handler(MessageHandler(filters.VOICE, self.handle_voice))
        self.ptb_app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, self.handle_text))

    async def request_login(self, update: Update, user_id: int):
        secure_token = DBManager.create_auth_session(user_id)
        login_url = f"{FRONTEND_URL}/login?token={secure_token}"
        kb = [[InlineKeyboardButton("🔗 Connect Securely", url=login_url)]]
        text = "⚠️ *Authorization Required*\nPlease connect your Google Account securely to proceed."
        
        if update.callback_query:
            await update.callback_query.edit_message_text(text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(kb))
        elif update.message:
            await update.message.reply_text(text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(kb))

    async def start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        user = update.effective_user
        DBManager.create_or_update_user(user.id, username=user.username, first_name=user.first_name)
        
        if not self.gmail.get_service(user.id):
            await self.request_login(update, user.id)
            return

        text = f"Welcome back {user.first_name}! 🤖✉️\nYour inbox is connected. How can I help you today?"
        await update.message.reply_text(text)

    async def settings(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        keyboard = [
            [InlineKeyboardButton("🧠 Toggle AI Mode", callback_data="toggle_ai")],
            [InlineKeyboardButton("🚪 Logout", callback_data="action_logout")]
        ]
        await update.message.reply_text("⚙️ **Settings Dashboard**", reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")

    async def handle_button_actions(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        query = update.callback_query
        user_id = update.effective_user.id
        await query.answer()
        data = query.data

        if data == "confirm_send_ai":
            keyboard = [[InlineKeyboardButton("↩️ UNDO (4s)", callback_data="undosend_ai")]]
            msg = await query.edit_message_text("⏳ Email queued for sending...", reply_markup=InlineKeyboardMarkup(keyboard))
            
            async def process_ai_send():
                await asyncio.sleep(UNDO_WINDOW_SECONDS)
                if user_id in self.gmail.pending_ai_sends:
                    draft = self.gmail.pending_ai_sends.pop(user_id)
                    res = await asyncio.to_thread(self.gmail.send_email, user_id, draft['to'], draft['subj'], draft['body'])
                    try:
                        await msg.edit_text(res)
                    except: pass
            asyncio.create_task(process_ai_send())
            
        elif data == "undosend_ai":
            if user_id in self.gmail.pending_ai_sends:
                self.gmail.pending_ai_sends.pop(user_id)
            await query.edit_message_text("❌ Action Undone. Email not sent.")

        elif data == "toggle_ai":
            prefs = DBManager.get_user_preferences(user_id)
            new_state = not prefs.get('ai_mode_enabled', True)
            DBManager.update_preferences(user_id, ai_mode_enabled=new_state)
            await query.edit_message_text(f"🧠 AI Mode is now **{'ON' if new_state else 'OFF'}**.", parse_mode="Markdown")
            
        elif data == "action_logout":
            DBManager.create_or_update_user(user_id, auth_token=None)
            await query.edit_message_text("✅ Logged out successfully. Send /start to reconnect.")

    async def handle_text(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        user_id = update.effective_user.id
        if not self.gmail.get_service(user_id):
            await self.request_login(update, user_id)
            return

        text = update.message.text
        DBManager.update_activity(user_id)
        MemoryManager.add_interaction(user_id, text, "", "text")

        msg_obj = await update.message.reply_text("⏳ Processing...")
        res = await asyncio.to_thread(self.ai.agent_chat, text, user_id)
        
        # Trigger background summary task
        asyncio.create_task(asyncio.to_thread(self.ai.generate_summary, user_id))

        kb = []
        if user_id in self.gmail.pending_ai_sends:
            kb.append([InlineKeyboardButton("✅ Confirm & Send", callback_data="confirm_send_ai"),
                       InlineKeyboardButton("❌ Cancel", callback_data="undosend_ai")])

        await msg_obj.edit_text(res, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(kb) if kb else None)

    async def handle_voice(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        user_id = update.effective_user.id
        if not self.gmail.get_service(user_id):
            await self.request_login(update, user_id)
            return

        msg = await update.message.reply_text("🎙️ Processing voice note...")
        try:
            file = await context.bot.get_file(update.message.voice.file_id)
            file_path = f"/tmp/voice_{int(time.time())}.ogg"
            await file.download_to_drive(file_path)
            
            transcribed_text = await asyncio.to_thread(self.ai.transcribe_audio, file_path)
            if os.path.exists(file_path): os.remove(file_path)

            if transcribed_text.startswith("System Error:") or "[Audio Unclear]" in transcribed_text:
                await msg.edit_text("⚠️ *Transcription Error:*\nThe audio was unclear. Please repeat.", parse_mode="Markdown")
                return

            await msg.edit_text(f"🗣️ *You said:* {transcribed_text}\n\n⏳ Processing AI response...", parse_mode="Markdown")
            res = await asyncio.to_thread(self.ai.agent_chat, transcribed_text, user_id)
            
            kb = []
            if user_id in self.gmail.pending_ai_sends:
                kb.append([InlineKeyboardButton("✅ Confirm & Send", callback_data="confirm_send_ai"),
                           InlineKeyboardButton("❌ Cancel", callback_data="undosend_ai")])

            await msg.edit_text(res, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(kb) if kb else None)
            
            # Voice Fallback execution (only if user prefers voice)
            prefs = DBManager.get_user_preferences(user_id)
            if prefs.get('voice_preference') in ['voice', 'both']:
                voice_path = await generate_voice_file(res)
                if voice_path:
                    with open(voice_path, 'rb') as f:
                        await context.bot.send_voice(chat_id=user_id, voice=f)
                    os.remove(voice_path)

        except Exception as e:
            await msg.edit_text(f"❌ Voice processing error: {str(e)}")

# Create the instance expected by main.py
bot_handler_instance = BotHandler()