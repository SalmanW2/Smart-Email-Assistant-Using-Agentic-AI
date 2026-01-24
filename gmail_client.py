import os
import base64
import logging
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from email.mime.text import MIMEText

# Logging Setup
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("GmailClient")

SCOPES = ['https://www.googleapis.com/auth/gmail.modify']
TOKEN_FILE = 'token.json'

def get_credentials():
    """Returns credentials object."""
    if os.path.exists(TOKEN_FILE):
        creds = Credentials.from_authorized_user_file(TOKEN_FILE, SCOPES)
        if creds and creds.valid:
            return creds
    return None

def _parse_body(payload):
    """Recursively decodes email body from Base64."""
    if 'parts' in payload:
        for part in payload['parts']:
            if part['mimeType'] == 'text/plain':
                data = part['body'].get('data')
                if data:
                    return base64.urlsafe_b64decode(data).decode()
            if 'parts' in part:
                val = _parse_body(part)
                if val: return val
    elif 'body' in payload:
        data = payload['body'].get('data')
        if data:
            return base64.urlsafe_b64decode(data).decode()
    return ""

def get_latest_email_details():
    """Fetches the latest email with full body."""
    creds = get_credentials()
    if not creds: return None
    
    try:
        service = build('gmail', 'v1', credentials=creds)
        results = service.users().messages().list(userId='me', maxResults=1).execute()
        messages = results.get('messages', [])
        if not messages: return None
        
        msg_id = messages[0]['id']
        msg = service.users().messages().get(userId='me', id=msg_id, format='full').execute()
        
        payload = msg['payload']
        headers = payload.get('headers', [])
        subject = "No Subject"
        sender = "Unknown"
        
        for h in headers:
            if h['name'] == 'Subject': subject = h['value']
            if h['name'] == 'From': sender = h['value']
        
        body = _parse_body(payload) or msg.get('snippet', '')

        return {
            'id': msg_id,
            'sender_email': sender, 
            'sender_view': sender.split("<")[0].strip().replace('"', ''),
            'subject': subject,
            'body': body
        }
    except Exception as e:
        logger.error(f"Error fetching email: {e}")
        return None

def get_latest_message_id():
    """Fetches just the ID for quick checking."""
    creds = get_credentials()
    if not creds: return None
    try:
        service = build('gmail', 'v1', credentials=creds)
        results = service.users().messages().list(userId='me', maxResults=1).execute()
        messages = results.get('messages', [])
        if not messages: return None
        return messages[0]['id']
    except Exception as e:
        logger.error(f"Error fetching ID: {e}")
        return None

def send_email(to, subject, body_text):
    """Sends an email using Gmail API."""
    creds = get_credentials()
    if not creds: return "⚠️ Auth Error: Login required."
    try:
        service = build('gmail', 'v1', credentials=creds)
        message = MIMEText(body_text)
        message['to'] = to
        message['subject'] = subject
        raw_message = base64.urlsafe_b64encode(message.as_bytes()).decode()
        
        service.users().messages().send(userId='me', body={'raw': raw_message}).execute()
        return "✅ Email Sent Successfully!"
    except Exception as e:
        return f"❌ Failed to send: {str(e)}"