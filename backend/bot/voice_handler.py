"""
Voice Processing Handler — Smart Email Assistant
================================================
Handles all auditory conversions including:
1. Speech-to-Text (STT) utilizing Groq Whisper API for low-latency transcription.
2. Text-to-Speech (TTS) utilizing Google Cloud TTS with an Edge-TTS fallback mechanism.
"""

import asyncio
import os
import tempfile
import uuid
import logging
import re
import httpx
from pathlib import Path
from typing import Dict, Optional
from config import settings
from db.models import db_manager

logger = logging.getLogger(__name__)

class VoiceHandler:
    def __init__(self) -> None:
        # Evaluate capabilities based on environment configurations
        self.google_available = bool(settings.GOOGLE_TTS_API_KEY)
        self.groq_available = bool(settings.GROQ_API_KEY)

    async def get_voice_status(self) -> Dict[str, bool]:
        """
        Returns the current operational status of the voice engines.
        Useful for dashboard telemetry and health checks.
        """
        return {
            "google_tts_configured": self.google_available,
            "edge_tts_available": True,
            "groq_stt_configured": self.groq_available,
        }

    # ==========================================
    # SPEECH-TO-TEXT (STT) ENGINE
    # ==========================================
    async def transcribe_voice(self, file_path: str) -> str:
        """
        Transcribes an audio file (.ogg) into text using Groq's Whisper Large V3 API.
        Executes asynchronously using httpx to prevent blocking the main server thread.
        """
        if not self.groq_available:
            logger.warning("Groq API key is missing. Speech-to-Text is unavailable.")
            raise Exception("Groq API key is not configured for Voice operations.")

        url = "https://api.groq.com/openai/v1/audio/transcriptions"
        headers = {
            "Authorization": f"Bearer {settings.GROQ_API_KEY}"
        }

        try:
            # Open the audio file in binary mode securely
            with open(file_path, "rb") as audio_file:
                files = {
                    "file": (os.path.basename(file_path), audio_file, "audio/ogg")
                }
                data = {
                    "model": "whisper-large-v3",
                    "response_format": "json"
                }

                # Asynchronous API request to Groq infrastructure
                async with httpx.AsyncClient(timeout=30.0) as client:
                    response = await client.post(url, headers=headers, files=files, data=data)
                    
                    # Raise exception for HTTP error statuses (e.g., 401, 429, 500)
                    response.raise_for_status()
                    
                    result = response.json()
                    transcribed_text = result.get("text", "").strip()
                    
                    logger.info("Successfully transcribed voice note via Groq Whisper.")
                    return transcribed_text

        except httpx.HTTPStatusError as http_err:
            logger.error(f"Groq API HTTP error occurred: {http_err.response.text}")
            raise Exception(f"Voice Transcription Failed: {http_err.response.status_code}")
        except Exception as e:
            logger.error(f"Groq Whisper transcription failed: {str(e)}")
            raise Exception("Failed to process voice audio. Please try again.")

    # ==========================================
    # TEXT-TO-SPEECH (TTS) ENGINE
    # ==========================================
    async def synthesize(self, text: str, telegram_id: Optional[int] = None, preferred_method: str = "google") -> str:
        """
        Generates speech audio from text after cleaning Markdown syntax.
        Implements a strict fallback mechanism: Google Cloud TTS -> Edge TTS.
        """
        # Strip Markdown symbols (*, _, #, `) to prevent TTS models from reading punctuation aloud
        clean_text = re.sub(r'[*_#`]', '', text)
        
        output_path = ""
        method_used = "edge_tts" # Default fallback assumption

        if preferred_method == "google" and self.google_available:
            try:
                # Attempt primary high-fidelity generation via Google Cloud
                output_path = await self._google_synthesize(clean_text)
                method_used = "google_tts"
            except Exception as e:
                logger.error(f"Google TTS failed, initiating Edge-TTS fallback: {e}")
                output_path = await self._edge_synthesize(clean_text)
        else:
            # Direct Edge-TTS execution
            output_path = await self._edge_synthesize(clean_text)

        # Log TTS token usage to the Supabase telemetry database if a valid user ID is provided
        if telegram_id:
            try:
                await db_manager.log_tts_usage(
                    telegram_id=telegram_id, 
                    method=method_used, 
                    characters_generated=len(clean_text)
                )
            except Exception as e:
                logger.error(f"Failed to log TTS telemetry: {e}")

        return output_path

    async def _google_synthesize(self, text: str) -> str:
        """
        Primary Engine: Google Cloud Text-to-Speech API.
        Provides superior pronunciation for bilingual (Roman Urdu / English) texts.
        """
        from google.cloud import texttospeech
        from google.oauth2 import service_account
        import json

        # Dynamically load Google Credentials
        raw_creds = os.environ.get("GOOGLE_CREDENTIALS_JSON", "").strip()
        if raw_creds:
            cred_dict = json.loads(raw_creds)
            credentials = service_account.Credentials.from_service_account_info(cred_dict)
        else:
            cred_path = os.path.join(os.path.dirname(__file__), "..", "credentials.json")
            credentials = service_account.Credentials.from_service_account_file(cred_path)

        client_opts = {"api_key": settings.GOOGLE_TTS_API_KEY} if settings.GOOGLE_TTS_API_KEY else None
        client = texttospeech.TextToSpeechClient(credentials=credentials, client_options=client_opts)
        
        synthesis_input = texttospeech.SynthesisInput(text=text)
        
        # 'en-IN' is optimized for regional names and mixed English/Roman-Urdu contexts
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
        """
        Fallback Engine: Microsoft Edge TTS (Free, Unlimited access).
        Utilized if Google TTS fails or limits are exceeded.
        """
        import edge_tts

        output_file = Path(tempfile.gettempdir()) / f"smart_email_voice_{uuid.uuid4().hex}.mp3"
        
        # NeerjaNeural provides excellent clarity for South Asian and standard English pronunciations
        communicate = edge_tts.Communicate(text, "en-IN-NeerjaNeural")
        await communicate.save(str(output_file))
        
        return str(output_file)

# Singleton instance initialization
voice_handler = VoiceHandler()