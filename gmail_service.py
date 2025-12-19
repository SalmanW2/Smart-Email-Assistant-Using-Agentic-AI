import os.path
import base64
import logging
from email.mime.text import MIMEText
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

# --- LOGGING ---
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# --- SCOPES ---
SCOPES = ['https://www.googleapis.com/auth/gmail.modify']

def get_credentials():
    """
    Ye function Render par '/etc/secrets/' check karega,
    aur Local PC par normal folder check karega.
    Browser open nahi karega.
    """
    creds = None
    
    # 1. Render Secret File Path (Standard Path)
    render_token_path = "/etc/secrets/token.json"
    # 2. Local File Path
    local_token_path = "token.json"

    # Check karo token kahan hai
    if os.path.exists(render_token_path):
        logger.info("✅ Found token in Render Secrets.")
        creds = Credentials.from_authorized_user_file(render_token_path, SCOPES)
    elif os.path.exists(local_token_path):
        logger.info("✅ Found token locally.")
        creds = Credentials.from_authorized_user_file(local_token_path, SCOPES)
    else:
        logger.error("❌ Token file not found! Please upload 'token.json' to Render Secret Files.")
        return None

    # Agar token mil gaya lekin valid nahi hai
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            try:
                logger.info("🔄 Token expired, refreshing...")
                creds.refresh(Request())
            except Exception as e:
                logger.error(f"❌ Token Refresh Failed: {e}")
                return None
        else:
            logger.error("❌ Token is invalid and cannot be refreshed. Please generate a new token locally.")
            return None

    return creds

def get_gmail_service():
    creds = get_credentials()
    if not creds:
        raise Exception("Authentication Failed: Token file missing or invalid.")
    return build('gmail', 'v1', credentials=creds)

def get_last_email():
    try:
        service = get_gmail_service()
        results = service.users().messages().list(userId='me', labelIds=['INBOX'], maxResults=1).execute()
        messages = results.get('messages', [])

        if not messages:
            return "📭 No new emails found."

        msg = service.users().messages().get(userId='me', id=messages[0]['id']).execute()
        payload = msg['payload']
        headers = payload['headers']

        subject = "No Subject"
        sender = "Unknown"
        
        for h in headers:
            if h['name'] == 'Subject': subject = h['value']
            if h['name'] == 'From': sender = h['value']

        snippet = msg.get('snippet', '')
        
        return f"📩 **Last Email:**\n\n👤 **From:** `{sender}`\n📌 **Subject:** `{subject}`\n📝 **Body:** {snippet}..."
    
    except Exception as e:
        logger.error(f"Error reading email: {e}")
        return f"❌ Error fetching email: {str(e)}"

def create_and_send_email(to_email, subject, body_text):
    try:
        service = get_gmail_service()
        message = MIMEText(body_text)
        message['to'] = to_email
        message['subject'] = subject
        raw_message = base64.urlsafe_b64encode(message.as_bytes()).decode()
        
        body = {'raw': raw_message}
        sent_message = service.users().messages().send(userId='me', body=body).execute()
        
        return f"Email Sent! Message ID: {sent_message['id']}"
    
    except Exception as e:
        logger.error(f"Error sending email: {e}")
        # Ye error detail mein batayega ke masla kya hai
        return f"❌ Unknown Error: {str(e)}"