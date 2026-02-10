import os
import base64
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from google.auth.transport.requests import Request
from email.mime.text import MIMEText
from config_env import TOKEN_FILE, SCOPES

def get_service():
    creds = None
    if os.path.exists(TOKEN_FILE):
        creds = Credentials.from_authorized_user_file(TOKEN_FILE, SCOPES)
    
    if creds and creds.expired and creds.refresh_token:
        creds.refresh(Request())
        with open(TOKEN_FILE, 'w') as token:
            token.write(creds.to_json())
            
    if creds and creds.valid:
        return build('gmail', 'v1', credentials=creds)
    return None

def list_messages(query='label:INBOX', max_results=5):
    """Returns a list of top 5 emails with Subject & Sender."""
    service = get_service()
    if not service: return []
    
    results = service.users().messages().list(userId='me', q=query, maxResults=max_results).execute()
    messages = results.get('messages', [])
    
    email_list = []
    for msg in messages:
        # Fetch minimal details for list view
        m = service.users().messages().get(userId='me', id=msg['id'], format='metadata').execute()
        headers = m['payload']['headers']
        subject = next((h['value'] for h in headers if h['name'] == 'Subject'), '(No Subject)')
        sender = next((h['value'] for h in headers if h['name'] == 'From'), 'Unknown')
        email_list.append({'id': msg['id'], 'subject': subject, 'sender': sender})
        
    return email_list

def get_email_details(msg_id):
    """Fetches full body for reading."""
    service = get_service()
    if not service: return None
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

def send_email_api(to, subject, body):
    service = get_service()
    if not service: return "❌ Login Required"
    message = MIMEText(body)
    message['to'] = to
    message['subject'] = subject
    raw = base64.urlsafe_b64encode(message.as_bytes()).decode()
    service.users().messages().send(userId='me', body={'raw': raw}).execute()
    return "✅ Sent!"