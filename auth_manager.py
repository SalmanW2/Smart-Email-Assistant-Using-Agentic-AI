import os
import threading
import time
import json
import requests
import uvicorn
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from google_auth_oauthlib.flow import Flow
from google.oauth2.credentials import Credentials
from config_env import SCOPES, CREDENTIALS_FILE, TOKEN_FILE, SESSION_FILE

app = FastAPI()

def ping_server():
    url = os.getenv("RENDER_WEB_SERVICE_URL", "http://localhost:8000")
    while True:
        time.sleep(840) # 14 minutes
        try:
            requests.get(url)
            print("Pinged server to keep it awake.")
        except Exception:
            pass

class AuthManager:
    def __init__(self):
        self.scopes = SCOPES
        self.creds_file = CREDENTIALS_FILE
        self.token_file = TOKEN_FILE
        self.session_file = SESSION_FILE
        
        threading.Thread(target=ping_server, daemon=True).start()

    def get_login_link(self):
        flow = Flow.from_client_secrets_file(
            self.creds_file,
            scopes=self.scopes,
            redirect_uri=os.getenv("REDIRECT_URI", "http://localhost:8000/callback")
        )
        auth_url, _ = flow.authorization_url(prompt='consent', access_type='offline')
        
        # Save code_verifier to file (Cloud-Proof PKCE)
        with open(self.session_file, 'w') as f:
            json.dump({'code_verifier': flow.code_verifier}, f)
            
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
        port = int(os.getenv("PORT", 8080))
        config = uvicorn.Config(app, host="0.0.0.0", port=port)
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
        return "<h3>Authentication Failed: No code provided.</h3>"
    
    if not os.path.exists(auth_manager_instance.session_file):
        return "<h3>Session Expired. Please restart login from Telegram.</h3>"
    
    try:
        # Load the saved verifier
        with open(auth_manager_instance.session_file, 'r') as f:
            session_data = json.load(f)
        
        flow = Flow.from_client_secrets_file(
            auth_manager_instance.creds_file,
            scopes=auth_manager_instance.scopes,
            redirect_uri=os.getenv("REDIRECT_URI", "http://localhost:8000/callback")
        )
        # Inject the saved verifier back into the flow
        flow.code_verifier = session_data['code_verifier']
        
        flow.fetch_token(code=code)
        auth_manager_instance.save_credentials(flow.credentials)
        
        # Cleanup session file
        if os.path.exists(auth_manager_instance.session_file):
            os.remove(auth_manager_instance.session_file)
            
        return "<h3>Authentication Successful! You can return to Telegram.</h3>"
    except Exception as e:
        return f"<h3>Authentication Failed: {str(e)}</h3>"
