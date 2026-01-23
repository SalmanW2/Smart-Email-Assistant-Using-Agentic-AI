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

class GmailClient:
    """
    Handles all interactions with Gmail API.
    Ref: Section 5.4 of Project Report.
    """
    def __init__(self):
        self.creds = None
        self.service = None
        # Initialize Auth immediately
        self.authenticate()

    def authenticate(self):
        """Loads OAuth2 credentials from token file."""
        if os.path.exists(TOKEN_FILE):
            self.creds = Credentials.from_authorized_user_file(TOKEN_FILE, SCOPES)
            if self.creds and self.creds.valid:
                self.service = build('gmail', 'v1', credentials=self.creds)
                logger.info("✅ Gmail Service Authenticated")
            else:
                logger.warning("⚠️ Credentials expired or invalid")
        else:
            logger.warning("⚠️ No token.json found.")

    def get_credentials(self):
        """Returns credentials object."""
        # Refresh if needed
        self.authenticate()
        return self.creds

    def _parse_body(self, payload):
        """Recursively decodes email body from Base64."""
        if 'parts' in payload:
            for part in payload['parts']:
                if part['mimeType'] == 'text/plain':
                    data = part['body'].get('data')
                    if data:
                        return base64.urlsafe_b64decode(data).decode()
                if 'parts' in part:
                    val = self._parse_body(part)
                    if val: return val
        elif 'body' in payload:
            data = payload['body'].get('data')
            if data:
                return base64.urlsafe_b64decode(data).decode()
        return ""

    def get_latest_email_details(self):
        """Fetches the latest email with full body."""
        if not self.service: self.authenticate()
        if not self.service: return None

        try:
            results = self.service.users().messages().list(userId='me', maxResults=1).execute()
            messages = results.get('messages', [])
            if not messages: return None
            
            msg_id = messages[0]['id']
            msg = self.service.users().messages().get(userId='me', id=msg_id, format='full').execute()
            
            payload = msg['payload']
            headers = payload.get('headers', [])
            subject = "No Subject"
            sender = "Unknown"
            
            for h in headers:
                if h['name'] == 'Subject': subject = h['value']
                if h['name'] == 'From': sender = h['value']
            
            # Fetch Full Body
            body = self._parse_body(payload) or msg.get('snippet', '')

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

    def get_latest_message_id(self):
        """Fetches just the ID for quick checking."""
        if not self.service: self.authenticate()
        if not self.service: return None
        try:
            results = self.service.users().messages().list(userId='me', maxResults=1).execute()
            messages = results.get('messages', [])
            if not messages: return None
            return messages[0]['id']
        except Exception as e:
            logger.error(f"Error fetching ID: {e}")
            return None

    def send_email(self, to, subject, body_text):
        """Sends an email using Gmail API."""
        if not self.service: return "⚠️ Auth Error: Login required."
        try:
            message = MIMEText(body_text)
            message['to'] = to
            message['subject'] = subject
            raw_message = base64.urlsafe_b64encode(message.as_bytes()).decode()
            
            self.service.users().messages().send(userId='me', body={'raw': raw_message}).execute()
            return "✅ Email Sent Successfully!"
        except Exception as e:
            return f"❌ Failed to send: {str(e)}"