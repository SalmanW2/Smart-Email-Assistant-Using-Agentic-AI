import os
import threading
import logging
from flask import Flask, request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import Flow
from google.auth.transport.requests import Request
from config_env import CREDENTIALS_FILE, TOKEN_FILE, SCOPES

# Logging hide karne ke liye
log = logging.getLogger('werkzeug')
log.setLevel(logging.ERROR)

class AuthManager:
    def __init__(self):
        self.creds = None
        self.app = Flask(__name__)
        self._setup_server_routes()

    def get_credentials(self):
        """Loads token and refreshes if expired."""
        if os.path.exists(TOKEN_FILE):
            self.creds = Credentials.from_authorized_user_file(TOKEN_FILE, SCOPES)
        
        if self.creds and self.creds.expired and self.creds.refresh_token:
            try:
                self.creds.refresh(Request())
                with open(TOKEN_FILE, 'w') as token:
                    token.write(self.creds.to_json())
            except Exception as e:
                print(f"❌ Refresh Failed: {e}")
                self.creds = None
        return self.creds

    def get_login_link(self):
        """Generates OAuth 2.0 Link matching your credentials.json port."""
        if not os.path.exists(CREDENTIALS_FILE): return None
        
        # ✅ FIX: Default to Port 8080 (Matches your credentials.json)
        redirect_uri = "https://smart-email-assistant-using-agentic-ai.onrender.com/oauth2callback"
        if not os.environ.get("RENDER"):
            # Localhost ke liye 8080 use karein
            redirect_uri = "http://localhost:8080/oauth2callback"

        try:
            flow = Flow.from_client_secrets_file(CREDENTIALS_FILE, SCOPES, redirect_uri=redirect_uri)
            auth_url, _ = flow.authorization_url(prompt='consent', access_type='offline')
            return auth_url
        except Exception as e:
            print(f"❌ Error generating link: {e}")
            return None

    def _setup_server_routes(self):
        @self.app.route('/')
        def home(): return "✅ Bot Server is Online on Port 8080!"

        @self.app.route('/oauth2callback')
        def oauth2callback():
            code = request.args.get('code')
            if not code: return "❌ No code provided."
            
            # ✅ FIX: Match Redirect URI exactly
            redirect_uri = "https://smart-email-assistant-using-agentic-ai.onrender.com/oauth2callback"
            if not os.environ.get("RENDER"):
                redirect_uri = "http://localhost:8080/oauth2callback"

            try:
                flow = Flow.from_client_secrets_file(CREDENTIALS_FILE, SCOPES, redirect_uri=redirect_uri)
                flow.fetch_token(code=code)
                with open(TOKEN_FILE, "w") as f:
                    f.write(flow.credentials.to_json())
                return "<h1>✅ Login Success! You can close this tab.</h1>"
            except Exception as e:
                return f"<h1>❌ Login Failed: {str(e)}</h1>"

    def run_server(self):
        # ✅ FIX: Running on Port 8080
        port = int(os.environ.get("PORT", 8080))
        threading.Thread(target=self.app.run, kwargs={'host': '0.0.0.0', 'port': port}, daemon=True).start()