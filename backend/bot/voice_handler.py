import asyncio
import os
import tempfile
import uuid
from pathlib import Path
from typing import Dict
from config import settings

class VoiceHandler:
    def __init__(self) -> None:
        self.google_available = settings.GOOGLE_TTS_API_KEY is not None

    async def synthesize(self, text: str, preferred_method: str = "google") -> str:
        """Generate speech audio and return a local file path."""
        if preferred_method == "google" and self.google_available:
            try:
                return await self._google_synthesize(text)
            except Exception:
                # Fallback to local voice generation without crashing
                return await self._edge_synthesize(text)

        return await self._edge_synthesize(text)

    async def get_voice_status(self) -> Dict[str, bool]:
        """Return voice provider availability status."""
        return {
            "google_tts_configured": self.google_available,
            "edge_tts_available": True,
        }

    async def _google_synthesize(self, text: str) -> str:
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

        response = client.synthesize_speech(
            input=synthesis_input,
            voice=voice_params,
            audio_config=audio_config,
        )

        output_file = Path(tempfile.gettempdir()) / f"smart_email_voice_{uuid.uuid4().hex}.ogg"
        output_file.write_bytes(response.audio_content)
        return str(output_file)

    async def _edge_synthesize(self, text: str) -> str:
        from edge_tts import Communicate

        output_file = Path(tempfile.gettempdir()) / f"smart_email_voice_{uuid.uuid4().hex}.ogg"
        communicate = Communicate(text, voice="en-US-AriaNeural")
        await communicate.save(str(output_file))
        return str(output_file)

voice_handler = VoiceHandler()
