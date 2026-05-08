import os
from datetime import datetime, timezone
from dotenv import load_dotenv

load_dotenv()

# ===== TELEGRAM & BOT =====
BOT_TOKEN = os.getenv("BOT_TOKEN")
OWNER_TELEGRAM_ID = int(os.getenv("OWNER_TELEGRAM_ID", "0"))
WEBHOOK_URL = os.getenv("RENDER_WEB_SERVICE_URL", "https://smart-email-assistant-using-agentic-ai.onrender.com")
REDIRECT_URI = os.getenv("REDIRECT_URI", f"{WEBHOOK_URL}/callback")

# ===== GOOGLE & GEMINI =====
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
GEMINI_MODEL = "gemini-2.5-flash-lite"
GOOGLE_TTS_API_KEY = os.getenv("GOOGLE_TTS_API_KEY", "")  # Optional for fallback

# ===== SUPABASE =====
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
SUPABASE_SERVICE_ROLE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY")  # server-only


# ===== RENDER URL FOR OAUTH =====
RENDER_URL = os.getenv("RENDER_EXTERNAL_URL", "https://smart-email-assistant-using-agentic-ai.onrender.com")

# ===== GOOGLE OAUTH SCOPES =====
SCOPES = [
    'https://www.googleapis.com/auth/userinfo.email',
    'https://www.googleapis.com/auth/gmail.readonly',
    'https://www.googleapis.com/auth/gmail.modify',
    'openid'
]

# ===== LLM CONTEXT SETTINGS =====
MAX_CONTEXT_MESSAGES = 5  # Number of recent summaries to send to LLM
SUMMARY_GENERATION_THRESHOLD = 10  # Generate summary every 10 messages
UNDO_WINDOW_SECONDS = 4  # Time window for undo operations
MAX_ATTACHMENT_SIZE_MB = 20

# ===== VOICE & TTS SETTINGS =====
USE_LOCAL_TTS = os.getenv("USE_LOCAL_TTS", "false").lower() == "true"
LOCAL_TTS_ENGINE = "pyttsx3"  # Options: 'pyttsx3', 'gtts'

# ===== REDIS/CACHE SETTINGS =====
REDIS_URL = os.getenv("REDIS_URL", "")  # Optional for caching
CACHE_TTL_SECONDS = 3600  # Cache expires in 1 hour
AUTO_CACHE_CLEANUP_INTERVAL = 1800  # Cleanup unused cache every 30 minutes

# ===== VALIDATION =====
if not all([BOT_TOKEN, SUPABASE_URL, SUPABASE_KEY, GEMINI_API_KEY]):
    print("⚠️  WARNING: Missing critical environment variables!")
    print("Required: BOT_TOKEN, SUPABASE_URL, SUPABASE_KEY, GEMINI_API_KEY")

def get_utc_now():
    """Returns current UTC timestamp in ISO format."""
    return datetime.now(timezone.utc).isoformat()

def get_utc_date():
    """Returns current UTC date (YYYY-MM-DD)."""
    return datetime.now(timezone.utc).date()