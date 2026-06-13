"""
Gmail API Client Wrapper — Smart Email Assistant
================================================
Handles all secure interactions with the Google Gmail API using OAuth 2.0 credentials.
Features:
1. Asynchronous fetching, searching, and parsing of complex MIME email formats.
2. Robust Base64 encoded transmission for outbound emails with dynamic attachments.
3. Strict separation of concerns: File deletion/cleanup is completely delegated to 
   the Telegram Handler's execution context to prevent resource race conditions.
"""

import os
import base64
import mimetypes
import asyncio
import logging
from typing import Dict, Any, List, Optional
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.base import MIMEBase
from email import encoders

from googleapiclient.discovery import build
from google.oauth2.credentials import Credentials

from db.models import db_manager

logger = logging.getLogger(__name__)

class GmailClient:
    def __init__(self) -> None:
        """
        Initializes the Gmail Client.
        Maintains a temporary in-memory dictionary to track staged attachments 
        for users before they trigger the final dispatch action.
        """
        self.user_attachments: Dict[int, List[Dict[str, str]]] = {} 

    def _handle_auth_error(self, e: Exception) -> str:
        """
        Centralized error handler for Google API token expiration or credential invalidation.
        Translates raw HTTP 400/401 errors into user-friendly Markdown warnings.
        """
        err_str = str(e).lower()
        if any(keyword in err_str for keyword in ["refresh_token", "credentials", "token", "unauthorized", "invalid_grant"]):
            return "❌ *Authentication Expired:* Your Google account access is invalid or expired. Please go to '⚙️ Settings', click **Logout Account**, and securely reconnect your account."
        return f"❌ Error executing Gmail API request: {str(e)}"

    async def get_service(self, user_id: int) -> Optional[Any]:
        """
        Retrieves the user's OAuth 2.0 token from the Supabase database and 
        constructs the authenticated Google API service resource.
        """
        try:
            user = await db_manager.get_user(user_id)
            if not user or not user.get("auth_token"):
                logger.warning(f"No auth token found for user {user_id}")
                return None

            token_data = user["auth_token"]
            credentials = Credentials(
                token=token_data.get("token"),
                refresh_token=token_data.get("refresh_token"),
                token_uri=token_data.get("token_uri"),
                client_id=token_data.get("client_id"),
                client_secret=token_data.get("client_secret"),
                scopes=token_data.get("scopes")
            )
            
            # Build the service asynchronously to prevent blocking
            service = await asyncio.to_thread(build, 'gmail', 'v1', credentials=credentials, cache_discovery=False)
            return service
        except Exception as e:
            logger.error(f"Failed to build Gmail service for user {user_id}: {e}")
            return None

    # ==========================================
    # ATTACHMENT STAGING MANAGEMENT
    # ==========================================
    
    def add_user_attachment(self, user_id: int, file_path: str, file_name: str) -> None:
        """Stages an attachment into the user's temporary session memory."""
        if user_id not in self.user_attachments:
            self.user_attachments[user_id] = []
        self.user_attachments[user_id].append({"path": file_path, "name": file_name})

    def get_user_attachments(self, user_id: int) -> List[Dict[str, str]]:
        """Retrieves all staged attachments for the current user session."""
        return self.user_attachments.get(user_id, [])

    def clear_user_attachments(self, user_id: int) -> None:
        """Clears the attachment reference cache. (Does not delete actual files)."""
        if user_id in self.user_attachments:
            del self.user_attachments[user_id]

    # ==========================================
    # OUTBOUND TRANSMISSION (SENDING)
    # ==========================================

    async def send_email(self, user_id: int, to_address: str, subject: str, body: str, manual_attachments: Optional[List[str]] = None) -> str:
        """
        Constructs and dispatches a multipart MIME email with dynamic attachments.
        NOTE: File lifecycle operations (os.remove) have been strictly stripped from this method 
        and delegated to the Telegram Handler to prevent race conditions.
        """
        service = await self.get_service(user_id)
        if not service:
            return "❌ *Error:* Not authenticated. Please link your Gmail account."

        try:
            # Construct the comprehensive MIME container
            message = MIMEMultipart()
            message['To'] = to_address
            message['Subject'] = subject
            message.attach(MIMEText(body, 'html'))

            # Merge manual task attachments with session staged attachments
            attachments_to_process = []
            if manual_attachments:
                attachments_to_process.extend([{"path": p, "name": os.path.basename(p)} for p in manual_attachments])
            
            staged_attachments = self.get_user_attachments(user_id)
            if staged_attachments:
                attachments_to_process.extend(staged_attachments)

            # Process and encode all verified attachments
            for att in attachments_to_process:
                file_path = att["path"]
                file_name = att["name"]
                
                if not os.path.exists(file_path):
                    logger.warning(f"Attachment missing during dispatch: {file_path}")
                    continue

                content_type, encoding = mimetypes.guess_type(file_path)
                if content_type is None or encoding is not None:
                    content_type = 'application/octet-stream'
                main_type, sub_type = content_type.split('/', 1)

                with open(file_path, 'rb') as f:
                    part = MIMEBase(main_type, sub_type)
                    part.set_payload(f.read())
                    encoders.encode_base64(part)
                    part.add_header('Content-Disposition', f'attachment; filename="{file_name}"')
                    message.attach(part)

            # Transmit the payload securely via Google's API
            raw_payload = base64.urlsafe_b64encode(message.as_bytes()).decode()
            await asyncio.to_thread(
                lambda: service.users().messages().send(userId='me', body={'raw': raw_payload}).execute()
            )
            
            # NOTE: We only clear the RAM cache dict here. 
            # Physical file deletion is now executed natively in telegram_handler.py's finally block.
            self.clear_user_attachments(user_id)
            
            return "✅ Email transmitted successfully."
            
        except Exception as e:
            logger.error(f"Failed to dispatch email for {user_id}: {e}")
            return self._handle_auth_error(e)

    # ==========================================
    # INBOUND FETCHING & SEARCHING
    # ==========================================

    async def get_unread_emails(self, user_id: int, limit: int = 5) -> List[Dict[str, Any]]:
        """
        Polls the inbox for unread messages within the last 24 hours.
        Utilized primarily by the background APScheduler cron logic.
        """
        service = await self.get_service(user_id)
        if not service:
            return []

        try:
            query = "is:unread newer_than:1d"
            response = await asyncio.to_thread(
                lambda: service.users().messages().list(userId='me', q=query, maxResults=limit).execute()
            )
            messages = response.get('messages', [])
            
            detailed_emails = []
            for msg in messages:
                details = await self.get_email_details(user_id, msg['id'])
                if details:
                    detailed_emails.append(details)
            return detailed_emails
        except Exception as e:
            logger.error(f"Error fetching unread emails for {user_id}: {e}")
            return []

    async def search_emails(self, user_id: int, query: str, max_results: int = 5) -> List[Dict[str, Any]]:
        """
        Searches the user's inbox based on a dynamic query.
        Utilized natively by the Agentic AI's search tool.
        """
        service = await self.get_service(user_id)
        if not service:
            return []
            
        try:
            response = await asyncio.to_thread(
                lambda: service.users().messages().list(userId='me', q=query, maxResults=max_results).execute()
            )
            messages = response.get('messages', [])
            
            results = []
            for msg in messages:
                details = await self.get_email_details(user_id, msg['id'])
                if details:
                    results.append(details)
            return results
        except Exception as e:
            logger.error(f"Error executing Gmail search query '{query}' for {user_id}: {e}")
            return []

    async def get_email_details(self, user_id: int, msg_id: str) -> Optional[Dict[str, Any]]:
        """
        Extracts complex payload data, resolves MIME parts, and identifies key headers.
        """
        service = await self.get_service(user_id)
        if not service:
            return None

        try:
            msg = await asyncio.to_thread(
                lambda: service.users().messages().get(userId='me', id=msg_id, format='full').execute()
            )
            
            payload = msg.get('payload', {})
            headers = payload.get('headers', [])
            
            subject = next((h['value'] for h in headers if h['name'].lower() == 'subject'), 'No Subject')
            sender = next((h['value'] for h in headers if h['name'].lower() == 'from'), 'Unknown Sender')
            
            body = self._extract_body(payload)
            snippet = msg.get('snippet', '')

            return {
                "id": msg_id,
                "sender": sender,
                "subject": subject,
                "snippet": snippet,
                "body": body
            }
        except Exception as e:
            logger.error(f"Error extracting email details for msg {msg_id}: {e}")
            return None

    def _extract_body(self, payload: Dict[str, Any]) -> str:
        """
        Recursively parses email payload boundaries to extract the cleanest available text format.
        """
        body_data = ""
        if 'parts' in payload:
            for part in payload['parts']:
                if part['mimeType'] == 'text/plain':
                    data = part['body'].get('data')
                    if data:
                        body_data += base64.urlsafe_b64decode(data).decode('utf-8')
                elif part['mimeType'] == 'text/html':
                    data = part['body'].get('data')
                    if data and not body_data: # Fallback to HTML if plain text is missing
                        body_data += base64.urlsafe_b64decode(data).decode('utf-8')
                elif 'parts' in part:
                    body_data += self._extract_body(part)
        else:
            data = payload.get('body', {}).get('data')
            if data:
                body_data = base64.urlsafe_b64decode(data).decode('utf-8')
                
        return body_data.strip()

    # ==========================================
    # EMAIL MUTATION OPERATIONS
    # ==========================================

    async def delete_email(self, user_id: int, msg_id: str) -> bool:
        """Moves a specific email to the user's Gmail trash bin."""
        service = await self.get_service(user_id)
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

    async def untrash_email(self, user_id: int, msg_id: str) -> bool:
        """Restores a specific email from the user's Gmail trash bin."""
        service = await self.get_service(user_id)
        if not service:
            return False
        try:
            await asyncio.to_thread(
                lambda: service.users().messages().untrash(userId='me', id=msg_id).execute()
            )
            return True
        except Exception as e:
            logger.error(f"Error untrashing email {msg_id}: {e}")
            return False