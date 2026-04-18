import os
from dotenv import load_dotenv

load_dotenv()

# Telegram Config
BOT_TOKEN = os.getenv("BOT_TOKEN")
OWNER_TELEGRAM_ID = int(os.getenv("OWNER_TELEGRAM_ID", "0"))

# Gemini Config
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

# Auth Config
CREDENTIALS_FILE = "credentials.json"
TOKEN_FILE = "token.json"
# PKCE session storage
SESSION_FILE = "session_data.json"
# Unified Scope for all Gmail tools
SCOPES = ['https://mail.google.com/']
