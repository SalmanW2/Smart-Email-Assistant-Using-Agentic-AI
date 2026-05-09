import re
from typing import List, Dict, Any, Optional
from db.contacts import contact_manager

class ContactManager:
    def __init__(self) -> None:
        self.db = contact_manager

    async def extract_contacts_from_text(self, telegram_id: int, text: str) -> None:
        email_pattern = r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b"
        emails = re.findall(email_pattern, text)
        for email in emails:
            name = self.extract_name_from_context(text, email)
            await self.db.save_contact(telegram_id, email_address=email, contact_name=name)

    def extract_name_from_context(self, text: str, email: str) -> str:
        words = text.replace("\n", " ").split()
        if email in words:
            email_index = words.index(email)
            if email_index > 0:
                return words[email_index - 1].replace('.', ' ').title()
        return email.split('@')[0].replace('.', ' ').title()

    async def resolve_contact(self, telegram_id: int, identifier: str) -> Optional[str]:
        if '@' in identifier:
            contact = await self.db.get_contact_by_email(telegram_id, identifier)
            return contact["email_address"] if contact else identifier

        contacts = await self.db.search_contacts(telegram_id, identifier)
        if contacts:
            return contacts[0]["email_address"]
        return None

    async def get_contact_suggestions(self, telegram_id: int, prefix: str) -> List[str]:
        contacts = await self.db.search_contacts(telegram_id, prefix)
        return [f"{contact.get('contact_name')} ({contact.get('email_address')})" for contact in contacts[:5]]

contact_manager = ContactManager()