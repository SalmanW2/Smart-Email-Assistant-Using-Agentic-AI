import os
import base64
import mimetypes
from googleapiclient.discovery import build
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.base import MIMEBase
from email import encoders

class GmailClient:
    def __init__(self, auth_manager):
        self.auth = auth_manager
        self.current_attachment = None

    def get_service(self):
        creds = self.auth.get_credentials()
        if creds and creds.valid:
            return build('gmail', 'v1', credentials=creds)
        return None

    def search_emails(self, query: str = 'label:INBOX', max_results: int = 5):
        """
        Searches the user's Gmail inbox using specialized search queries. 
        Parameters: query (standard Gmail search syntax), max_results (integer count).
        """
        service = self.get_service()
        if not service: return "❌ Authentication required."
        try:
            results = service.users().messages().list(userId='me', q=query, maxResults=max_results).execute()
            messages = results.get('messages', [])
            if not messages: return "📭 No relevant emails found."
            
            summary = []
            for m in messages:
                data = self.get_email_metadata(m['id'])
                summary.append(f"📧 ID: {m['id']} \n👤 From: {data['sender']} \n📝 Subject: {data['subject']}\n")
            return "\n".join(summary)
        except Exception as e:
            return f"❌ Search failure: {str(e)}"

    def get_email_metadata(self, msg_id):
        service = self.get_service()
        msg = service.users().messages().get(userId='me', id=msg_id, format='metadata', metadataHeaders=['Subject', 'From']).execute()
        headers = msg.get('payload', {}).get('headers', [])
        subject = next((h['value'] for h in headers if h['name'] == 'Subject'), "No Subject")
        sender = next((h['value'] for h in headers if h['name'] == 'From'), "Unknown Sender")
        return {"id": msg_id, "subject": subject, "sender": sender}

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
             
        return body[:3000] if body else "No text content identified."

    def send_email(self, to: str, subject: str, body: str):
        """
        Transmits a new email message to the specified recipient. 
        Automatically attaches files stored in the temporary system buffer.
        """
        service = self.get_service()
        if not service: return "❌ Authentication Required"
        try:
            message = MIMEMultipart()
            message['to'] = to
            message['subject'] = subject
            message.attach(MIMEText(body, 'plain'))

            if self.current_attachment and os.path.exists(self.current_attachment):
                content_type, encoding = mimetypes.guess_type(self.current_attachment)
                if content_type is None or encoding is not None:
                    content_type = 'application/octet-stream'
                main_type, sub_type = content_type.split('/', 1)

                with open(self.current_attachment, 'rb') as fp:
                    msg_file = MIMEBase(main_type, sub_type)
                    msg_file.set_payload(fp.read())
                encoders.encode_base64(msg_file)
                filename = os.path.basename(self.current_attachment)
                msg_file.add_header('Content-Disposition', 'attachment', filename=filename)
                message.attach(msg_file)

            raw = base64.urlsafe_b64encode(message.as_bytes()).decode()
            service.users().messages().send(userId='me', body={'raw': raw}).execute()
            return "✅ Transmission Successful!"
        except Exception as e:
            return f"❌ Transmission Error: {str(e)}"
        finally:
            if self.current_attachment and os.path.exists(self.current_attachment):
                os.remove(self.current_attachment)
                self.current_attachment = None

    def delete_email(self, msg_id):
        service = self.get_service()
        if not service: return False
        try:
            service.users().messages().trash(userId='me', id=msg_id).execute()
            return True
        except:
            return False
