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
    """Retrieves and refreshes user credentials."""
    creds = None
    if os.path.exists(TOKEN_FILE):
        creds = Credentials.from_authorized_user_file(TOKEN_FILE, SCOPES)
    
    # Auto-refresh logic
    if creds and creds.expired and creds.refresh_token:
        try:
            creds.refresh(Request())
            with open(TOKEN_FILE, 'w') as token:
                token.write(creds.to_json())
        except Exception as e:
            logger.error(f"Token Refresh Failed: {e}")
            return None
    return creds

def is_user_authenticated():
    """Checks if the user has a valid session."""
    creds = get_credentials()
    return creds is not None and creds.valid

def get_service():
    creds = get_credentials()
    if creds and creds.valid:
        return build('gmail', 'v1', credentials=creds)
    return None

def list_messages(query='label:INBOX', max_results=5):
    """Fetches a list of emails (ID, Subject, Sender) for Inbox/Search."""
    service = get_service()
    if not service: return []
    
    try:
        results = service.users().messages().list(userId='me', q=query, maxResults=max_results).execute()
        messages = results.get('messages', [])
        
        email_list = []
        for msg in messages:
            # Metadata fetch (lighter than full format)
            m = service.users().messages().get(userId='me', id=msg['id'], format='metadata').execute()
            headers = m['payload']['headers']
            subject = next((h['value'] for h in headers if h['name'] == 'Subject'), '(No Subject)')
            sender = next((h['value'] for h in headers if h['name'] == 'From'), 'Unknown')
            email_list.append({'id': msg['id'], 'subject': subject, 'sender': sender})
            
        return email_list
    except Exception as e:
        logger.error(f"List Error: {e}")
        return []

def get_email_details(msg_id):
    """Fetches full email content."""
    service = get_service()
    if not service: return None
    try:
        msg = service.users().messages().get(userId='me', id=msg_id, format='full').execute()
        payload = msg['payload']
        
        body = ""
        if 'parts' in payload:
            for part in payload['parts']:
                if part['mimeType'] == 'text/plain':
                    body = base64.urlsafe_b64decode(part['body'].get('data', '')).decode()
        elif 'body' in payload:
            body = base64.urlsafe_b64decode(payload['body'].get('data', '')).decode()
            
        headers = payload.get('headers', [])
        subject = next((h['value'] for h in headers if h['name'] == 'Subject'), "No Subject")
        sender = next((h['value'] for h in headers if h['name'] == 'From'), "Unknown")
        
        return {'id': msg_id, 'sender': sender, 'subject': subject, 'body': body or msg.get('snippet', '')}
    except Exception:
        return None

def send_email_api(to, subject, body):
    """Sends an email via Gmail API."""
    service = get_service()
    if not service: return "❌ Authentication Failed. Please Login."
    try:
        message = MIMEText(body)
        message['to'] = to
        message['subject'] = subject
        raw = base64.urlsafe_b64encode(message.as_bytes()).decode()
        service.users().messages().send(userId='me', body={'raw': raw}).execute()
        return "✅ Email sent successfully."
    except Exception as e:
        return f"❌ Transmission Error: {str(e)}"