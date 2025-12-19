import os
import json
from flask import Flask, request
from google_auth_oauthlib.flow import Flow

# --- CONFIGURATION ---
app = Flask(__name__)

# Render Secret Paths (Best Practice)
SECRETS_DIR = "/etc/secrets/"
CREDENTIALS_PATH = os.path.join(SECRETS_DIR, "credentials.json")
SCOPES = ['https://www.googleapis.com/auth/gmail.modify']

def get_credentials_path():
    """Checks if running on Render or Local PC"""
    if os.path.exists(CREDENTIALS_PATH):
        return CREDENTIALS_PATH
    elif os.path.exists("credentials.json"):
        return "credentials.json"
    return None

def get_redirect_uri():
    """Auto-detects environment to set the correct Redirect URI"""
    # Agar RENDER environment variable set hai (Cloud)
    if os.environ.get("RENDER"):
        return "https://smart-email-assistant-using-agentic-ai.onrender.com/oauth2callback"
    # Warna Localhost (PC)
    return "http://localhost:10000/oauth2callback"

@app.route('/')
def home():
    return "✅ Auth Server is Running! Go back to Telegram."

@app.route('/oauth2callback')
def oauth2callback():
    state = request.args.get('state')
    code = request.args.get('code')
    
    creds_file = get_credentials_path()
    if not creds_file:
        return "❌ Error: credentials.json missing."

    try:
        flow = Flow.from_client_secrets_file(
            creds_file,
            scopes=SCOPES,
            state=state,
            redirect_uri=get_redirect_uri()
        )
        
        flow.fetch_token(code=code)
        creds = flow.credentials
        
        # Save Token
        token_json = creds.to_json()
        with open("token.json", "w") as f:
            f.write(token_json)
            
        return "<h1>✅ Login Successful!</h1><p>You can close this tab and check Telegram.</p>"
    except Exception as e:
        return f"<h1>❌ Login Failed</h1><p>Error: {str(e)}</p>"

def run_flask_server():
    port = int(os.environ.get("PORT", 10000))
    # 'use_reloader=False' zaroori hai taake thread mein crash na ho
    app.run(host="0.0.0.0", port=port, debug=False, use_reloader=False)