import os
import base64
import logging
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from google.auth.transport.requests import Request
from email.mime.text import MIMEText
from config_env import TOKEN_FILE, SCOPES

logger = logging.getLogger(__name__)

def get_credentials():
    """Loads and Auto-Refreshes tokens."""
    creds = None
    if os.path.exists(TOKEN_FILE):
        creds = Credentials.from_authorized_user_file(TOKEN_FILE, SCOPES)
    
    if creds and creds.expired and creds.refresh_token:
        try:
            creds.refresh(Request())
            with open(TOKEN_FILE, 'w') as token:
                token.write(creds.to_json())
        except Exception as e:
            logger.error(f"Refresh Error: {e}")
            return None
    return creds

def get_service():
    creds = get_credentials()
    if creds and creds.valid:
        return build('gmail', 'v1', credentials=creds)
    return None

def get_latest_id(filter_unread=False):
    service = get_service()
    if not service: return None
    try:
        query = "label:INBOX"
        if filter_unread:
            query += " label:UNREAD"
        results = service.users().messages().list(userId='me', q=query, maxResults=1).execute()
        messages = results.get('messages', [])
        return messages[0]['id'] if messages else None
    except Exception:
        return None

def get_email_details(msg_id):
    service = get_service()
    if not service or not msg_id: return None
    try:
        msg = service.users().messages().get(userId='me', id=msg_id, format='full').execute()
        payload = msg['payload']
        headers = payload.get('headers', [])
        
        subject = next((h['value'] for h in headers if h['name'] == 'Subject'), "No Subject")
        sender = next((h['value'] for h in headers if h['name'] == 'From'), "Unknown")
        
        body = ""
        if 'parts' in payload:
            for part in payload['parts']:
                if part['mimeType'] == 'text/plain':
                    data = part['body'].get('data', '')
                    body = base64.urlsafe_b64decode(data).decode()
        elif 'body' in payload:
            data = payload['body'].get('data', '')
            body = base64.urlsafe_b64decode(data).decode()
            
        return {'id': msg_id, 'sender': sender, 'subject': subject, 'body': body or msg.get('snippet', '')}
    except Exception:
        return None

def send_email_api(to, subject, body):
    service = get_service()
    if not service: return "❌ Login Required"
    try:
        message = MIMEText(body)
        message['to'] = to
        message['subject'] = subject
        raw = base64.urlsafe_b64encode(message.as_bytes()).decode()
        service.users().messages().send(userId='me', body={'raw': raw}).execute()
        return "✅ Email Sent!"
    except Exception as e:
        return f"❌ Error: {str(e)}"