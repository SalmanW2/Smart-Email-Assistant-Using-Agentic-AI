import base64
from datetime import datetime
from typing import Any, Dict, List, Optional
from email.mime.text import MIMEText
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from db.models import db_manager
from config import settings

class GmailClient:
    def __init__(self) -> None:
        self.db = db_manager

    async def _get_user(self, telegram_id: int) -> Optional[Dict[str, Any]]:
        return await self.db.get_user(telegram_id)

    async def _build_credentials(self, telegram_id: int) -> Optional[Credentials]:
        user = await self._get_user(telegram_id)
        if not user:
            return None

        auth_token = user.get("auth_token") or {}
        token = auth_token.get("token")
        if not token:
            return None

        expiry = None
        expires_at = auth_token.get("expires_at")
        if expires_at:
            expiry = datetime.fromisoformat(expires_at)

        creds = Credentials(
            token=token,
            refresh_token=auth_token.get("refresh_token"),
            token_uri=auth_token.get("token_uri", "https://oauth2.googleapis.com/token"),
            client_id=settings.GOOGLE_OAUTH_CLIENT_ID,
            client_secret=settings.GOOGLE_OAUTH_CLIENT_SECRET,
            scopes=auth_token.get("scopes"),
            expiry=expiry,
        )

        if creds.expired and creds.refresh_token:
            creds.refresh(Request())
            auth_token["token"] = creds.token
            auth_token["expires_at"] = creds.expiry.isoformat() if creds.expiry else None
            await self.db.upsert_user_token(telegram_id, user.get("email", ""), auth_token)

        return creds

    def _build_service(self, creds: Credentials):
        return build("gmail", "v1", credentials=creds)

    async def get_recent_emails(self, telegram_id: int, count: int = 5) -> List[Dict[str, Any]]:
        creds = await self._build_credentials(telegram_id)
        if not creds:
            return []

        try:
            service = self._build_service(creds)
            results = service.users().messages().list(userId="me", maxResults=count).execute()
            messages = results.get("messages", [])
            emails = []
            for msg in messages:
                message_data = service.users().messages().get(userId="me", id=msg["id"]).execute()
                emails.append(self._parse_email(message_data))
            return emails
        except HttpError:
            return []

    async def search_emails(self, telegram_id: int, query: str) -> List[Dict[str, Any]]:
        creds = await self._build_credentials(telegram_id)
        if not creds:
            return []

        try:
            service = self._build_service(creds)
            results = service.users().messages().list(userId="me", q=query, maxResults=10).execute()
            messages = results.get("messages", [])
            return [self._parse_email(service.users().messages().get(userId="me", id=msg["id"]).execute()) for msg in messages]
        except HttpError:
            return []

    def _parse_email(self, msg_data: Dict[str, Any]) -> Dict[str, Any]:
        headers = msg_data.get("payload", {}).get("headers", [])
        subject = next((item["value"] for item in headers if item["name"] == "Subject"), "")
        sender = next((item["value"] for item in headers if item["name"] == "From"), "")
        snippet = msg_data.get("snippet", "")
        return {
            "id": msg_data.get("id"),
            "thread_id": msg_data.get("threadId"),
            "subject": subject,
            "sender": sender,
            "snippet": snippet,
        }

    async def send_email(self, telegram_id: int, to: str, subject: str, body: str) -> bool:
        creds = await self._build_credentials(telegram_id)
        if not creds:
            return False

        message = MIMEText(body)
        message["to"] = to
        message["subject"] = subject
        raw = base64.urlsafe_b64encode(message.as_bytes()).decode()

        try:
            service = self._build_service(creds)
            service.users().messages().send(userId="me", body={"raw": raw}).execute()
            return True
        except HttpError:
            return False

    async def reply_email(self, telegram_id: int, thread_id: str, body: str) -> bool:
        creds = await self._build_credentials(telegram_id)
        if not creds:
            return False

        message = MIMEText(body)
        raw = base64.urlsafe_b64encode(message.as_bytes()).decode()

        try:
            service = self._build_service(creds)
            service.users().messages().send(userId="me", body={"raw": raw, "threadId": thread_id}).execute()
            return True
        except HttpError:
            return False

    async def delete_email(self, telegram_id: int, email_id: str) -> bool:
        creds = await self._build_credentials(telegram_id)
        if not creds:
            return False

        try:
            service = self._build_service(creds)
            service.users().messages().delete(userId="me", id=email_id).execute()
            return True
        except HttpError:
            return False

gmail_client = GmailClient()