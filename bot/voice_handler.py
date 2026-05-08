"""
Voice Handler - Text-to-Speech with Fallback Logic
Handles voice generation with Google TTS primary + Local TTS fallback
"""

import logging
import os
from typing import Optional, Tuple
from datetime import datetime, timedelta
from config import (
    GOOGLE_TTS_API_KEY, USE_LOCAL_TTS, LOCAL_TTS_ENGINE,
    SUPABASE_URL, SUPABASE_KEY, get_utc_now
)
from supabase import create_client

supabase = create_client(SUPABASE_URL, SUPABASE_KEY)
logger = logging.getLogger(__name__)

# Try importing Google TTS
try:
    from google.cloud import texttospeech
    GOOGLE_TTS_AVAILABLE = bool(GOOGLE_TTS_API_KEY)
except ImportError:
    GOOGLE_TTS_AVAILABLE = False
    logger.warning("Google Cloud TTS not available")

# Try importing local TTS
try:
    import pyttsx3
    LOCAL_TTS_AVAILABLE = True
except ImportError:
    LOCAL_TTS_AVAILABLE = False
    logger.warning("pyttsx3 not available")

try:
    from gtts import gTTS
    GTTS_AVAILABLE = True
except ImportError:
    GTTS_AVAILABLE = False


class TTSHandler:
    """Handles Text-to-Speech with fallback logic."""
    
    @staticmethod
    def _get_google_tts_client():
        """Initializes Google TTS client."""
        if not GOOGLE_TTS_API_KEY:
            return None
        try:
            os.environ['GOOGLE_APPLICATION_CREDENTIALS'] = GOOGLE_TTS_API_KEY
            return texttospeech.TextToSpeechClient()
        except Exception as e:
            logger.error(f"Google TTS init error: {e}")
            return None

    @staticmethod
    def _check_google_quota(telegram_id: int) -> bool:
        """Checks if Google TTS quota is available for today."""
        try:
            today = datetime.utcnow().date().isoformat()
            res = supabase.table("tts_usage").select(
                "characters_generated", count="exact"
            ).eq("telegram_id", telegram_id).eq(
                "method", "google"
            ).gte("created_at", f"{today}T00:00:00").execute()
            
            total_chars = sum([r.get("characters_generated", 0) for r in res.data]) if res.data else 0
            
            # Google free tier: 1 million chars/month (~33k/day average)
            # Conservative limit: 5000 chars/day per user
            return total_chars < 5000
        except Exception as e:
            logger.error(f"Quota check error: {e}")
            return False

    @staticmethod
    def _generate_google_tts(text: str, telegram_id: int, output_file: str) -> Tuple[bool, str]:
        """Generates voice using Google Cloud TTS."""
        try:
            if not GOOGLE_TTS_AVAILABLE or not TTSHandler._check_google_quota(telegram_id):
                return False, "Quota limit reached"
            
            client = TTSHandler._get_google_tts_client()
            if not client:
                return False, "Client init failed"
            
            input_text = texttospeech.SynthesisInput(text=text)
            voice = texttospeech.VoiceSelectionParams(
                language_code="en-US",
                ssml_gender=texttospeech.SsmlVoiceGender.NEUTRAL,
                name="en-US-Neural2-C"
            )
            audio_config = texttospeech.AudioConfig(
                audio_encoding=texttospeech.AudioEncoding.OGG_OPUS
            )
            
            response = client.synthesize_speech(
                input=input_text,
                voice=voice,
                audio_config=audio_config
            )
            
            with open(output_file, "wb") as out:
                out.write(response.audio_content)
            
            # Log usage
            supabase.table("tts_usage").insert({
                "telegram_id": telegram_id,
                "method": "google",
                "characters_generated": len(text),
                "created_at": get_utc_now()
            }).execute()
            
            logger.info(f"Google TTS generated: {len(text)} chars")
            return True, "success"
        except Exception as e:
            logger.error(f"Google TTS error: {str(e)}")
            return False, str(e)

    @staticmethod
    def _generate_local_tts_pyttsx3(text: str, telegram_id: int, output_file: str) -> Tuple[bool, str]:
        """Generates voice using local pyttsx3."""
        try:
            if not LOCAL_TTS_AVAILABLE:
                return False, "pyttsx3 not available"
            
            engine = pyttsx3.init()
            engine.setProperty('rate', 150)
            engine.setProperty('volume', 0.9)
            engine.save_to_file(text, output_file)
            engine.runAndWait()
            
            # Log usage
            supabase.table("tts_usage").insert({
                "telegram_id": telegram_id,
                "method": "local",
                "characters_generated": len(text),
                "created_at": get_utc_now()
            }).execute()
            
            logger.info(f"Local TTS (pyttsx3) generated: {len(text)} chars")
            return True, "success"
        except Exception as e:
            logger.error(f"Local TTS (pyttsx3) error: {str(e)}")
            return False, str(e)

    @staticmethod
    def _generate_local_tts_gtts(text: str, telegram_id: int, output_file: str) -> Tuple[bool, str]:
        """Generates voice using gTTS (free, no API key)."""
        try:
            if not GTTS_AVAILABLE:
                return False, "gTTS not available"
            
            tts = gTTS(text=text, lang='en', slow=False)
            # Convert MP3 to OGG or keep as MP3
            tts.save(output_file)
            
            # Log usage
            supabase.table("tts_usage").insert({
                "telegram_id": telegram_id,
                "method": "local",
                "characters_generated": len(text),
                "created_at": get_utc_now()
            }).execute()
            
            logger.info(f"Local TTS (gTTS) generated: {len(text)} chars")
            return True, "success"
        except Exception as e:
            logger.error(f"Local TTS (gTTS) error: {str(e)}")
            return False, str(e)

    @staticmethod
    def generate_voice(text: str, telegram_id: int, output_file: str = "/tmp/voice_output.ogg") -> Tuple[bool, str]:
        """
        Main TTS handler with fallback logic.
        
        1. Try Google TTS (best quality, low server load)
        2. Fallback to local TTS (pyttsx3 or gTTS)
        
        Returns: (success: bool, file_path: str or error_message: str)
        """
        
        # Validate input
        if not text or len(text.strip()) == 0:
            return False, "Empty text"
        
        if len(text) > 5000:
            text = text[:5000] + "..."  # Truncate long text
        
        logger.info(f"TTS request for user {telegram_id}: {len(text)} chars")
        
        # Try Google TTS first
        if GOOGLE_TTS_AVAILABLE:
            success, msg = TTSHandler._generate_google_tts(text, telegram_id, output_file)
            if success:
                logger.info(f"✅ Used Google TTS for user {telegram_id}")
                return True, output_file
            else:
                logger.warning(f"Google TTS failed: {msg}. Falling back to local TTS.")
        
        # Fallback to gTTS (internet-based, free)
        if GTTS_AVAILABLE:
            success, msg = TTSHandler._generate_local_tts_gtts(text, telegram_id, output_file)
            if success:
                logger.info(f"✅ Used gTTS (fallback) for user {telegram_id}")
                return True, output_file
        
        # Fallback to pyttsx3 (local, CPU intensive)
        if LOCAL_TTS_AVAILABLE:
            success, msg = TTSHandler._generate_local_tts_pyttsx3(text, telegram_id, output_file)
            if success:
                logger.info(f"✅ Used pyttsx3 (fallback) for user {telegram_id}")
                return True, output_file
        
        # All methods failed
        logger.error(f"All TTS methods failed for user {telegram_id}")
        return False, "All TTS methods failed. Please try again later."


class VoiceTranscriber:
    """Handles audio transcription using Gemini."""
    
    @staticmethod
    def transcribe_audio(file_path: str) -> str:
        """Transcribes audio file using Gemini."""
        try:
            from google import genai
            from config import GEMINI_API_KEY, GEMINI_MODEL
            
            client = genai.Client(api_key=GEMINI_API_KEY)
            
            with open(file_path, 'rb') as f:
                response = client.models.generate_content(
                    model=GEMINI_MODEL,
                    contents=[
                        genai.types.Part.from_data(
                            data=f.read(),
                            mime_type="audio/ogg"
                        ),
                        "Transcribe this audio accurately. Do not invent words if it is noisy. If the audio is completely unintelligible, just output: '[Audio Unclear]'."
                    ]
                )
            
            return response.text.strip()
        except Exception as e:
            logger.error(f"Transcription error: {e}")
            return "[Audio Unclear]"


class AttachmentQAHandler:
    """Handles attachment Q&A using Gemini Vision."""
    
    SUPPORTED_TYPES = {
        'application/pdf': 'PDF',
        'application/vnd.openxmlformats-officedocument.wordprocessingml.document': 'DOCX',
        'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet': 'XLSX',
        'image/jpeg': 'JPG',
        'image/png': 'PNG',
        'image/gif': 'GIF',
        'text/plain': 'TXT'
    }
    
    @staticmethod
    def is_supported(mime_type: str) -> bool:
        """Checks if file type is supported."""
        return mime_type in AttachmentQAHandler.SUPPORTED_TYPES or mime_type.startswith('image/')
    
    @staticmethod
    def analyze_attachment(file_path: str, question: str) -> str:
        """Analyzes attachment and answers question about it."""
        try:
            from google import genai
            from config import GEMINI_API_KEY, GEMINI_MODEL
            
            client = genai.Client(api_key=GEMINI_API_KEY)
            
            # Determine MIME type
            import mimetypes
            mime_type, _ = mimetypes.guess_type(file_path)
            
            if not mime_type:
                mime_type = 'application/octet-stream'
            
            with open(file_path, 'rb') as f:
                file_data = f.read()
            
            # Build prompt
            prompt = f"""You are a helpful document analyst. The user is asking about the attached document.

User's Question: {question}

Please analyze the document and provide a clear, concise answer. If the document is an image, describe what you see. If it's a PDF or document, extract the relevant information.

Provide the answer in 2-3 bullet points if possible."""
            
            response = client.models.generate_content(
                model=GEMINI_MODEL,
                contents=[
                    genai.types.Part.from_data(
                        data=file_data,
                        mime_type=mime_type
                    ),
                    prompt
                ]
            )
            
            return response.text.strip()
        except Exception as e:
            logger.error(f"Attachment analysis error: {e}")
            return f"❌ Could not analyze attachment: {str(e)}"