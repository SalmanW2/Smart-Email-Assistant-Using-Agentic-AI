from datetime import datetime
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    BOT_TOKEN: str
    OWNER_TELEGRAM_ID: int | None = None
    GEMINI_API_KEY: str
    SUPABASE_URL: str
    SUPABASE_SERVICE_ROLE_KEY: str
    REDIRECT_URI: str
    PORT: int = 10000
    DEBUG: bool = False
    
    # --- DIGITALOCEAN DEPLOYMENT URL ---
    APP_URL: str | None = None

    @property
    def CORS_ORIGINS(self) -> list[str]:
        origins = ["http://localhost:5173", "http://127.0.0.1:5173", "http://localhost:3000"]
        if self.APP_URL:
            origins.append(self.APP_URL.rstrip("/"))
        return origins

    @property
    def FRONTEND_URL(self) -> str:
        return self.APP_URL.rstrip("/") if self.APP_URL else "http://localhost:5173"

    GOOGLE_TTS_API_KEY: str | None = None
    GOOGLE_OAUTH_CLIENT_ID: str | None = None
    GOOGLE_OAUTH_CLIENT_SECRET: str | None = None
    GROQ_API_KEY: str | None = None
    
    # --- ADDITIONAL ENVIRONMENT VARIABLES ---
    WEBHOOK_URL: str | None = None
    SUPABASE_KEY: str | None = None
    GOOGLE_CREDENTIALS_JSON: str | None = None
    
    MAX_CONTEXT_MESSAGES: int = 5
    SUMMARY_GENERATION_THRESHOLD: int = 10
    GEMINI_MODEL: str = "gemini-2.5-flash"
    
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    def get_utc_now(self) -> str:
        return datetime.utcnow().replace(tzinfo=None).isoformat() + "Z"

    def get_utc_date(self) -> str:
        return datetime.utcnow().strftime("%Y-%m-%d")

settings = Settings()