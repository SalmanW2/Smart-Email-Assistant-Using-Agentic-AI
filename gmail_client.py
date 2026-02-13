import base64
from googleapiclient.discovery import build
from email.mime.text import MIMEText

class GmailClient:
    def __init__(self, auth_manager):
        self.auth = auth_manager

    def get_service(self):
        creds = self.auth.get_credentials()
        if creds and creds.valid:
            return build('gmail', 'v1', credentials=creds)
        return None

    def list_emails(self, query='label:INBOX', max_results=5):
        service = self.get_service()
        if not service: return []
        results = service.users().messages().list(userId='me', q=query, maxResults=max_results).execute()
        return results.get('messages', [])

    def get_email_content(self, msg_id):
        service = self.get_service()
        if not service: return None
        msg = service.users().messages().get(userId='me', id=msg_id, format='full').execute()
        
        payload = msg['payload']
        headers = payload.get('headers', [])
        subject = next((h['value'] for h in headers if h['name'] == 'Subject'), "No Subject")
        sender = next((h['value'] for h in headers if h['name'] == 'From'), "Unknown")
        
        body = ""
        if 'parts' in payload:
            for part in payload['parts']:
                if part['mimeType'] == 'text/plain':
                    data = part['body'].get('data', '')
                    body = base64.urlsafe_b64decode(data).decode()
        elif 'body' in payload:
            data = payload['body'].get('data', '')
            body = base64.urlsafe_b64decode(data).decode()
            
        return {'id': msg_id, 'sender': sender, 'subject': subject, 'body': body or msg.get('snippet', '')}

    def send_email(self, to, subject, body):
        service = self.get_service()
        if not service: return "❌ Login Required"
        try:
            message = MIMEText(body)
            message['to'] = to
            message['subject'] = subject
            raw = base64.urlsafe_b64encode(message.as_bytes()).decode()
            service.users().messages().send(userId='me', body={'raw': raw}).execute()
            return "✅ Email Sent!"
        except Exception as e:
            return f"❌ Send Error: {str(e)}"