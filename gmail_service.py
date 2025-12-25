import os
import base64
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
import logging

# Setup Logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

SCOPES = ['https://www.googleapis.com/auth/gmail.modify']
TOKEN_FILE = 'token.json'

def get_credentials():
    creds = None
    if os.path.exists(TOKEN_FILE):
        creds = Credentials.from_authorized_user_file(TOKEN_FILE, SCOPES)
    return creds

def get_service():
    creds = get_credentials()
    if creds and creds.valid:
        return build('gmail', 'v1', credentials=creds)
    return None

def get_latest_message_id():
    """Sirf Latest Email ki ID lata hai (Fast check ke liye)"""
    service = get_service()
    if not service: return None
    try:
        results = service.users().messages().list(userId='me', maxResults=1).execute()
        messages = results.get('messages', [])
        if not messages: return None
        return messages[0]['id']
    except Exception as e:
        logger.error(f"Error fetching ID: {e}")
        return None

# --- NEW: BODY DECODER FUNCTION 🕵️‍♂️ ---
def parse_email_body(payload):
    """
    Ye function email ke andar ghus kar 'text/plain' body dhoondta hai.
    """
    body = ""
    if 'parts' in payload:
        for part in payload['parts']:
            if part['mimeType'] == 'text/plain':
                data = part['body'].get('data')
                if data:
                    body = base64.urlsafe_b64decode(data).decode()
                    return body
            # Agar nested parts hain (multipart/alternative)
            if 'parts' in part:
                return parse_email_body(part)
    elif 'body' in payload:
        data = payload['body'].get('data')
        if data:
            body = base64.urlsafe_b64decode(data).decode()
    return body

def get_email_details(msg_id):
    """Email ki poori details (Sender, Subject, Full Body) lata hai"""
    service = get_service()
    if not service: return None
    
    try:
        msg = service.users().messages().get(userId='me', id=msg_id, format='full').execute()
        payload = msg['payload']
        headers = payload.get('headers', [])

        subject = "No Subject"
        sender = "Unknown"
        
        for h in headers:
            if h['name'] == 'Subject': subject = h['value']
            if h['name'] == 'From': sender = h['value']

        # Snippet (Preview)
        snippet = msg.get('snippet', '')

        # Full Body Extraction
        full_body = parse_email_body(payload)
        
        # Agar full body na mile to snippet use kar lo
        if not full_body:
            full_body = snippet

        # Sender Name Safai
        sender_view = sender.split("<")[0].strip().replace('"', '')

        return {
            'id': msg_id,
            'sender_email': sender,     # Reply ke liye (with <email>)
            'sender_view': sender_view, # Dikhane ke liye (Name only)
            'subject': subject,
            'snippet': snippet,         # Notification ke liye
            'body': full_body           # AI Summary ke liye (FULL TEXT)
        }
    except Exception as e:
        logger.error(f"Error fetching details: {e}")
        return None

def get_last_email(query=None):
    """Telegram command ke liye text format banata hai"""
    # (Ye function abhi use nahi ho raha naye logic mein, but rakh lo crash na ho)
    msg_id = get_latest_message_id()
    if not msg_id: return None
    details = get_email_details(msg_id)
    if not details: return None
    
    return (
        f"📩 **Latest Email**\n\n"
        f"👤 **From:** `{details['sender_view']}`\n"
        f"📌 **Subject:** `{details['subject']}`\n\n"
        f"{details['body'][:500]}..." # Sirf 500 chars dikhao
    )

def create_and_send_email(to, subject, body_text):
    service = get_service()
    if not service: return "⚠️ Auth Error: Login required."
    
    try:
        message = MIMEText(body_text)
        message['to'] = to
        message['subject'] = subject
        raw_message = base64.urlsafe_b64encode(message.as_bytes()).decode()
        
        service.users().messages().send(userId='me', body={'raw': raw_message}).execute()
        return "✅ Email Sent Successfully!"
    except Exception as e:
        return f"❌ Failed to send: {str(e)}"
    
from email.mime.text import MIMEText