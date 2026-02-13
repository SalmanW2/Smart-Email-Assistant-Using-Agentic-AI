import os
from dotenv import load_dotenv

load_dotenv()

# Telegram Config
BOT_TOKEN = os.getenv("BOT_TOKEN")
OWNER_TELEGRAM_ID = int(os.getenv("OWNER_TELEGRAM_ID", "0"))

# Gemini Config
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

# Auth Files
CREDENTIALS_FILE = "credentials.json"
TOKEN_FILE = "token.json"
SCOPES = ["https://www.googleapis.com/auth/gmail.readonly", "https://www.googleapis.com/auth/gmail.send"]