"""
Gmail API Client Wrapper — Smart Email Assistant
================================================
Handles secure interactions with the Google Gmail API using OAuth 2.0 credentials.

Features:
1. Metadata Payload Polling: Uses Google's format='metadata' to fetch background unread streams,
   avoiding heavy body downloads, reducing latency, and blocking Render timeouts.
2. Dynamic Token Interceptor: Resolves Google 401/403 errors and auto-refreshes tokens.
3. Sentinel Routing: Bubbles up the structured string 'TOKEN_EXPIRED_REAUTH_REQUIRED' on auth failure.
4. Clean Life-Cycle: File deletion and cleanup are delegated entirely to the caller.
"""

import os
import base64
import mimetypes
import asyncio
import logging
import tempfile
import uuid
from typing import Dict, Any, List, Optional
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.base import MIMEBase
from email import encoders

from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from google.oauth2.credentials import Credentials
from google.auth.exceptions import RefreshError
from google.auth.transport.requests import Request as GoogleRequest

from db.models import db_manager

logger = logging.getLogger(__name__)


class GmailAuthException(Exception):
    """Custom exception raised when Google OAuth credentials are invalid, expired, or revoked."""
    pass


class GmailClient:
    def __init__(self) -> None:
        """
        Initializes the Gmail Client.
        Tracks temporary in-memory attachments staged by the user before dispatch.
        """
        self.user_attachments: Dict[int, List[Dict[str, str]]] = {}

    def _is_auth_error(self, e: Exception) -> bool:
        """
        Determines if an exception is caused by revoked, invalid, or expired Google credentials.
        Processes standard HTTP statuses, RefreshErrors, and client auth failures.
        """
        err_str = str(e).lower()
        if isinstance(e, RefreshError) or isinstance(e, GmailAuthException):
            return True
        if any(keyword in err_str for keyword in ["refresh_token", "invalid_grant", "credentials", "unauthorized", "token"]):
            return True
        if isinstance(e, HttpError):
            if e.resp.status in [401, 403]:
                return True
        if "status: 401" in err_str or "status: 403" in err_str or "401 unauthorized" in err_str or "403 forbidden" in err_str:
            return True
        return False

    def _handle_auth_error(self, e: Exception) -> str:
        """
        Translates raw OAuth exceptions into a structured user-friendly Markdown string.
        """
        if self._is_auth_error(e):
            return "❌ *Authentication Expired:* Your Google account access is invalid or expired. Please go to '⚙️ Settings', click **Logout Account**, and reconnect your account."
        return f"❌ Error executing Gmail API request: {str(e)}"

    async def get_service(self, user_id: int) -> Optional[Any]:
        """
        Builds the authenticated Gmail service object.
        Intercepts expired tokens and attempts an automatic, proactive credentials refresh.
        Raises GmailAuthException if refresh fails or tokens are missing.
        """
        try:
            user = await db_manager.get_user(user_id)
            if not user or not user.get("auth_token"):
                logger.warning(f"No auth token found for user {user_id}")
                raise GmailAuthException("TOKEN_EXPIRED_REAUTH_REQUIRED")

            token_data = user["auth_token"]
            credentials = Credentials(
                token=token_data.get("token"),
                refresh_token=token_data.get("refresh_token"),
                token_uri=token_data.get("token_uri"),
                client_id=token_data.get("client_id"),
                client_secret=token_data.get("client_secret"),
                scopes=token_data.get("scopes")
            )

            # Proactively refresh the access token if expired
            if credentials.expired and credentials.refresh_token:
                try:
                    logger.info(f"Proactively refreshing Google OAuth token for user {user_id}")
                    await asyncio.to_thread(credentials.refresh, GoogleRequest())
                    
                    # Persist the refreshed token back to the Supabase database
                    updated_token_data = {**token_data, "token": credentials.token}
                    await db_manager.db.run(
                        lambda: db_manager.db.client.table("users")
                        .update({"auth_token": updated_token_data})
                        .eq("telegram_id", user_id).execute()
                    )
                    logger.info(f"Refreshed token successfully saved to Supabase for user {user_id}")
                except Exception as refresh_err:
                    logger.error(f"Failed auto-refreshing OAuth token for user {user_id}: {refresh_err}")
                    raise GmailAuthException("TOKEN_EXPIRED_REAUTH_REQUIRED")

            # Build the discovery service
            service = await asyncio.to_thread(build, 'gmail', 'v1', credentials=credentials, cache_discovery=False)
            return service
        except GmailAuthException as auth_e:
            raise auth_e
        except Exception as e:
            if self._is_auth_error(e):
                raise GmailAuthException("TOKEN_EXPIRED_REAUTH_REQUIRED")
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
        """Clears the attachment reference cache."""
        if user_id in self.user_attachments:
            del self.user_attachments[user_id]

    # ==========================================
    # OUTBOUND TRANSMISSION (SENDING)
    # ==========================================

    async def send_email(self, user_id: int, to_address: str, subject: str, body: str, manual_attachments: Optional[List[str]] = None) -> str:
        """
        Constructs and dispatches a multipart MIME email with dynamic attachments.
        Returns the structured sentinel on auth failures to prompt a re-login flow.
        """
        try:
            service = await self.get_service(user_id)
            if not service:
                return "TOKEN_EXPIRED_REAUTH_REQUIRED"

            message = MIMEMultipart()
            message['To'] = to_address
            message['Subject'] = subject or "No Subject"
            message.attach(MIMEText(body or "", 'html'))

            attachments_to_process = []
            if manual_attachments:
                attachments_to_process.extend([{"path": p, "name": os.path.basename(p)} for p in manual_attachments])
            
            staged_attachments = self.get_user_attachments(user_id)
            if staged_attachments:
                attachments_to_process.extend(staged_attachments)

            for att in attachments_to_process:
                file_path = att["path"]
                file_name = att["name"]
                
                if not os.path.exists(file_path):
                    logger.warning(f"Staged attachment file not found: {file_path}")
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

            raw_payload = base64.urlsafe_b64encode(message.as_bytes()).decode()
            await asyncio.to_thread(
                lambda: service.users().messages().send(userId='me', body={'raw': raw_payload}).execute()
            )
            
            self.clear_user_attachments(user_id)
            return "✅ Email transmitted successfully."
            
        except Exception as e:
            if self._is_auth_error(e):
                return "TOKEN_EXPIRED_REAUTH_REQUIRED"
            logger.error(f"Failed to dispatch email for user {user_id}: {e}")
            return self._handle_auth_error(e)

    # ==========================================
    # INBOUND FETCHING & SEARCHING (OPTIMIZED)
    # ==========================================

    async def get_emails(self, user_id: int, query: str = "label:INBOX", max_results: int = 5) -> Any:
        """
        Standard email fetcher.
        Returns 'TOKEN_EXPIRED_REAUTH_REQUIRED' if OAuth authorization fails.
        """
        try:
            service = await self.get_service(user_id)
            if not service:
                return "TOKEN_EXPIRED_REAUTH_REQUIRED"
            
            response = await asyncio.to_thread(
                lambda: service.users().messages().list(userId='me', q=query, maxResults=max_results).execute()
            )
            return response.get('messages', [])
        except GmailAuthException:
            return "TOKEN_EXPIRED_REAUTH_REQUIRED"
        except Exception as e:
            if self._is_auth_error(e):
                return "TOKEN_EXPIRED_REAUTH_REQUIRED"
            logger.error(f"Error fetching emails list for user {user_id}: {e}")
            return []

    async def get_unread_emails(self, user_id: int, limit: int = 5) -> Any:
        """
        Polles the inbox for unread message metadata.
        OPTIMIZED: Uses format='metadata' during background synchronization queries to completely 
        prevent parsing heavy email payloads and protect Render CPU bottlenecks.
        """
        try:
            service = await self.get_service(user_id)
            if not service:
                return "TOKEN_EXPIRED_REAUTH_REQUIRED"

            query = "is:unread newer_than:1d"
            response = await asyncio.to_thread(
                lambda: service.users().messages().list(userId='me', q=query, maxResults=limit).execute()
            )
            messages = response.get('messages', [])
            
            minimal_emails = []
            for msg in messages:
                try:
                    # Optimized Payload Polling via format='metadata' with specific headers
                    minimal_msg = await asyncio.to_thread(
                        lambda m_id=msg['id']: service.users().messages().get(
                            userId='me', id=m_id, format='metadata',
                            metadataHeaders=['From', 'Subject']
                        ).execute()
                    )
                    
                    headers = minimal_msg.get('payload', {}).get('headers', [])
                    subject = next((h['value'] for h in headers if h['name'].lower() == 'subject'), 'No Subject')
                    sender = next((h['value'] for h in headers if h['name'].lower() == 'from'), 'Unknown Sender')
                    internal_date = minimal_msg.get('internalDate', '0')

                    minimal_emails.append({
                        "id": msg['id'],
                        "sender": sender,
                        "subject": subject,
                        "snippet": minimal_msg.get('snippet', ''),
                        "internal_date": int(internal_date)
                    })
                except Exception as parse_err:
                    if self._is_auth_error(parse_err):
                        return "TOKEN_EXPIRED_REAUTH_REQUIRED"
                    logger.warning(f"Failed to fetch minimal schema for email {msg['id']}: {parse_err}")

            return minimal_emails
        except GmailAuthException:
            return "TOKEN_EXPIRED_REAUTH_REQUIRED"
        except Exception as e:
            if self._is_auth_error(e):
                return "TOKEN_EXPIRED_REAUTH_REQUIRED"
            logger.error(f"Error fetching unread emails for user {user_id}: {e}")
            return []

    async def search_emails(self, user_id: int, query: str, max_results: int = 5) -> Any:
        """
        Performs active searches in Gmail using advanced search filters.
        Intercepts expired OAuth sessions securely.
        """
        try:
            service = await self.get_service(user_id)
            if not service:
                return "TOKEN_EXPIRED_REAUTH_REQUIRED"
            
            response = await asyncio.to_thread(
                lambda: service.users().messages().list(userId='me', q=query, maxResults=max_results).execute()
            )
            messages = response.get('messages', [])
            
            results = []
            for msg in messages:
                details = await self.get_email_details(user_id, msg['id'])
                if details == "TOKEN_EXPIRED_REAUTH_REQUIRED":
                    return "TOKEN_EXPIRED_REAUTH_REQUIRED"
                if details:
                    results.append(details)
            return results
        except GmailAuthException:
            return "TOKEN_EXPIRED_REAUTH_REQUIRED"
        except Exception as e:
            if self._is_auth_error(e):
                return "TOKEN_EXPIRED_REAUTH_REQUIRED"
            logger.error(f"Error executing email search query '{query}' for user {user_id}: {e}")
            return []

    async def get_email_details(self, user_id: int, msg_id: str) -> Any:
        """
        Extracts raw MIME body and headers for complete email viewing.
        Handles authorization exceptions dynamically.
        """
        try:
            service = await self.get_service(user_id)
            if not service:
                return "TOKEN_EXPIRED_REAUTH_REQUIRED"

            msg = await asyncio.to_thread(
                lambda: service.users().messages().get(userId='me', id=msg_id, format='full').execute()
            )
            
            payload = msg.get('payload', {})
            headers = payload.get('headers', [])
            
            subject = next((h['value'] for h in headers if h['name'].lower() == 'subject'), 'No Subject')
            sender = next((h['value'] for h in headers if h['name'].lower() == 'from'), 'Unknown Sender')
            
            body = self._extract_body(payload)
            snippet = msg.get('snippet', '')
            
            # Truncate body for UI/API payload efficiency — full content is still
            # available for display, but prevents massive chain emails from
            # flooding AI context memory or Telegram message size limits.
            if len(body) > 4000:
                body = body[:4000] + "\n\n[... Truncated for UI presentation]"

            return {
                "id": msg_id,
                "sender": sender,
                "subject": subject,
                "snippet": snippet,
                "body": body
            }
        except GmailAuthException:
            return "TOKEN_EXPIRED_REAUTH_REQUIRED"
        except Exception as e:
            if self._is_auth_error(e):
                return "TOKEN_EXPIRED_REAUTH_REQUIRED"
            logger.error(f"Error retrieving email details for message {msg_id}: {e}")
            return None

    async def get_email_metadata(self, user_id: int, msg_id: str) -> Any:
        """
        Retrieves lightweight metadata (Headers, Sender, Subject, Attachments)
        without heavy payload loading overheads.
        """
        try:
            service = await self.get_service(user_id)
            if not service:
                return "TOKEN_EXPIRED_REAUTH_REQUIRED"

            msg = await asyncio.to_thread(
                lambda: service.users().messages().get(userId='me', id=msg_id, format='metadata', 
                                                       metadataHeaders=['From', 'Subject']).execute()
            )
            
            headers = msg.get('payload', {}).get('headers', [])
            subject = next((h['value'] for h in headers if h['name'].lower() == 'subject'), 'No Subject')
            sender = next((h['value'] for h in headers if h['name'].lower() == 'from'), 'Unknown Sender')
            
            full_msg = await asyncio.to_thread(
                lambda: service.users().messages().get(userId='me', id=msg_id, format='full').execute()
            )
            attachments = []
            payload = full_msg.get('payload', {})
            self._extract_attachments_metadata(payload, attachments)

            return {
                "id": msg_id,
                "sender": sender,
                "subject": subject,
                "attachments": attachments
            }
        except GmailAuthException:
            return "TOKEN_EXPIRED_REAUTH_REQUIRED"
        except Exception as e:
            if self._is_auth_error(e):
                return "TOKEN_EXPIRED_REAUTH_REQUIRED"
            logger.error(f"Error fetching email metadata for {msg_id}: {e}")
            return {"error": str(e)}

    def _extract_attachments_metadata(self, part: Dict[str, Any], attachments: List[Dict[str, Any]]) -> None:
        """Recursively parses email MIME parts to gather attachment metadata."""
        if 'parts' in part:
            for sub_part in part['parts']:
                self._extract_attachments_metadata(sub_part, attachments)
        else:
            filename = part.get('filename')
            body = part.get('body', {})
            attachment_id = body.get('attachmentId')
            if filename and attachment_id:
                attachments.append({
                    "id": attachment_id,
                    "filename": filename,
                    "size": body.get('size', 0)
                })

    def _extract_body(self, payload: Dict[str, Any]) -> str:
        """Recursively parses email boundaries to clean and isolate text bodies."""
        body_data = ""
        if 'parts' in payload:
            for part in payload['parts']:
                if part['mimeType'] == 'text/plain':
                    data = part['body'].get('data')
                    if data:
                        body_data += base64.urlsafe_b64decode(data).decode('utf-8')
                elif part['mimeType'] == 'text/html':
                    data = part['body'].get('data')
                    if data and not body_data:
                        body_data += base64.urlsafe_b64decode(data).decode('utf-8')
                elif 'parts' in part:
                    body_data += self._extract_body(part)
        else:
            data = payload.get('body', {}).get('data')
            if data:
                body_data = base64.urlsafe_b64decode(data).decode('utf-8')
                
        return body_data.strip()

    # ==========================================
    # EMAIL ATTACHMENT DOWNLOAD ENGINE
    # ==========================================

    async def get_attachments(self, user_id: int, msg_id: str) -> Any:
        """
        Downloads all attachments associated with a message ID to local temp directories.
        Returns a list of local file paths.
        """
        try:
            service = await self.get_service(user_id)
            if not service:
                return "TOKEN_EXPIRED_REAUTH_REQUIRED"

            msg = await asyncio.to_thread(
                lambda: service.users().messages().get(userId='me', id=msg_id, format='full').execute()
            )
            
            attachments_paths = []
            payload = msg.get('payload', {})
            await self._download_parts_attachments(user_id, service, msg_id, payload, attachments_paths)
            return attachments_paths
        except GmailAuthException:
            return "TOKEN_EXPIRED_REAUTH_REQUIRED"
        except Exception as e:
            if self._is_auth_error(e):
                return "TOKEN_EXPIRED_REAUTH_REQUIRED"
            logger.error(f"Failed to fetch attachments for message {msg_id}: {e}")
            return []

    async def _download_parts_attachments(self, user_id: int, service, msg_id: str, part: Dict[str, Any], paths: List[str]) -> None:
        """Recursively downloads file chunks from Gmail API matching MIME layout structures."""
        if 'parts' in part:
            for sub_part in part['parts']:
                await self._download_parts_attachments(user_id, service, msg_id, sub_part, paths)
        else:
            filename = part.get('filename')
            body = part.get('body', {})
            attachment_id = body.get('attachmentId')
            
            if filename and attachment_id:
                try:
                    attachment = await asyncio.to_thread(
                        lambda: service.users().messages().attachments().get(
                            userId='me', messageId=msg_id, id=attachment_id
                        ).execute()
                    )
                    
                    file_data = base64.urlsafe_b64decode(attachment.get('data', '').encode('utf-8'))
                    
                    temp_dir = tempfile.gettempdir()
                    file_path = os.path.join(temp_dir, f"att_{uuid.uuid4().hex}_{filename}")
                    
                    with open(file_path, 'wb') as f:
                        f.write(file_data)
                        
                    paths.append(file_path)
                    logger.info(f"Downloaded attachment: {filename} to {file_path}")
                except Exception as err:
                    logger.error(f"Failed to download specific attachment {filename}: {err}")

    # ==========================================
    # EMAIL MUTATION OPERATIONS
    # ==========================================

    async def delete_email(self, user_id: int, msg_id: str) -> Any:
        """Moves a specific email to the user's Gmail trash bin."""
        try:
            service = await self.get_service(user_id)
            if not service:
                return "TOKEN_EXPIRED_REAUTH_REQUIRED"
            await asyncio.to_thread(
                lambda: service.users().messages().trash(userId='me', id=msg_id).execute()
            )
            return True
        except GmailAuthException:
            return "TOKEN_EXPIRED_REAUTH_REQUIRED"
        except Exception as e:
            if self._is_auth_error(e):
                return "TOKEN_EXPIRED_REAUTH_REQUIRED"
            logger.error(f"Error trashing email {msg_id}: {e}")
            return False

    async def untrash_email(self, user_id: int, msg_id: str) -> Any:
        """Restores a specific email from the user's Gmail trash bin."""
        try:
            service = await self.get_service(user_id)
            if not service:
                return "TOKEN_EXPIRED_REAUTH_REQUIRED"
            await asyncio.to_thread(
                lambda: service.users().messages().untrash(userId='me', id=msg_id).execute()
            )
            return True
        except GmailAuthException:
            return "TOKEN_EXPIRED_REAUTH_REQUIRED"
        except Exception as e:
            if self._is_auth_error(e):
                return "TOKEN_EXPIRED_REAUTH_REQUIRED"
            logger.error(f"Error untrashing email {msg_id}: {e}")
            return False