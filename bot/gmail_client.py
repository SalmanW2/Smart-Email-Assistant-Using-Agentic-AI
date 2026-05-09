import os
import base64
import mimetypes
import re
from googleapiclient.discovery import build
from google.oauth2.credentials import Credentials
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.base import MIMEBase
from email import encoders
from db.models import DBManager

class GmailClient:
    def __init__(self):
        self.user_attachments = {} 
        self.pending_ai_sends = {}

    def get_service(self, telegram_id: int):
        """Fetches dynamic credentials from the Database for Multi-Tenant Support."""
        user = DBManager.get_user(telegram_id)
        if not user or not user.get("auth_token"):
            return None
            
        token_data = user["auth_token"]
        creds = Credentials(
            token=token_data.get("token"),
            refresh_token=token_data.get("refresh_token"),
            token_uri=token_data.get("token_uri"),
            client_id=token_data.get("client_id"),
            client_secret=token_data.get("client_secret"),
            scopes=token_data.get("scopes")
        )
        
        if creds and creds.valid:
            return build('gmail', 'v1', credentials=creds)
        return None

    def get_email_metadata(self, telegram_id: int, msg_id: str):
        service = self.get_service(telegram_id)
        if not service: return {"error": "Authentication Required"}
        
        msg = service.users().messages().get(userId='me', id=msg_id, format='metadata', metadataHeaders=['Subject', 'From']).execute()
        headers = msg.get('payload', {}).get('headers', [])
        subject = next((h['value'] for h in headers if h['name'] == 'Subject'), "No Subject")
        sender = next((h['value'] for h in headers if h['name'] == 'From'), "Unknown Sender")
        
        parts = msg.get('payload', {}).get('parts', [])
        attachments = [p['filename'] for p in parts if p.get('filename')]
        
        return {"id": msg_id, "subject": subject, "sender": sender, "attachments": attachments}

    def get_full_body(self, telegram_id: int, msg_id: str):
        service = self.get_service(telegram_id)
        if not service: return "❌ Authentication Required"
        
        msg = service.users().messages().get(userId='me', id=msg_id, format='full').execute()
        payload = msg.get('payload', {})
        
        def extract_text(part):
            body = ""
            if part.get('mimeType') == 'text/plain':
                data = part.get('body', {}).get('data')
                if data:
                    body = base64.urlsafe_b64decode(data).decode('utf-8')
            elif 'parts' in part:
                for p in part['parts']:
                    body += extract_text(p)
            return body

        body = extract_text(payload)
        if not body and 'body' in payload and 'data' in payload['body']:
             body = base64.urlsafe_b64decode(payload['body']['data']).decode('utf-8')
             
        if not body: return "No text content identified."
        
        body = re.sub(r'-{3,}', '---', body)
        body = re.sub(r'To reply click on this link:.*', '', body, flags=re.IGNORECASE | re.DOTALL)
        body = os.linesep.join([s for s in body.splitlines() if s.strip()]) 
        
        return body[:3000]

    def queue_ai_email(self, telegram_id: int, to: str, subject: str, body: str):
        """Temporarily holds the AI email in memory to allow an Undo window."""
        self.pending_ai_sends[telegram_id] = {'to': to, 'subj': subject, 'body': body}
        return "Email queued successfully. It will be sent in 4 seconds unless the user clicks Undo."

    def send_email(self, telegram_id: int, to: str, subject: str, body: str, manual_attachments: list = None):
        service = self.get_service(telegram_id)
        if not service: return "❌ Error: Authentication Required."
        manual_attachments = manual_attachments or []
        
        try:
            message = MIMEMultipart()
            message['to'] = to
            message['subject'] = subject
            message.attach(MIMEText(body, 'plain'))

            # Handle Attachments
            global_atts = self.user_attachments.get(telegram_id, [])
            all_files = manual_attachments + global_atts

            for file_path in all_files:
                if os.path.exists(file_path):
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

            raw = base64.urlsafe_b64encode(message.as_bytes()).decode()
            service.users().messages().send(userId='me', body={'raw': raw}).execute()
            
            # Cleanup
            for file_path in all_files:
                if os.path.exists(file_path): os.remove(file_path)
            self.user_attachments[telegram_id] = []
            
            return "✅ Email transmitted successfully."
        except Exception as e:
            return f"❌ Transmission Error: ({str(e)})"

    def delete_email(self, telegram_id: int, msg_id: str):
        service = self.get_service(telegram_id)
        if not service: return False
        try:
            service.users().messages().trash(userId='me', id=msg_id).execute()
            return True
        except: return False