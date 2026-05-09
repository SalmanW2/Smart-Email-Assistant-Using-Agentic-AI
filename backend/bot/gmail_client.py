from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from db.models import db_manager
from config import config
import base64
from email.mime.text import MIMEText
from typing import List, Dict, Any, Optional

class GmailClient:
    def __init__(self):
        self.db = db_manager

    async def get_credentials(self, user_id: str) -> Optional[Credentials]:
        session = await self.db.get_auth_session(user_id)
        if not session:
            return None

        return Credentials(
            token=session["access_token"],
            refresh_token=session["refresh_token"],
            token_uri="https://oauth2.googleapis.com/token",
            client_id=config.GOOGLE_CLIENT_ID,  # Assuming added to config
            client_secret=config.GOOGLE_CLIENT_SECRET,
            expiry=session["expires_at"]
        )

    async def refresh_credentials(self, user_id: str) -> bool:
        creds = await self.get_credentials(user_id)
        if creds and creds.expired:
            creds.refresh(Request())
            await self.db.update_auth_session(
                user_id, 
                creds.token, 
                creds.refresh_token, 
                creds.expiry.timestamp()
            )
        return True

    async def get_recent_emails(self, user_id: str, max_results: int = 10) -> List[Dict[str, Any]]:
        creds = await self.get_credentials(user_id)
        if not creds:
            return []

        try:
            service = build('gmail', 'v1', credentials=creds)
            results = service.users().messages().list(userId='me', maxResults=max_results).execute()
            messages = results.get('messages', [])

            emails = []
            for msg in messages:
                msg_data = service.users().messages().get(userId='me', id=msg['id']).execute()
                email = self.parse_email(msg_data)
                emails.append(email)

            return emails
        except HttpError as e:
            print(f"Gmail API error: {e}")
            return []

    def parse_email(self, msg_data: Dict) -> Dict[str, Any]:
        headers = msg_data['payload']['headers']
        subject = next((h['value'] for h in headers if h['name'] == 'Subject'), '')
        sender = next((h['value'] for h in headers if h['name'] == 'From'), '')
        snippet = msg_data.get('snippet', '')

        return {
            'id': msg_data['id'],
            'subject': subject,
            'sender': sender,
            'snippet': snippet,
            'thread_id': msg_data['threadId']
        }

    async def send_email(self, user_id: str, to: str, subject: str, body: str) -> bool:
        creds = await self.get_credentials(user_id)
        if not creds:
            return False

        try:
            service = build('gmail', 'v1', credentials=creds)
            message = MIMEText(body)
            message['to'] = to
            message['subject'] = subject
            raw = base64.urlsafe_b64encode(message.as_bytes()).decode()

            service.users().messages().send(userId='me', body={'raw': raw}).execute()
            return True
        except HttpError:
            return False

    async def reply_email(self, user_id: str, thread_id: str, body: str) -> bool:
        creds = await self.get_credentials(user_id)
        if not creds:
            return False

        try:
            service = build('gmail', 'v1', credentials=creds)
            message = MIMEText(body)
            raw = base64.urlsafe_b64encode(message.as_bytes()).decode()

            service.users().messages().send(
                userId='me', 
                body={
                    'raw': raw,
                    'threadId': thread_id
                }
            ).execute()
            return True
        except HttpError:
            return False

    async def delete_email(self, user_id: str, email_id: str) -> bool:
        creds = await self.get_credentials(user_id)
        if not creds:
            return False

        try:
            service = build('gmail', 'v1', credentials=creds)
            service.users().messages().delete(userId='me', id=email_id).execute()
            return True
        except HttpError:
            return False

gmail_client = GmailClient()