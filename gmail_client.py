from googleapiclient.discovery import build
import base64

class GmailClient:
    def __init__(self, auth_manager):
        self.auth = auth_manager

    def get_service(self):
        creds = self.auth.get_credentials()
        if creds:
            return build('gmail', 'v1', credentials=creds)
        return None

    def get_email_metadata(self, msg_id):
        # AI Token Saving: Sirf Headers aur file names la raha hai
        service = self.get_service()
        msg = service.users().messages().get(userId='me', id=msg_id, format='metadata', metadataHeaders=['Subject', 'From']).execute()
        
        headers = msg.get('payload', {}).get('headers', [])
        subject = next((h['value'] for h in headers if h['name'] == 'Subject'), "No Subject")
        sender = next((h['value'] for h in headers if h['name'] == 'From'), "Unknown Sender")
        
        # Attachment check logic
        full_msg = service.users().messages().get(userId='me', id=msg_id, format='full').execute()
        attachments = []
        if 'parts' in full_msg.get('payload', {}):
            for part in full_msg['payload']['parts']:
                if part.get('filename'):
                    attachments.append(part['filename'])
        
        return {"id": msg_id, "subject": subject, "sender": sender, "attachments": attachments}

    def get_full_body(self, msg_id):
        # Sirf tab chalega jab AI ko summary banani ho
        service = self.get_service()
        msg = service.users().messages().get(userId='me', id=msg_id, format='full').execute()
        parts = msg.get('payload', {}).get('parts', [])
        body = "No text content found."
        for part in parts:
            if part.get('mimeType') == 'text/plain':
                data = part.get('body', {}).get('data')
                if data:
                    body = base64.urlsafe_b64decode(data).decode('utf-8')
                    break
        return body[:3000] # Truncate to save tokens

    def delete_email(self, msg_id):
        service = self.get_service()
        service.users().messages().trash(userId='me', id=msg_id).execute()
        return True
        
