"""
Voice Processing Handler — Smart Email Assistant
================================================
Handles all auditory conversions including:
1. Speech-to-Text (STT) utilizing Groq Whisper API for low-latency transcription.
2. Text-to-Speech (TTS) utilizing Google Cloud TTS with an Edge-TTS fallback mechanism.
3. Dynamic Language Interceptor: Auto-detects Punjabi, Urdu, and Hindi scripts to route to native voice models.
4. Supabase Telemetry Integration: Fully synced with standard db.run lambda structures.
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

    def _detect_language(self, text: str) -> str:
        """
        Language Detection Interceptor:
        Analyzes text characters using Unicode ranges to detect regional scripts.
        Returns a language code for precise TTS model routing.
        """
        # Detect Gurmukhi (Punjabi) Script
        if re.search(r'[\u0A00-\u0A7F]', text):
            return 'pa'
        # Detect Arabic/Urdu Script
        elif re.search(r'[\u0600-\u06FF]', text):
            return 'ur'
        # Detect Devanagari (Hindi) Script
        elif re.search(r'[\u0900-\u097F]', text):
            return 'hi'
        
        # Default to English (also handles Roman Urdu/Roman Punjabi gracefully)
        return 'en'

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
        
        # Intercept and detect language natively
        detected_lang = self._detect_language(clean_text)
        
        output_path = ""
        method_used = "edge_tts" # Default fallback assumption

        if preferred_method == "google" and self.google_available:
            try:
                # Attempt primary high-fidelity generation via Google Cloud
                output_path = await self._google_synthesize(clean_text, detected_lang)
                method_used = "google_tts"
            except Exception as e:
                logger.error(f"Google TTS failed, initiating Edge-TTS fallback: {e}")
                output_path = await self._edge_synthesize(clean_text, detected_lang)
        else:
            # Direct Edge-TTS execution
            output_path = await self._edge_synthesize(clean_text, detected_lang)

        # Log TTS token usage to the Supabase telemetry database using robust synchronous lambda wrapper
        if telegram_id:
            try:
                await db_manager.db.run(lambda: db_manager.db.client.table("tts_usage").insert({
                    "telegram_id": telegram_id,
                    "method": method_used,
                    "characters_generated": len(clean_text)
                }).execute())
            except Exception as e:
                logger.error(f"Failed to log TTS telemetry metrics to database: {e}")

        return output_path

    async def _google_synthesize(self, text: str, lang_code: str) -> str:
        """
        Primary Engine: Google Cloud Text-to-Speech API.
        Applies dynamic language mapping for precise regional accents.
        """
        from google.cloud import texttospeech
        import json

        # Build credentials from multiple sources with graceful fallback
        credentials = None
        raw_creds = os.environ.get("GOOGLE_CREDENTIALS_JSON", "").strip()
        if raw_creds:
            from google.oauth2 import service_account
            cred_dict = json.loads(raw_creds)
            credentials = service_account.Credentials.from_service_account_info(cred_dict)
        else:
            cred_path = os.path.join(os.path.dirname(__file__), "..", "credentials.json")
            if os.path.exists(cred_path):
                from google.oauth2 import service_account
                credentials = service_account.Credentials.from_service_account_file(cred_path)

        # Build client — works with credentials OR API key alone
        client_opts = {"api_key": settings.GOOGLE_TTS_API_KEY} if settings.GOOGLE_TTS_API_KEY else None
        if credentials:
            client = texttospeech.TextToSpeechClient(credentials=credentials, client_options=client_opts)
        elif client_opts:
            client = texttospeech.TextToSpeechClient(client_options=client_opts)
        else:
            raise Exception("No Google TTS credentials or API key configured.")
        
        synthesis_input = texttospeech.SynthesisInput(text=text)
        
        # Dynamic locale mapping for Google TTS
        google_voice_map = {
            'pa': 'pa-IN', # Punjabi
            'ur': 'ur-PK', # Urdu
            'hi': 'hi-IN', # Hindi
            'en': 'en-IN'  # English / Roman Urdu optimized accent
        }
        target_lang = google_voice_map.get(lang_code, 'en-IN')

        voice_params = texttospeech.VoiceSelectionParams(
            language_code=target_lang, 
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
    def _convert_mp3_to_ogg(self, mp3_path: str) -> str:
        import subprocess
        ogg_path = mp3_path.replace(".mp3", ".ogg")
        try:
            # Check if ffmpeg is available
            subprocess.run(["ffmpeg", "-version"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
            # Convert mp3 to ogg (opus)
            subprocess.run(["ffmpeg", "-i", mp3_path, "-acodec", "libopus", "-b:a", "64k", ogg_path, "-y"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
            if os.path.exists(ogg_path):
                try: os.remove(mp3_path)
                except Exception: pass
                return ogg_path
        except Exception as e:
            logger.warning(f"FFmpeg conversion failed or ffmpeg not found: {e}")
        return mp3_path

    async def _edge_synthesize(self, text: str, lang_code: str) -> str:
        """
        Fallback Engine: Microsoft Edge TTS (Free, Unlimited access).
        Dynamically applies regional neural voices (Punjabi, Urdu, Hindi) based on detected scripts.
        """
        import edge_tts

        output_file = Path(tempfile.gettempdir()) / f"smart_email_voice_{uuid.uuid4().hex}.mp3"
        
        # Dynamic locale mapping for Edge-TTS Neural Voices
        edge_voice_map = {
            'pa': 'pa-IN-AmandeepNeural', # Punjabi native voice
            'ur': 'ur-PK-AsadNeural',     # Urdu native voice
            'hi': 'hi-IN-SwaraNeural',    # Hindi native voice
            'en': 'en-IN-NeerjaNeural'    # English/Roman Urdu (Excellent South Asian clarity)
        }
        target_voice = edge_voice_map.get(lang_code, 'en-IN-NeerjaNeural')
        
        communicate = edge_tts.Communicate(text, target_voice)
        await communicate.save(str(output_file))
        return self._convert_mp3_to_ogg(str(output_file))

# Singleton instance initialization
voice_handler = VoiceHandler()