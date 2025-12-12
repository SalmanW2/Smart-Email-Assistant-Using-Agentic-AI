import os
import base64
from email import message_from_bytes
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

from config_env import SCOPES, CREDENTIALS_FILE, TOKEN_FILE


def get_gmail_service():
    creds = None

    if os.path.exists(TOKEN_FILE):
        try:
            creds = Credentials.from_authorized_user_file(TOKEN_FILE, SCOPES)
        except:
            creds = None

    if not creds or not creds.valid or not creds.refresh_token:
        if os.path.exists(TOKEN_FILE):
            os.remove(TOKEN_FILE)

        flow = InstalledAppFlow.from_client_secrets_file(
            CREDENTIALS_FILE, SCOPES
        )
        creds = flow.run_local_server(port=8080, prompt="consent")

        with open(TOKEN_FILE, "w") as token:
            token.write(creds.to_json())

    return build("gmail", "v1", credentials=creds)


def get_last_email():
    service = get_gmail_service()

    results = service.users().messages().list(
        userId="me",
        labelIds=["INBOX"],
        maxResults=1
    ).execute()

    messages = results.get("messages", [])

    if not messages:
        return "📭 No emails found."

    msg_id = messages[0]["id"]
    message = service.users().messages().get(
        userId="me", id=msg_id, format="raw"
    ).execute()

    msg_str = base64.urlsafe_b64decode(message["raw"].encode("ASCII"))
    mime_msg = message_from_bytes(msg_str)

    sender = mime_msg["From"]
    subject = mime_msg["Subject"]

    body = ""

    if mime_msg.is_multipart():
        for part in mime_msg.walk():
            ctype = part.get_content_type()
            disp = str(part.get("Content-Disposition"))

            if ctype == "text/plain" and "attachment" not in disp:
                body = part.get_payload(decode=True).decode(errors="ignore")
                break

            elif ctype == "text/html" and "attachment" not in disp:
                body = part.get_payload(decode=True).decode(errors="ignore")
                break
    else:
        body = mime_msg.get_payload(decode=True).decode(errors="ignore")

    return f"From: {sender}\nSubject: {subject}\n\n{body}"