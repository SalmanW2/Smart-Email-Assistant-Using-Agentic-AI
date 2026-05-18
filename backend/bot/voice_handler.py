import asyncio
import os
import tempfile
import uuid
import logging
from pathlib import Path
from typing import Dict, Optional
from config import settings
from db.models import db_manager

logger = logging.getLogger(__name__)

class VoiceHandler:
    def __init__(self) -> None:
        # Check if Google TTS is configured
        self.google_available = bool(settings.GOOGLE_TTS_API_KEY)

    async def get_voice_status(self) -> Dict[str, bool]:
        """Returns the current status of the voice engines."""
        return {
            "google_tts_configured": self.google_available,
            "edge_tts_available": True,
        }

    async def synthesize(self, text: str, telegram_id: Optional[int] = None, preferred_method: str = "google") -> str:
        """
        Generates speech audio and returns the local file path.
        Implements strict fallback: Google Cloud TTS -> Edge TTS.
        Logs usage to the database automatically.
        """
        output_path = ""
        method_used = "edge_tts" # Default fallback

        if preferred_method == "google" and self.google_available:
            try:
                # Attempt primary high-quality generation
                output_path = await self._google_synthesize(text)
                method_used = "google_tts"
            except Exception as e:
                logger.warning(f"Google TTS quota/error encountered. Falling back to Edge TTS: {e}")
                output_path = await self._edge_synthesize(text)
        else:
            # If Google is not preferred or not configured, use Edge TTS
            output_path = await self._edge_synthesize(text)

        # --- DB LOGGING: Track TTS Usage ---
        if telegram_id and output_path and os.path.exists(output_path):
            char_count = len(text)
            # Run in background to prevent delaying the voice message
            asyncio.create_task(db_manager.log_tts_usage(telegram_id, method_used, char_count))

        return output_path

    async def _google_synthesize(self, text: str) -> str:
        """Primary Engine: Google Cloud Text-to-Speech"""
        from google.cloud import texttospeech

        client_opts = {"api_key": settings.GOOGLE_TTS_API_KEY} if settings.GOOGLE_TTS_API_KEY else None
        client = texttospeech.TextToSpeechClient(client_options=client_opts)
        
        synthesis_input = texttospeech.SynthesisInput(text=text)
        
        # Changed to en-IN for much better Roman Urdu/Hindi pronunciation
        voice_params = texttospeech.VoiceSelectionParams(
            language_code="en-IN", 
            ssml_gender=texttospeech.SsmlVoiceGender.NEUTRAL,
        )
        audio_config = texttospeech.AudioConfig(
            audio_encoding=texttospeech.AudioEncoding.OGG_OPUS,
            speaking_rate=1.0,
        )

        response = await asyncio.to_thread(
            client.synthesize_speech,
            input=synthesis_input,
            voice=voice_params,
            audio_config=audio_config,
        )

        output_file = Path(tempfile.gettempdir()) / f"smart_email_voice_{uuid.uuid4().hex}.ogg"
        output_file.write_bytes(response.audio_content)
        return str(output_file)

    async def _edge_synthesize(self, text: str) -> str:
        """Fallback Engine: Microsoft Edge TTS (Free, Unlimited)"""
        import edge_tts

        output_file = Path(tempfile.gettempdir()) / f"smart_email_voice_{uuid.uuid4().hex}.mp3"
        # Changed to NeerjaNeural (Indian English) for clear Roman Urdu pronunciation
        communicate = edge_tts.Communicate(text, "en-IN-NeerjaNeural") 
        await communicate.save(str(output_file))
        
        return str(output_file)

# Singleton instance
voice_handler = VoiceHandler()