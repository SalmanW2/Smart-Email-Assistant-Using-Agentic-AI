import os
import time
import datetime
import requests
import threading
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from google_auth_oauthlib.flow import Flow
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from telegram import Bot, InlineKeyboardButton, InlineKeyboardMarkup
from config_env import SCOPES, CREDENTIALS_FILE, TOKEN_FILE, BOT_TOKEN, OWNER_TELEGRAM_ID

app = FastAPI()

def ping_server():
    url = os.getenv("RENDER_WEB_SERVICE_URL", "http://localhost:8000")
    while True:
        time.sleep(840)
        try:
            requests.get(url)
        except Exception:
            pass

class AuthManager:
    def __init__(self):
        self.scopes = SCOPES
        self.creds_file = CREDENTIALS_FILE
        self.token_file = TOKEN_FILE
        self.active_flow = None
        threading.Thread(target=ping_server, daemon=True).start()

    def get_login_link(self):
        self.active_flow = Flow.from_client_secrets_file(
            self.creds_file,
            scopes=self.scopes,
            redirect_uri=os.getenv("REDIRECT_URI")
        )
        auth_url, _ = self.active_flow.authorization_url(prompt='consent', access_type='offline')
        return auth_url

    def get_credentials(self):
        if os.path.exists(self.token_file):
            creds = Credentials.from_authorized_user_file(self.token_file, self.scopes)
            if creds.valid:
                return creds
        return None

    def save_credentials(self, creds):
        with open(self.token_file, 'w') as f:
            f.write(creds.to_json())

auth_manager_instance = AuthManager()

@app.get("/")
def read_root():
    return {"status": "System Online"}

@app.get("/callback", response_class=HTMLResponse)
async def callback(request: Request):
    code = request.query_params.get("code")
    if not code or not auth_manager_instance.active_flow:
        return "<h3>Authentication Failed: Session expired in RAM. Restart from Telegram.</h3>"
    
    try:
        auth_manager_instance.active_flow.fetch_token(code=code)
        creds = auth_manager_instance.active_flow.credentials
        auth_manager_instance.save_credentials(creds)
        auth_manager_instance.active_flow = None 

        service = build('gmail', 'v1', credentials=creds)
        profile = service.users().getProfile(userId='me').execute()
        email_addr = profile.get('emailAddress')
        
        now = datetime.datetime.now(datetime.timezone.utc)
        dt_string = now.strftime("%B %d, %Y at %I:%M %p UTC")

        bot = Bot(token=BOT_TOKEN)
        text = f"Authentication Successful!\n\nAccount: {email_addr} has been successfully logged in on {dt_string}."
        kb = [[InlineKeyboardButton("Read Inbox", callback_data="menu_read")]]
        await bot.send_message(chat_id=OWNER_TELEGRAM_ID, text=text, reply_markup=InlineKeyboardMarkup(kb))

        return "<h3>Authentication Successful! You can return to Telegram.</h3>"
    except Exception as e:
        return f"<h3>Authentication Failed: {str(e)}</h3>"
