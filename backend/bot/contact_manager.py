from db.contacts import contact_manager
from typing import List, Dict, Any, Optional
import re

class ContactManager:
    def __init__(self):
        self.db = contact_manager

    async def extract_contacts_from_text(self, user_id: str, text: str):
        # Extract emails
        email_pattern = r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b'
        emails = re.findall(email_pattern, text)
        
        for email in emails:
            name = self.extract_name_from_context(text, email)
            await self.db.save_contact(user_id, name, email)

    def extract_name_from_context(self, text: str, email: str) -> str:
        # Simple name extraction - look for words before email
        words = text.split()
        email_index = words.index(email) if email in words else -1
        if email_index > 0:
            return words[email_index - 1].title()
        return email.split('@')[0].replace('.', ' ').title()

    async def resolve_contact(self, user_id: str, identifier: str) -> Optional[str]:
        # Resolve name or partial email to full email
        if '@' in identifier:
            contact = await self.db.get_contact_by_email(user_id, identifier)
            return contact['email'] if contact else identifier
        
        # Search by name
        contacts = await self.db.search_contacts(user_id, identifier)
        if contacts:
            return contacts[0]['email']
        
        return None

    async def get_contact_suggestions(self, user_id: str, prefix: str) -> List[str]:
        contacts = await self.db.search_contacts(user_id, prefix)
        return [f"{c['name']} ({c['email']})" for c in contacts[:5]]

contact_manager_instance = ContactManager()