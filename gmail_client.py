import os
import base64
import mimetypes
import re
from googleapiclient.discovery import build
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.base import MIMEBase
from email import encoders

class GmailClient:
    def __init__(self, auth_manager):
        self.auth = auth_manager
        # Dictionary isolating attachments securely per user session
        self.user_attachments = {} 

    def get_service(self):
        creds = self.auth.get_credentials()
        if creds and creds.valid:
            return build('gmail', 'v1', credentials=creds)
        return None

    def add_user_attachment(self, user_id: str, file_path: str):
        if user_id not in self.user_attachments:
            self.user_attachments[user_id] = []
        self.user_attachments[user_id].append(file_path)

    def get_user_attachments(self, user_id: str):
        return self.user_attachments.get(user_id, [])

    def clear_user_attachments(self, user_id: str):
        for fp in self.user_attachments.get(user_id, []):
            if os.path.exists(fp):
                os.remove(fp)
        self.user_attachments[user_id] = []

    def get_email_metadata(self, msg_id):
        service = self.get_service()
        msg = service.users().messages().get(userId='me', id=msg_id, format='metadata', metadataHeaders=['Subject', 'From']).execute()
        headers = msg.get('payload', {}).get('headers', [])
        subject = next((h['value'] for h in headers if h['name'] == 'Subject'), "No Subject")
        sender = next((h['value'] for h in headers if h['name'] == 'From'), "Unknown Sender")
        
        parts = msg.get('payload', {}).get('parts', [])
        attachments = [p['filename'] for p in parts if p.get('filename')]
        
        return {"id": msg_id, "subject": subject, "sender": sender, "attachments": attachments}

    def get_full_body(self, msg_id):
        service = self.get_service()
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
        body = re.sub(r'Unsubscribe from this forum:.*', '', body, flags=re.IGNORECASE | re.DOTALL)
        body = os.linesep.join([s for s in body.splitlines() if s.strip()]) 
        
        return body[:3000]

    def get_attachments(self, msg_id):
        service = self.get_service()
        if not service: return []
        
        try:
            msg = service.users().messages().get(userId='me', id=msg_id).execute()
            payload = msg.get('payload', {})
            attachments = []

            def extract_parts(parts):
                for part in parts:
                    if part.get('filename') and part.get('body', {}).get('attachmentId'):
                        att_id = part['body']['attachmentId']
                        att = service.users().messages().attachments().get(
                            userId='me', messageId=msg_id, id=att_id).execute()
                        data = att.get('data')
                        if data:
                            file_data = base64.urlsafe_b64decode(data)
                            file_path = f"/tmp/{part['filename']}"
                            with open(file_path, 'wb') as f:
                                f.write(file_data)
                            attachments.append(file_path)
                    if 'parts' in part:
                        extract_parts(part['parts'])

            if 'parts' in payload:
                extract_parts(payload['parts'])
                
            return attachments
        except:
            return []

    def send_email(self, to: str, subject: str, body: str, manual_attachments: list, user_id: str = None):
        service = self.get_service()
        if not service: return "❌ Error: Authentication Required."
        try:
            message = MIMEMultipart()
            message['to'] = to
            message['subject'] = subject
            message.attach(MIMEText(body, 'plain'))

            global_atts = self.get_user_attachments(user_id) if user_id else []
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
            
            # Auto-purge RAM and Disk after sending successfully
            for file_path in manual_attachments:
                if os.path.exists(file_path): os.remove(file_path)
            if user_id:
                self.clear_user_attachments(user_id)
            
            return "✅ Email transmitted successfully."
        except Exception as e:
            return f"❌ Transmission Error: Please check the format of the email address or content. ({str(e)})"

    def delete_email(self, msg_id):
        service = self.get_service()
        if not service: return False
        try:
            service.users().messages().trash(userId='me', id=msg_id).execute()
            return True
        except:
            return False