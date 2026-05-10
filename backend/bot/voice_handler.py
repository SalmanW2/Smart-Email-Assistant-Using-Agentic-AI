import asyncio
import os
import tempfile
import uuid
import logging
from pathlib import Path
from typing import Dict
from config import settings

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

    async def synthesize(self, text: str, preferred_method: str = "google") -> str:
        """
        Generates speech audio and returns the local file path.
        Implements strict fallback: Google Cloud TTS -> Edge TTS.
        """
        if preferred_method == "google" and self.google_available:
            try:
                # Attempt primary high-quality generation
                return await self._google_synthesize(text)
            except Exception as e:
                logger.warning(f"Google TTS quota/error encountered. Falling back to Edge TTS: {e}")
                # Fallback to Edge TTS automatically on failure
                return await self._edge_synthesize(text)
        
        # If Google is not preferred or not configured, use Edge TTS
        return await self._edge_synthesize(text)

    async def _google_synthesize(self, text: str) -> str:
        """Primary Engine: Google Cloud Text-to-Speech"""
        from google.cloud import texttospeech

        client = texttospeech.TextToSpeechClient()
        synthesis_input = texttospeech.SynthesisInput(text=text)
        voice_params = texttospeech.VoiceSelectionParams(
            language_code="en-US",
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
        communicate = edge_tts.Communicate(text, "en-US-AriaNeural")
        await communicate.save(str(output_file))
        
        return str(output_file)

# Singleton instance
voice_handler = VoiceHandler()