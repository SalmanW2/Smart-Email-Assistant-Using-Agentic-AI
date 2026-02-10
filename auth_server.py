import os
import time
import requests
import threading
from flask import Flask, request
from google_auth_oauthlib.flow import Flow
from config_env import CREDENTIALS_FILE, SCOPES

app = Flask(__name__)

def get_redirect_uri():
    if os.environ.get("RENDER"):
        return "https://smart-email-assistant-using-agentic-ai.onrender.com/oauth2callback"
    return "http://localhost:10000/oauth2callback"

def get_login_link():
    if not os.path.exists(CREDENTIALS_FILE): return None
    flow = Flow.from_client_secrets_file(CREDENTIALS_FILE, scopes=SCOPES, redirect_uri=get_redirect_uri())
    auth_url, _ = flow.authorization_url(prompt='consent', access_type='offline', include_granted_scopes='true')
    return auth_url

@app.route('/')
def home():
    return "✅ Bot Server is Online!"

@app.route('/oauth2callback')
def oauth2callback():
    code = request.args.get('code')
    flow = Flow.from_client_secrets_file(CREDENTIALS_FILE, scopes=SCOPES, redirect_uri=get_redirect_uri())
    flow.fetch_token(code=code)
    with open("token.json", "w") as f:
        f.write(flow.credentials.to_json())
    return "<h1>✅ Login Success! You can close this tab.</h1>"

def keep_alive():
    url = "https://smart-email-assistant-using-agentic-ai.onrender.com"
    if not os.environ.get("RENDER"): return
    while True:
        time.sleep(300) 
        try: requests.get(url)
        except: pass

def run_flask_server():
    threading.Thread(target=keep_alive, daemon=True).start()
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)