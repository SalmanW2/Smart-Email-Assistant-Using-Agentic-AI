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
    _token_cache: Dict[int, dict] = {}
    _user_locks: Dict[int, asyncio.Lock] = {}
    cache_hits: int = 0
    cache_misses: int = 0

    def __init__(self) -> None:
        """
        Initializes the Gmail Client.
        Tracks temporary in-memory attachments staged by the user before dispatch.
        """
        self.user_attachments: Dict[int, List[Dict[str, str]]] = {}

    def clear_cache(self, user_id: int) -> None:
        """Evicts a user's cached Google OAuth credentials."""
        self.__class__._token_cache.pop(user_id, None)

    def _is_auth_error(self, e: Exception) -> bool:
        """
        Determines if an exception is caused by revoked, invalid, or expired Google credentials.
        Processes standard HTTP statuses, RefreshErrors, and client auth failures.
        """
        err_str = str(e).lower()
        if isinstance(e, AttributeError) and "get" in err_str and "str" in err_str:
            return True
        if isinstance(e, TypeError) and "string indices must be integers" in err_str:
            return True
        if hasattr(e, "resp") and getattr(e.resp, "status", 200) in (401, 403):
            return True
        if "invalid_grant" in err_str or "unauthorized_client" in err_str or "token has been expired" in err_str or "token is invalid" in err_str or "authentication_error" in err_str:
            return True
        if "refresh" in err_str and ("fail" in err_str or "error" in err_str):
            return True
        return False

    async def _prompt_reauth(self, user_id: int) -> str:
        """Generates a secure re-authentication redirect message for Telegram."""
        return "⚠️ *Authentication Expired:* Your Google account access is invalid or expired. Please go to '⚙️ Settings', click **Logout Account**, and reconnect your account."

    async def get_service(self, user_id: int) -> Optional[Any]:
        """
        Builds the authenticated Gmail service object.
        Intercepts expired tokens and attempts an automatic, proactive credentials refresh.
        Raises GmailAuthException if refresh fails or tokens are missing.
        """
        # Secure the refresh logic per-user to prevent parallel search race conditions
        if user_id not in self.__class__._user_locks:
            self.__class__._user_locks[user_id] = asyncio.Lock()
            
        async with self.__class__._user_locks[user_id]:
            try:
                from datetime import datetime, timezone, timedelta
                
                # Check RAM cache first
                token_data = self.__class__._token_cache.get(user_id)
                cached_valid = False
                
                if token_data:
                    expires_at = token_data.get("expires_at")
                    if expires_at:
                        try:
                            if expires_at.endswith("Z"):
                                expires_at = expires_at[:-1] + "+00:00"
                            dt = datetime.fromisoformat(expires_at)
                            if dt.tzinfo is None:
                                dt = dt.replace(tzinfo=timezone.utc)
                            else:
                                dt = dt.astimezone(timezone.utc)
                            
                            # Cache is valid if expiration is in the future beyond 5 minutes
                            if dt > datetime.now(timezone.utc) + timedelta(minutes=5):
                                cached_valid = True
                        except ValueError:
                            pass
                
                if cached_valid and token_data:
                    self.__class__.cache_hits += 1
                else:
                    self.__class__.cache_misses += 1
                    user = await db_manager.get_user(user_id)
                    if not user or not user.get('auth_token'):
                        raise GmailAuthException("User lacks Google Authentication context")
                    
                    token_data = user['auth_token']
                    self.__class__._token_cache[user_id] = token_data
                
                # Handle potential string-serialized JSON from DB
                if isinstance(token_data, str):
                    import json
                    try:
                        token_data = json.loads(token_data)
                    except json.JSONDecodeError:
                        raise GmailAuthException("TOKEN_EXPIRED_REAUTH_REQUIRED")

                # Safely parse expires_at to a timezone-aware UTC datetime object
                expiry = None
                expires_at = token_data.get("expires_at")
                needs_refresh = False

                if expires_at:
                    try:
                        if expires_at.endswith("Z"):
                            expires_at = expires_at[:-1] + "+00:00"
                        dt = datetime.fromisoformat(expires_at)
                        if dt.tzinfo is None:
                            dt = dt.replace(tzinfo=timezone.utc)
                        else:
                            dt = dt.astimezone(timezone.utc)
                    
                        # Convert to naive for google-auth compatibility
                        expiry = dt.replace(tzinfo=None)
                    
                        # Implement strict 5-minute safety buffer
                        if datetime.now(timezone.utc) + timedelta(seconds=300) >= dt:
                            needs_refresh = True
                    except Exception as parse_err:
                        logger.warning(f"Failed to parse expires_at timestamp '{expires_at}' for user {user_id}: {parse_err}")
                        needs_refresh = True
                else:
                    needs_refresh = True

                credentials = Credentials(
                    token=token_data.get("token"),
                    refresh_token=token_data.get("refresh_token"),
                    token_uri=token_data.get("token_uri"),
                    client_id=token_data.get("client_id"),
                    client_secret=token_data.get("client_secret"),
                    scopes=token_data.get("scopes"),
                    expiry=expiry
                )

                # Proactively refresh the access token if expired or within 5-min buffer
                if (credentials.expired or needs_refresh) and credentials.refresh_token:
                    try:
                        logger.info(f"Proactively refreshing Google OAuth token for user {user_id}")
                        await asyncio.to_thread(credentials.refresh, GoogleRequest())
                    
                        # Persist only if the token actually changed to prevent needless DB loops
                        if credentials.token and credentials.token != token_data.get("token"):
                            new_expiry_str = None
                            if credentials.expiry:
                                expiry_aware = credentials.expiry.replace(tzinfo=timezone.utc)
                                new_expiry_str = expiry_aware.isoformat()
                        
                            updated_token_data = {
                                **token_data, 
                                "token": credentials.token,
                                "expires_at": new_expiry_str
                            }
                            await db_manager.db.run(
                                lambda: db_manager.db.client.table("users")
                                .update({"auth_token": updated_token_data})
                                .eq("telegram_id", user_id).execute()
                            )
                            logger.info(f"Refreshed token successfully saved to Supabase for user {user_id}")
                            token_data = updated_token_data
                    except Exception as refresh_err:
                        logger.error(f"Failed auto-refreshing OAuth token for user {user_id}: {refresh_err}")
                        self.clear_cache(user_id)
                        raise GmailAuthException("TOKEN_EXPIRED_REAUTH_REQUIRED")

                # Update/populate the RAM cache
                self.__class__._token_cache[user_id] = token_data

                # Build the discovery service
                service = await asyncio.to_thread(build, 'gmail', 'v1', credentials=credentials, cache_discovery=False)
                return service
            except GmailAuthException as auth_e:
                self.clear_cache(user_id)
                raise auth_e
            except Exception as e:
                if self._is_auth_error(e):
                    self.clear_cache(user_id)
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
                self.clear_cache(user_id)
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
            self.clear_cache(user_id)
            return "TOKEN_EXPIRED_REAUTH_REQUIRED"
        except Exception as e:
            if self._is_auth_error(e):
                self.clear_cache(user_id)
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
                        self.clear_cache(user_id)
                        return "TOKEN_EXPIRED_REAUTH_REQUIRED"
                    logger.warning(f"Failed to fetch minimal schema for email {msg['id']}: {parse_err}")

            return minimal_emails
        except GmailAuthException:
            self.clear_cache(user_id)
            return "TOKEN_EXPIRED_REAUTH_REQUIRED"
        except Exception as e:
            if self._is_auth_error(e):
                self.clear_cache(user_id)
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
            self.clear_cache(user_id)
            return "TOKEN_EXPIRED_REAUTH_REQUIRED"
        except Exception as e:
            if self._is_auth_error(e):
                self.clear_cache(user_id)
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
            date_str = next((h['value'] for h in headers if h['name'].lower() == 'date'), 'Unknown Date')
            
            body = self._extract_body(payload)
            snippet = msg.get('snippet', '')
            thread_id = msg.get('threadId', '')
            
            def check_attach(p):
                return bool(p.get('filename')) or any(check_attach(sp) for sp in p.get('parts', []))
            has_attachment = check_attach(payload)
            
            # Truncate body for UI/API payload efficiency — full content is still
            # available for display, but prevents massive chain emails from
            # flooding AI context memory or Telegram message size limits.
            if len(body) > 4000:
                body = body[:4000] + "\n\n[... Truncated for UI presentation]"

            return {
                "id": msg_id,
                "threadId": thread_id,
                "sender": sender,
                "subject": subject,
                "date": date_str,
                "snippet": snippet,
                "body": body,
                "has_attachment": has_attachment
            }
        except GmailAuthException:
            self.clear_cache(user_id)
            return "TOKEN_EXPIRED_REAUTH_REQUIRED"
        except HttpError as e:
            if e.resp.status == 404:
                logger.warning(f"Email details not found (404) for message {msg_id}.")
                return None
            logger.error(f"Error retrieving email details for message {msg_id}: {e}")
            return None
        except Exception as e:
            if self._is_auth_error(e):
                self.clear_cache(user_id)
                return "TOKEN_EXPIRED_REAUTH_REQUIRED"
            logger.error(f"Error retrieving email details for message {msg_id}: {e}")
            return None

    async def get_email_html(self, user_id: int, msg_id: str) -> Any:
        """
        Retrieves the complete, un-truncated HTML body of an email.
        """
        try:
            service = await self.get_service(user_id)
            if not service:
                return "TOKEN_EXPIRED_REAUTH_REQUIRED"

            msg = await asyncio.to_thread(
                lambda: service.users().messages().get(userId='me', id=msg_id, format='full').execute()
            )
            
            payload = msg.get('payload', {})
            
            # Extract HTML body recursively without truncation
            def _extract_full_html(part: Dict[str, Any]) -> str:
                html_data = ""
                if 'parts' in part:
                    for sub_part in part['parts']:
                        if sub_part['mimeType'] == 'text/html':
                            data = sub_part['body'].get('data')
                            if data:
                                html_data += base64.urlsafe_b64decode(data).decode('utf-8')
                        elif 'parts' in sub_part:
                            html_data += _extract_full_html(sub_part)
                else:
                    if part.get('mimeType') == 'text/html':
                        data = part.get('body', {}).get('data')
                        if data:
                            html_data = base64.urlsafe_b64decode(data).decode('utf-8')
                return html_data

            html_body = _extract_full_html(payload)
            
            # Fallback to plain text body if HTML is not found
            if not html_body:
                html_body = self._extract_body(payload)
                
            return html_body
        except GmailAuthException:
            self.clear_cache(user_id)
            return "TOKEN_EXPIRED_REAUTH_REQUIRED"
        except Exception as e:
            if self._is_auth_error(e):
                self.clear_cache(user_id)
                return "TOKEN_EXPIRED_REAUTH_REQUIRED"
            logger.error(f"Error fetching full email HTML for {msg_id}: {e}")
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
            self.clear_cache(user_id)
            return "TOKEN_EXPIRED_REAUTH_REQUIRED"
        except HttpError as e:
            if e.resp.status == 404:
                logger.warning(f"Email metadata not found (404) for message {msg_id}.")
                return None
            logger.error(f"Error fetching email metadata for {msg_id}: {e}")
            return {"error": str(e)}
        except Exception as e:
            if self._is_auth_error(e):
                self.clear_cache(user_id)
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
                
        if body_data and '<' in body_data and '>' in body_data:
            try:
                from bs4 import BeautifulSoup
                soup = BeautifulSoup(body_data, 'html.parser')
                for tag in soup(["style", "script"]):
                    tag.decompose()
                body_data = soup.get_text(separator='\n', strip=True)
            except ImportError:
                pass

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
            self.clear_cache(user_id)
            return "TOKEN_EXPIRED_REAUTH_REQUIRED"
        except Exception as e:
            if self._is_auth_error(e):
                self.clear_cache(user_id)
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
                        
                    paths.append({"path": file_path, "original_filename": filename})
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
            self.clear_cache(user_id)
            return "TOKEN_EXPIRED_REAUTH_REQUIRED"
        except Exception as e:
            if self._is_auth_error(e):
                self.clear_cache(user_id)
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
            self.clear_cache(user_id)
            return "TOKEN_EXPIRED_REAUTH_REQUIRED"
        except Exception as e:
            if self._is_auth_error(e):
                self.clear_cache(user_id)
                return "TOKEN_EXPIRED_REAUTH_REQUIRED"
            logger.error(f"Error untrashing email {msg_id}: {e}")
            return False