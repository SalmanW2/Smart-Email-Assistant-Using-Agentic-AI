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

SCOPES = ['https://www.googleapis.com/auth/gmail.modify']

def get_credentials():
    creds = None
    # 1. Pehle Local File check karo (Fresh Login)
    if os.path.exists("token.json"):
        creds = Credentials.from_authorized_user_file("token.json", SCOPES)
    # 2. Phir Render Secret check karo (Backup)
    elif os.path.exists("/etc/secrets/token.json"):
        creds = Credentials.from_authorized_user_file("/etc/secrets/token.json", SCOPES)

    # Token Refresh Logic
    if creds and creds.expired and creds.refresh_token:
        try:
            creds.refresh(Request())
            # Save refreshed token locally
            with open("token.json", "w") as token_file:
                token_file.write(creds.to_json())
        except Exception as e:
            logger.error(f"❌ Token Refresh Failed: {e}")
            return None

    if not creds or not creds.valid:
        return None

    return creds

def get_gmail_service():
    creds = get_credentials()
    if not creds: return None
    return build('gmail', 'v1', credentials=creds)

# --- NEW: LIGHTWEIGHT CHECKER ---
def get_latest_message_id():
    """Sirf Latest Email ki ID lata hai (Data bachat ke liye)"""
    try:
        service = get_gmail_service()
        if not service: return None
        
        # Sirf 1 ID mangwao
        results = service.users().messages().list(userId='me', labelIds=['INBOX'], maxResults=1).execute()
        messages = results.get('messages', [])
        
        if messages:
            return messages[0]['id']
        return None
    except Exception as e:
        logger.error(f"Check Error: {e}")
        return None

# --- NEW: DETAILS FETCHING ---
def get_email_details(msg_id):
    """Specific ID ki detail lata hai"""
    try:
        service = get_gmail_service()
        if not service: return None
        
        msg = service.users().messages().get(userId='me', id=msg_id).execute()
        payload = msg['payload']
        headers = payload['headers']

        subject = "No Subject"
        sender = "Unknown"
        sender_email = ""

        for h in headers:
            if h['name'] == 'Subject': subject = h['value']
            if h['name'] == 'From': 
                sender = h['value']
                # Email address extract karna (<email@com>)
                if "<" in sender:
                    sender_email = sender.split("<")[1].strip(">")
                else:
                    sender_email = sender

        snippet = msg.get('snippet', '')
        
        return {
            "sender_view": sender,
            "sender_email": sender_email,
            "subject": subject,
            "snippet": snippet
        }
    
    except Exception as e:
        return None

# --- OLD FUNCTIONS (STILL NEEDED) ---
def get_last_email(query='label:INBOX'):
    # (Ye function manual check ke liye abhi bhi use hoga)
    # Isay wesa hi rehne do jesa pichli baar tha
    try:
        service = get_gmail_service()
        if not service: return "AUTH_ERROR"

        results = service.users().messages().list(userId='me', q=query, maxResults=1).execute()
        messages = results.get('messages', [])

        if not messages: return None

        msg = service.users().messages().get(userId='me', id=messages[0]['id']).execute()
        payload = msg['payload']
        headers = payload['headers']

        subject = "No Subject"
        sender = "Unknown"
        for h in headers:
            if h['name'] == 'Subject': subject = h['value']
            if h['name'] == 'From': sender = h['value']

        snippet = msg.get('snippet', '')
        return f"👤 **From:** `{sender}`\n📌 **Subject:** `{subject}`\n📝 **Body:** {snippet}..."
    except Exception as e:
        return f"Error: {str(e)}"

def create_and_send_email(to_email, subject, body_text):
    try:
        service = get_gmail_service()
        if not service: return "AUTH_ERROR"
        
        message = MIMEText(body_text)
        message['to'] = to_email
        message['subject'] = subject
        raw_message = base64.urlsafe_b64encode(message.as_bytes()).decode()
        
        body = {'raw': raw_message}
        service.users().messages().send(userId='me', body=body).execute()
        return "Email Sent Successfully! ✅"
    except Exception as e:
        return f"Failed: {str(e)}"