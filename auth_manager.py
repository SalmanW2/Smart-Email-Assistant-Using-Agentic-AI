import os
import threading
import time
import urllib.request
import uvicorn
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import Flow
from google.auth.transport.requests import Request as GoogleAuthRequest
from config_env import CREDENTIALS_FILE, TOKEN_FILE, SCOPES

app = FastAPI()

class AuthManager:
    def __init__(self):
        self.creds = None
        self.pending_flow = None  # OAuth State yaad rakhne ke liye
        self._setup_server_routes()
        self._start_keep_awake() # Render ko jagaye rakhne wala function

    def get_credentials(self):
        if os.path.exists(TOKEN_FILE):
            self.creds = Credentials.from_authorized_user_file(TOKEN_FILE, SCOPES)
        
        if self.creds and self.creds.expired and self.creds.refresh_token:
            try:
                self.creds.refresh(GoogleAuthRequest())
                with open(TOKEN_FILE, 'w') as token:
                    token.write(self.creds.to_json())
            except Exception as e:
                print(f"❌ Refresh Failed: {e}")
                self.creds = None
        return self.creds

    def get_login_link(self):
        if not os.path.exists(CREDENTIALS_FILE): return None
        
        redirect_uri = "https://smart-email-assistant-using-agentic-ai.onrender.com/oauth2callback"
        if not os.environ.get("RENDER"):
            redirect_uri = "http://localhost:8080/oauth2callback"

        try:
            # Flow banate waqt isay memory mein save kar liya (PKCE verifier fix)
            self.pending_flow = Flow.from_client_secrets_file(CREDENTIALS_FILE, SCOPES, redirect_uri=redirect_uri)
            auth_url, _ = self.pending_flow.authorization_url(prompt='consent', access_type='offline')
            return auth_url
        except Exception as e:
            print(f"❌ Error generating link: {e}")
            return None

    def _setup_server_routes(self):
        @app.get("/", response_class=HTMLResponse)
        def home(): 
            return "✅ FastAPI Bot Server is Online & Awake!"

        @app.get("/oauth2callback", response_class=HTMLResponse)
        def oauth2callback(code: str = None):
            if not code: return "❌ No code provided."
            if not self.pending_flow: return "❌ Session expired or invalid. Please try logging in again from Telegram."

            try:
                # Wahi pending flow use kiya taake code verifier match kar jaye
                self.pending_flow.fetch_token(code=code)
                with open(TOKEN_FILE, "w") as f:
                    f.write(self.pending_flow.credentials.to_json())
                return "<h1>✅ Login Success! You can safely close this tab and return to Telegram.</h1>"
            except Exception as e:
                return f"<h1>❌ Login Failed: {str(e)}</h1>"

    def _start_keep_awake(self):
        """Render server ko har 14 minute baad ping karta hai"""
        def ping():
            while True:
                time.sleep(14 * 60) # 14 minutes
                try:
                    urllib.request.urlopen("https://smart-email-assistant-using-agentic-ai.onrender.com/")
                    print("🔄 Pinged server to keep it awake.")
                except Exception:
                    pass
        threading.Thread(target=ping, daemon=True).start()

    def run_server(self):
        port = int(os.environ.get("PORT", 8080))
        config = uvicorn.Config(app, host="0.0.0.0", port=port, log_level="error")
        server = uvicorn.Server(config)
        threading.Thread(target=server.run, daemon=True).start()
