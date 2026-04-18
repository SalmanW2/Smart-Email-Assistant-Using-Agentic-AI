import os
import threading
import time
import requests
import uvicorn
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from google_auth_oauthlib.flow import Flow
from google.oauth2.credentials import Credentials

app = FastAPI()

def ping_server():
    url = os.getenv("RENDER_WEB_SERVICE_URL", "http://localhost:8000")
    while True:
        time.sleep(840) # 14 minutes
        try:
            requests.get(url)
            print("Pinged server to prevent sleep.")
        except Exception:
            pass

class AuthManager:
    def __init__(self):
        self.scopes = ['https://mail.google.com/']
        self.creds_file = 'credentials.json'
        self.token_file = 'token.json'
        self.active_flow = None  # FIX: Original flow ko save karne ke liye
        
        # Start Anti-Sleep Thread
        threading.Thread(target=ping_server, daemon=True).start()

    def get_login_link(self):
        self.active_flow = Flow.from_client_secrets_file(
            self.creds_file,
            scopes=self.scopes,
            redirect_uri=os.getenv("REDIRECT_URI", "http://localhost:8000/callback")
        )
        # Auth url generate hote waqt code_verifier ban jata hai
        auth_url, _ = self.active_flow.authorization_url(prompt='consent')
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

    def run_server(self):
        config = uvicorn.Config(app, host="0.0.0.0", port=int(os.getenv("PORT", 8080)))
        server = uvicorn.Server(config)
        threading.Thread(target=server.run, daemon=True).start()

auth_manager_instance = AuthManager()

@app.get("/")
def read_root():
    return {"status": "System Online"}

@app.get("/callback", response_class=HTMLResponse)
async def callback(request: Request):
    code = request.query_params.get("code")
    if not code:
        return "Authentication Failed: No code provided."
    
    # FIX: Naya Flow banane ke bajaye original saved Flow use karein
    if not auth_manager_instance.active_flow:
        return "<h3>Authentication Session Expired. Please type /start in Telegram again.</h3>"
    
    try:
        auth_manager_instance.active_flow.fetch_token(code=code)
        auth_manager_instance.save_credentials(auth_manager_instance.active_flow.credentials)
        auth_manager_instance.active_flow = None  # Success ke baad clear kar dein
        return "<h3>Authentication Successful! You can return to Telegram.</h3>"
    except Exception as e:
        return f"<h3>Authentication Failed: {str(e)}</h3>"
        
