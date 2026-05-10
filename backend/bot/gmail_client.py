import os
import base64
import mimetypes
import asyncio
import logging
from typing import Any, Dict, List, Optional
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.base import MIMEBase
from email import encoders

from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

from db.models import db_manager
from config import settings

logger = logging.getLogger(__name__)

class GmailClient:
    def __init__(self) -> None:
        self.db = db_manager

    async def _build_credentials(self, telegram_id: int) -> Optional[Credentials]:
        """Securely reconstructs Google OAuth credentials from the database."""
        user = await self.db.get_user(telegram_id)
        if not user or not user.get("auth_token"):
            return None

        auth_token = user["auth_token"]
        token = auth_token.get("token")
        if not token:
            return None

        try:
            return Credentials(
                token=token,
                refresh_token=auth_token.get("refresh_token"),
                token_uri=auth_token.get("token_uri", "https://oauth2.googleapis.com/token"),
                client_id=settings.GOOGLE_OAUTH_CLIENT_ID,
                client_secret=settings.GOOGLE_OAUTH_CLIENT_SECRET,
                scopes=auth_token.get("scopes")
            )
        except Exception as e:
            logger.error(f"Failed to build credentials for {telegram_id}: {e}")
            return None

    async def get_service(self, telegram_id: int) -> Any:
        """Returns an authenticated Gmail service instance for the user."""
        creds = await self._build_credentials(telegram_id)
        if creds and creds.valid:
            return build('gmail', 'v1', credentials=creds)
        return None

    async def get_emails(self, telegram_id: int, query: str = 'is:unread', max_results: int = 5) -> List[Dict[str, Any]]:
        """Fetches a list of emails matching the query."""
        service = await self.get_service(telegram_id)
        if not service:
            return []

        try:
            results = await asyncio.to_thread(
                lambda: service.users().messages().list(userId='me', q=query, maxResults=max_results).execute()
            )
            return results.get('messages', [])
        except Exception as e:
            logger.error(f"Error fetching emails for {telegram_id}: {e}")
            return []

    async def get_email_metadata(self, telegram_id: int, msg_id: str) -> Dict[str, Any]:
        """Fetches and parses essential metadata (Sender, Subject, Date) from an email."""
        service = await self.get_service(telegram_id)
        if not service:
            return {"error": "Authentication required"}

        try:
            msg = await asyncio.to_thread(
                lambda: service.users().messages().get(userId='me', id=msg_id, format='metadata', metadataHeaders=['From', 'Subject', 'Date']).execute()
            )
            
            headers = msg['payload']['headers']
            subject = next((h['value'] for h in headers if h['name'].lower() == 'subject'), 'No Subject')
            sender = next((h['value'] for h in headers if h['name'].lower() == 'from'), 'Unknown Sender')
            date = next((h['value'] for h in headers if h['name'].lower() == 'date'), 'Unknown Date')
            
            return {
                "id": msg_id,
                "subject": subject,
                "sender": sender,
                "date": date,
                "snippet": msg.get('snippet', '')
            }
        except Exception as e:
            logger.error(f"Error fetching metadata for {msg_id}: {e}")
            return {"error": str(e)}

    async def read_full_email(self, telegram_id: int, msg_id: str) -> str:
        """Fetches the full content of an email, decoding base64 payload."""
        service = await self.get_service(telegram_id)
        if not service:
            return "Authentication required. Please login."

        try:
            msg = await asyncio.to_thread(
                lambda: service.users().messages().get(userId='me', id=msg_id, format='full').execute()
            )
            
            payload = msg.get('payload', {})
            body_data = ""
            
            if 'parts' in payload:
                for part in payload['parts']:
                    if part['mimeType'] == 'text/plain':
                        body_data = part['body'].get('data', '')
                        break
            else:
                body_data = payload.get('body', {}).get('data', '')

            if body_data:
                decoded_body = base64.urlsafe_b64decode(body_data).decode('utf-8')
                return decoded_body
            return "Email content is empty or contains unsupported rich media."
            
        except Exception as e:
            logger.error(f"Error reading email {msg_id}: {e}")
            return f"Failed to read email: {str(e)}"

    async def send_email(self, telegram_id: int, to: str, subject: str, body: str, attachments: List[str] = None) -> str:
        """Constructs and sends an email, handling optional attachments securely."""
        service = await self.get_service(telegram_id)
        if not service:
            return "❌ Authentication required. Please log in first."

        try:
            if not attachments:
                message = MIMEText(body)
            else:
                message = MIMEMultipart()
                message.attach(MIMEText(body))
                
                for file_path in attachments:
                    if not os.path.exists(file_path):
                        continue
                    content_type, encoding = mimetypes.guess_type(file_path)
                    if content_type is None or encoding is not None:
                        content_type = 'application/octet-stream'
                    main_type, sub_type = content_type.split('/', 1)

                    with open(file_path, 'rb') as fp:
                        msg_file = MIMEBase(main_type, sub_type)
                        msg_file.set_payload(fp.read())
                    
                    encoders.encode_base64(msg_file)
                    filename = os.path.basename(file_path)
                    msg_file.add_header('Content-Disposition', 'attachment', filename=filename)
                    message.attach(msg_file)

            message['to'] = to
            message['subject'] = subject
            raw = base64.urlsafe_b64encode(message.as_bytes()).decode()

            await asyncio.to_thread(
                lambda: service.users().messages().send(userId='me', body={'raw': raw}).execute()
            )
            
            return "✅ Email transmitted successfully."
        except HttpError as error:
            logger.error(f"Google API Error: {error}")
            return f"❌ Transmission failed: {error}"
        except Exception as e:
            logger.error(f"Transmission Error: {e}")
            return f"❌ Transmission Error: {str(e)}"

    async def delete_email(self, telegram_id: int, msg_id: str) -> bool:
        """Moves a specific email to the trash."""
        service = await self.get_service(telegram_id)
        if not service:
            return False
        try:
            await asyncio.to_thread(
                lambda: service.users().messages().trash(userId='me', id=msg_id).execute()
            )
            return True
        except Exception as e:
            logger.error(f"Error trashing email {msg_id}: {e}")
            return False

# Singleton instance
gmail_client = GmailClient()