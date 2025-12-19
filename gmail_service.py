import os.path
import base64
import logging
from email.mime.text import MIMEText
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

SCOPES = ['https://www.googleapis.com/auth/gmail.modify']

def get_credentials():
    # Pehle Render Secrets check karo, phir Local
    if os.path.exists("/etc/secrets/token.json"):
        return Credentials.from_authorized_user_file("/etc/secrets/token.json", SCOPES)
    elif os.path.exists("token.json"):
        return Credentials.from_authorized_user_file("token.json", SCOPES)
    return None

def get_gmail_service():
    creds = get_credentials()
    # Agar token expired hai to refresh karne ki koshish (Basic Logic)
    if creds and creds.expired and creds.refresh_token:
        try:
            creds.refresh(Request())
        except:
            return None
            
    if not creds or not creds.valid:
        return None
        
    return build('gmail', 'v1', credentials=creds)

# --- UPDATED FUNCTION FOR SPECIFIC SEARCH ---
def get_last_email(query='label:INBOX'):
    """
    Emails fetch karta hai.
    Default: Inbox ki last email.
    Query: Agar 'from:boss@gmail.com' doge to uski last email layega.
    """
    try:
        service = get_gmail_service()
        if not service: return "AUTH_ERROR"

        # Query parameter use kar rahe hain search ke liye
        results = service.users().messages().list(userId='me', q=query, maxResults=1).execute()
        messages = results.get('messages', [])

        if not messages:
            return None # Koi email nahi mili

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
        
        service.users().messages().send(userId='me', body={'raw': raw_message}).execute()
        return "Email Sent Successfully! ✅"
    except Exception as e:
        return f"Failed: {str(e)}"