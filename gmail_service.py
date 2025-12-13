import os
import base64
from email.message import EmailMessage
from email import message_from_bytes
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

from config_env import SCOPES, CREDENTIALS_FILE, TOKEN_FILE

def get_gmail_service():
    """Authentication aur Login handle karta hai."""
    creds = None
    if os.path.exists(TOKEN_FILE):
        try:
            creds = Credentials.from_authorized_user_file(TOKEN_FILE, SCOPES)
        except:
            creds = None

    # Agar credentials expire ho gaye hain ya nahi hain
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            try:
                from google.auth.transport.requests import Request
                creds.refresh(Request())
            except:
                creds = None
        
        if not creds:
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
    """Inbox ki sabse nayi email lata hai."""
    try:
        service = get_gmail_service()
        results = service.users().messages().list(
            userId="me", labelIds=["INBOX"], maxResults=1
        ).execute()
        
        messages = results.get("messages", [])
        if not messages:
            return "📭 Inbox khali hai. Koi email nahi mili."

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
                if part.get_content_type() == "text/plain":
                    body = part.get_payload(decode=True).decode(errors="ignore")
                    break
        else:
            body = mime_msg.get_payload(decode=True).decode(errors="ignore")

        # Telegram limit 4096 chars hoti hai, isliye hum body cut kar rahe hain
        return f"📧 **From:** {sender}\n**Subject:** {subject}\n\n{body[:1000]}..."
    except Exception as e:
        return f"❌ Error: {str(e)}"

def create_and_send_email(to_email, subject, body_content):
    """Email Bhejne ka function."""
    try:
        service = get_gmail_service()
        
        message = EmailMessage()
        message.set_content(body_content)
        message['To'] = to_email
        message['From'] = 'me'
        message['Subject'] = subject

        encoded_message = base64.urlsafe_b64encode(message.as_bytes()).decode()
        create_message = {'raw': encoded_message}

        sent_msg = (service.users().messages().send(userId="me", body=create_message).execute())
        return f"✅ Email Successfully Sent! (ID: {sent_msg['id']})"
    except HttpError as error:
        return f"❌ Gmail Error: {error}"
    except Exception as e:
        return f"❌ Unknown Error: {e}"