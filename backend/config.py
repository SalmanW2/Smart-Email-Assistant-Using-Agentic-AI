from datetime import datetime
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    BOT_TOKEN: str
    OWNER_TELEGRAM_ID: int
    GEMINI_API_KEY: str
    SUPABASE_URL: str
    SUPABASE_SERVICE_ROLE_KEY: str
    REDIRECT_URI: str
    RENDER_WEB_SERVICE_URL: str
    FRONTEND_URL: str
    PORT: int = 10000
    DEBUG: bool = False
    CORS_ORIGINS: list[str] = ["*"]
    GOOGLE_TTS_API_KEY: str | None = None
    GOOGLE_OAUTH_CLIENT_ID: str | None = None
    GOOGLE_OAUTH_CLIENT_SECRET: str | None = None
    GROQ_API_KEY: str | None = None
    
    # --- MISSING VARIABLES ADDED HERE ---
    MAX_CONTEXT_MESSAGES: int = 5
    SUMMARY_GENERATION_THRESHOLD: int = 10

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    def get_utc_now(self) -> str:
        return datetime.utcnow().replace(tzinfo=None).isoformat() + "Z"

    def get_utc_date(self) -> str:
        return datetime.utcnow().strftime("%Y-%m-%d")

settings = Settings()