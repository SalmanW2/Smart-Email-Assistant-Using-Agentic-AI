import os
from dotenv import load_dotenv

load_dotenv()

# Telegram & Gemini Config
BOT_TOKEN = os.getenv("BOT_TOKEN")
OWNER_TELEGRAM_ID = int(os.getenv("OWNER_TELEGRAM_ID", "0"))
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

# Gmail Configuration
SCOPES = ['https://www.googleapis.com/auth/gmail.modify']
CREDENTIALS_FILE = "credentials.json"
TOKEN_FILE = "token.json"