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

    def search_emails(self, query: str):
        """Tool to search emails based on a query (e.g., 'from:Ghous'). Returns simple text."""
        service = self.get_service()
        if not service: return "Login required."
        try:
            results = service.users().messages().list(userId='me', q=query, maxResults=3).execute()
            messages = results.get('messages', [])
            if not messages: return "No emails found."
            
            summary = []
            for m in messages:
                data = self.get_email_content(m['id'])
                summary.append(f"From: {data['sender']}, Subject: {data['subject']}, Snippet: {data['body'][:100]}")
            return "\n".join(summary)
        except Exception as e:
            return f"Search error: {str(e)}"

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
            if data:
                body = base64.urlsafe_b64decode(data).decode()
            
        return {'id': msg_id, 'sender': sender, 'subject': subject, 'body': body or msg.get('snippet', '')}

    def get_last_email_from_sender(self, sender_email):
        service = self.get_service()
        if not service: return None
        results = service.users().messages().list(userId='me', q=f"from:{sender_email}", maxResults=1).execute()
        messages = results.get('messages', [])
        if not messages: return None
        return self.get_email_content(messages[0]['id'])

    def send_email(self, to: str, subject: str, body: str):
        """Tool to physically send an email. Must only be called after user confirms."""
        service = self.get_service()
        if not service: return "Login Required"
        try:
            message = MIMEText(body)
            message['to'] = to
            message['subject'] = subject
            raw = base64.urlsafe_b64encode(message.as_bytes()).decode()
            service.users().messages().send(userId='me', body={'raw': raw}).execute()
            return "Email Sent Successfully!"
        except Exception as e:
            return f"Send Error: {str(e)}"

    def delete_email(self, msg_id):
        service = self.get_service()
        if not service: return False
        try:
            service.users().messages().trash(userId='me', id=msg_id).execute()
            return True
        except:
            return False
