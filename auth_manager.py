import os
import time
import requests
import threading
from flask import Flask, request
from google_auth_oauthlib.flow import Flow

app = Flask(__name__)
SECRETS_DIR = "/etc/secrets/"
CREDENTIALS_PATH = os.path.join(SECRETS_DIR, "credentials.json")
SCOPES = ['https://www.googleapis.com/auth/gmail.modify']

def get_credentials_path():
    if os.path.exists(CREDENTIALS_PATH):
        return CREDENTIALS_PATH
    elif os.path.exists("credentials.json"):
        return "credentials.json"
    return None

def get_redirect_uri():
    if os.environ.get("RENDER"):
        return "https://smart-email-assistant-using-agentic-ai.onrender.com/oauth2callback"
    return "http://localhost:10000/oauth2callback"

def get_login_link():
    """Generates the Google Login Link"""
    creds_file = get_credentials_path()
    if not creds_file: return None
    
    try:
        flow = Flow.from_client_secrets_file(
            creds_file,
            scopes=SCOPES,
            redirect_uri=get_redirect_uri()
        )
        auth_url, _ = flow.authorization_url(prompt='consent')
        return auth_url
    except Exception as e:
        print(f"Error generating link: {e}")
        return None

def keep_alive():
    url = "https://smart-email-assistant-using-agentic-ai.onrender.com"
    if not os.environ.get("RENDER"):
        print("🏠 Running Locally - Self Ping Disabled.")
        return
    print(f"⏰ Self-Ping started for: {url}")
    while True:
        time.sleep(300)
        try:
            requests.get(url)
        except:
            pass

@app.route('/')
def home():
    return "✅ Auth Server is Running & Keeping Itself Alive!"

@app.route('/oauth2callback')
def oauth2callback():
    state = request.args.get('state')
    code = request.args.get('code')
    creds_file = get_credentials_path()
    try:
        flow = Flow.from_client_secrets_file(
            creds_file, scopes=SCOPES, state=state, redirect_uri=get_redirect_uri()
        )
        flow.fetch_token(code=code)
        with open("token.json", "w") as f:
            f.write(flow.credentials.to_json())
        return "<h1>✅ Login Successful!</h1><p>You can close this tab.</p>"
    except Exception as e:
        return f"<h1>❌ Login Failed</h1><p>Error: {str(e)}</p>"

def run_flask_server():
    port = int(os.environ.get("PORT", 10000))
    threading.Thread(target=keep_alive, daemon=True).start()
    app.run(host="0.0.0.0", port=port, debug=False, use_reloader=False)