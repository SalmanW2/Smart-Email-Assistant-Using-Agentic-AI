from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    BOT_TOKEN: str
    GEMINI_API_KEY: str
    SUPABASE_URL: str
    SUPABASE_KEY: str
    REDIRECT_URI: str
    RENDER_WEB_SERVICE_URL: str
    FRONTEND_URL: str
    PORT: int = 10000
    GOOGLE_TTS_API_KEY: str | None = None
    GOOGLE_OAUTH_CLIENT_ID: str
    GOOGLE_OAUTH_CLIENT_SECRET: str

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

settings = Settings()