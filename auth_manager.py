import os
import datetime
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from google_auth_oauthlib.flow import Flow
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from telegram import Bot, InlineKeyboardButton, InlineKeyboardMarkup
from config import SCOPES, CREDENTIALS_FILE, TOKEN_FILE, BOT_TOKEN, OWNER_TELEGRAM_ID
app = FastAPI()

class AuthManager:
    def __init__(self):
        self.scopes = SCOPES
        self.creds_file = CREDENTIALS_FILE
        self.token_file = TOKEN_FILE
        self.last_login_msg_id = None # FIXED: Variable to track login message ID

    def get_login_link(self):
        """Generates the Google OAuth login link automatically."""
        flow = Flow.from_client_secrets_file(
            self.creds_file,
            scopes=self.scopes,
            redirect_uri=os.getenv("REDIRECT_URI")
        )
        auth_url, _ = flow.authorization_url(prompt='consent', access_type='offline')
        return auth_url

    def get_credentials(self):
        """Retrieves saved credentials from the token file."""
        if os.path.exists(self.token_file):
            creds = Credentials.from_authorized_user_file(self.token_file, self.scopes)
            if creds.valid:
                return creds
        return None

    def save_credentials(self, creds):
        """Saves the credentials to the token file."""
        with open(self.token_file, 'w') as f:
            f.write(creds.to_json())

auth_manager_instance = AuthManager()

@app.api_route("/", methods=["GET", "HEAD"])
def read_root():
    return {"status": "System Online"}

@app.get("/callback", response_class=HTMLResponse)
async def callback(request: Request):
    code = request.query_params.get("code")
    
    if not code:
        return "<h3>Authentication Failed: No authorization code provided.</h3>"
    
    try:
        # Rebuilding the flow here prevents RAM expiration issues on Render
        flow = Flow.from_client_secrets_file(CREDENTIALS_FILE, scopes=SCOPES, redirect_uri=os.getenv("REDIRECT_URI"))
        flow.fetch_token(code=code)
        creds = flow.credentials
        auth_manager_instance.save_credentials(creds)

        service = build('gmail', 'v1', credentials=creds)
        profile = service.users().getProfile(userId='me').execute()
        email_addr = profile.get('emailAddress')
        
        bot = Bot(token=BOT_TOKEN)
        
        # FIXED: Delete the old "Please login first!" message automatically
        if auth_manager_instance.last_login_msg_id:
            try:
                await bot.delete_message(chat_id=OWNER_TELEGRAM_ID, message_id=auth_manager_instance.last_login_msg_id)
            except Exception:
                pass
            auth_manager_instance.last_login_msg_id = None # Reset the tracker

        kb = [
            [InlineKeyboardButton("📥 Inbox", callback_data="manual_read_0"),
             InlineKeyboardButton("✍️ Compose", callback_data="menu_compose")],
            [InlineKeyboardButton("🔍 Search", callback_data="menu_search_prompt")],
            [InlineKeyboardButton("⚙️ Settings", callback_data="menu_settings")]
        ]
        
        success_text = (
            f"✅ *Logged In Successfully!*\n"
            f"Account: `{email_addr}`\n\n"
            f"🎛️ *Workspace Dashboard*\n"
            f"Select an action below or type your request."
        )
        
        await bot.send_message(chat_id=OWNER_TELEGRAM_ID, text=success_text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(kb))
        return "<h3>Authentication Successful! You can close this tab and return to Telegram.</h3>"
    except Exception as e:
        return f"<h3>Authentication Failed: {str(e)}</h3>"