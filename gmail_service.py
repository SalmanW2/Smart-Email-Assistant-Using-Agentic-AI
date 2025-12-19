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
    """
    Priority:
    1. Local 'token.json' (Jo abhi taaza login se bana hai)
    2. Render Secret '/etc/secrets/token.json' (Backup/Old)
    """
    creds = None
    
    # --- CHANGE IS HERE (Priority Flip) ---
    
    # 1. Pehle Local File check karo (Jo Flask ne banayi hai)
    if os.path.exists("token.json"):
        logger.info("✅ Found FRESH Local Token.")
        creds = Credentials.from_authorized_user_file("token.json", SCOPES)
        
    # 2. Agar Local nahi mili, to Render Secret check karo
    elif os.path.exists("/etc/secrets/token.json"):
        logger.info("⚠️ Using Render Secret Token (Might be old).")
        creds = Credentials.from_authorized_user_file("/etc/secrets/token.json", SCOPES)
    
    # --------------------------------------

    # Token Refresh Logic
    if creds and creds.expired and creds.refresh_token:
        try:
            logger.info("🔄 Refreshing Token...")
            creds.refresh(Request())
            
            # Refresh hone ke baad naya token wapas save bhi kar lo
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
    if not creds:
        return None
    return build('gmail', 'v1', credentials=creds)

# --- SEARCH LOGIC (Updated for Specific Sender) ---
def get_last_email(query='label:INBOX'):
    try:
        service = get_gmail_service()
        if not service: return "AUTH_ERROR"

        results = service.users().messages().list(userId='me', q=query, maxResults=1).execute()
        messages = results.get('messages', [])

        if not messages:
            return None

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
        logger.error(f"Read Error: {e}")
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
        logger.error(f"Send Error: {e}")
        return f"Failed: {str(e)}" 