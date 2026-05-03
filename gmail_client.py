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
        # NEW: Global array for AI voice attachments
        self.current_global_attachments = []

    def get_service(self):
        creds = self.auth.get_credentials()
        if creds and creds.valid:
            return build('gmail', 'v1', credentials=creds)
        return None

    def get_email_metadata(self, msg_id):
        service = self.get_service()
        msg = service.users().messages().get(userId='me', id=msg_id, format='metadata', metadataHeaders=['Subject', 'From']).execute()
        headers = msg.get('payload', {}).get('headers', [])
        subject = next((h['value'] for h in headers if h['name'] == 'Subject'), "No Subject")
        sender = next((h['value'] for h in headers if h['name'] == 'From'), "Unknown Sender")
        
        # Extract attachment names for notification
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
        
        # NEW: Text Cleaner to remove messy forum footers and dashes
        body = re.sub(r'-{3,}', '---', body) # Reduce huge dash lines
        body = re.sub(r'To reply click on this link:.*', '', body, flags=re.IGNORECASE | re.DOTALL)
        body = re.sub(r'Unsubscribe from this forum:.*', '', body, flags=re.IGNORECASE | re.DOTALL)
        body = os.linesep.join([s for s in body.splitlines() if s.strip()]) # Remove empty blank lines
        
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

    def send_email(self, to: str, subject: str, body: str, manual_attachments: list):
        service = self.get_service()
        if not service: return "❌ Authentication Required"
        try:
            message = MIMEMultipart()
            message['to'] = to
            message['subject'] = subject
            message.attach(MIMEText(body, 'plain'))

            # Combine manual upload and global AI memory uploads
            all_files = manual_attachments + self.current_global_attachments

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
            
            # Clean up all temp files
            for file_path in all_files:
                if os.path.exists(file_path): os.remove(file_path)
            self.current_global_attachments = []
            
            return "✅ Transmission Successful!"
        except Exception as e:
            return f"❌ Transmission Error: {str(e)}"

    def delete_email(self, msg_id):
        service = self.get_service()
        if not service: return False
        try:
            service.users().messages().trash(userId='me', id=msg_id).execute()
            return True
        except:
            return False