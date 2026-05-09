import os
from datetime import datetime, timezone
from dotenv import load_dotenv

load_dotenv()

# ===== TELEGRAM & BOT =====
BOT_TOKEN = os.getenv("BOT_TOKEN")
OWNER_TELEGRAM_ID = int(os.getenv("OWNER_TELEGRAM_ID", "0"))
WEBHOOK_URL = os.getenv("RENDER_WEB_SERVICE_URL")
REDIRECT_URI = os.getenv("REDIRECT_URI")

# ===== GOOGLE & GEMINI =====
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
GEMINI_MODEL = "gemini-2.5-flash-lite"
GOOGLE_TTS_API_KEY = os.getenv("GOOGLE_TTS_API_KEY", "")

# ===== SUPABASE =====
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

# ===== LLM CONTEXT SETTINGS =====
MAX_CONTEXT_MESSAGES = 5
SUMMARY_GENERATION_THRESHOLD = 10
UNDO_WINDOW_SECONDS = 4
MAX_ATTACHMENT_SIZE_MB = 20

# ===== VOICE & TTS SETTINGS =====
USE_LOCAL_TTS = os.getenv("USE_LOCAL_TTS", "false").lower() == "true"
LOCAL_TTS_ENGINE = "pyttsx3"

def get_utc_now():
    return datetime.now(timezone.utc).isoformat()

def get_utc_date():
    return datetime.now(timezone.utc).date()