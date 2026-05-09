import os
from dotenv import load_dotenv

load_dotenv()

class Config:
    BOT_TOKEN = os.getenv("BOT_TOKEN")
    GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
    SUPABASE_URL = os.getenv("SUPABASE_URL")
    SUPABASE_KEY = os.getenv("SUPABASE_KEY")
    REDIRECT_URI = os.getenv("REDIRECT_URI")
    RENDER_WEB_SERVICE_URL = os.getenv("RENDER_WEB_SERVICE_URL")
    FRONTEND_URL = os.getenv("FRONTEND_URL")
    PORT = int(os.getenv("PORT", 10000))
    GOOGLE_TTS_API_KEY = os.getenv("GOOGLE_TTS_API_KEY")

    # Validate required configs
    REQUIRED = ["BOT_TOKEN", "GEMINI_API_KEY", "SUPABASE_URL", "SUPABASE_KEY", "REDIRECT_URI", "RENDER_WEB_SERVICE_URL", "FRONTEND_URL"]
    for key in REQUIRED:
        if not getattr(Config, key):
            raise ValueError(f"Missing required environment variable: {key}")

config = Config()