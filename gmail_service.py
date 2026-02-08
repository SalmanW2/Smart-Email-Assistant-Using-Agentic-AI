import os
import base64
import logging
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from email.mime.text import MIMEText

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
    """
    Sirf Latest Email ki ID lata hai (Fast check ke liye)
    FIX: Added q='label:INBOX' to ignore sent emails.
    """
    service = get_service()
    if not service: return None
    try:
        # Sirf INBOX check karega
        results = service.users().messages().list(userId='me', q='label:INBOX', maxResults=1).execute()
        messages = results.get('messages', [])
        if not messages: return None
        return messages[0]['id']
    except Exception as e:
        logger.error(f"Error fetching ID: {e}")
        return None

# --- BODY DECODER FUNCTION ---
def parse_email_body(payload):
    body = ""
    if 'parts' in payload:
        for part in payload['parts']:
            if part['mimeType'] == 'text/plain':
                data = part['body'].get('data')
                if data:
                    body = base64.urlsafe_b64decode(data).decode()
                    return body
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

        snippet = msg.get('snippet', '')
        full_body = parse_email_body(payload)
        
        if not full_body:
            full_body = snippet

        sender_view = sender.split("<")[0].strip().replace('"', '')

        return {
            'id': msg_id,
            'sender_email': sender,     
            'sender_view': sender_view, 
            'subject': subject,
            'snippet': snippet,         
            'body': full_body           
        }
    except Exception as e:
        logger.error(f"Error fetching details: {e}")
        return None

def get_last_email(query=None):
    # Backward compatibility wrapper
    msg_id = get_latest_message_id()
    if not msg_id: return None
    details = get_email_details(msg_id)
    if not details: return None
    
    return (
        f"📩 **Latest Email**\n\n"
        f"👤 **From:** `{details['sender_view']}`\n"
        f"📌 **Subject:** `{details['subject']}`\n\n"
        f"{details['body'][:500]}..." 
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