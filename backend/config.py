from pydantic import BaseSettings, Field, HttpUrl, SecretStr

class Settings(BaseSettings):
    BOT_TOKEN: str = Field(..., env="BOT_TOKEN")
    GEMINI_API_KEY: str = Field(..., env="GEMINI_API_KEY")
    SUPABASE_URL: HttpUrl = Field(..., env="SUPABASE_URL")
    SUPABASE_KEY: SecretStr = Field(..., env="SUPABASE_KEY")
    REDIRECT_URI: HttpUrl = Field(..., env="REDIRECT_URI")
    RENDER_WEB_SERVICE_URL: HttpUrl = Field(..., env="RENDER_WEB_SERVICE_URL")
    FRONTEND_URL: HttpUrl = Field(..., env="FRONTEND_URL")
    PORT: int = Field(10000, env="PORT")
    GOOGLE_TTS_API_KEY: str | None = Field(None, env="GOOGLE_TTS_API_KEY")
    GOOGLE_OAUTH_CLIENT_ID: str = Field(..., env="GOOGLE_OAUTH_CLIENT_ID")
    GOOGLE_OAUTH_CLIENT_SECRET: str = Field(..., env="GOOGLE_OAUTH_CLIENT_SECRET")

    class Config:
        env_file = ".env"
        case_sensitive = True

settings = Settings()