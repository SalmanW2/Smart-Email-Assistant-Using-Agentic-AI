import re
import logging
from typing import Optional, List, Dict, Any
from db.contacts import contact_manager as db_contact_manager

logger = logging.getLogger(__name__)

class ContactManager:
    def __init__(self) -> None:
        self.db = db_contact_manager

    async def extract_contacts_from_text(self, telegram_id: int, text: str) -> None:
        """
        Proactively extracts email addresses from messages and saves them 
        into the contact database for relationship mapping.
        """
        email_pattern = r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b"
        emails = re.findall(email_pattern, text)
        
        for email in set(emails):  # Use set to avoid processing duplicates in the same message
            name = self._extract_name_from_context(text, email)
            existing = await self.db.find_contacts_by_email(telegram_id, email)
            
            if not existing:
                await self.db.add_contact(telegram_id=telegram_id, name=name, email=email)
                logger.info(f"Auto-saved new contact: {name} ({email}) for user {telegram_id}")

    def _extract_name_from_context(self, text: str, email: str) -> str:
        """
        Intelligently guesses the name of the person based on words preceding the email.
        """
        words = text.replace("\n", " ").split()
        if email in words:
            email_index = words.index(email)
            if email_index > 0:
                # Clean up the word before the email
                guess = re.sub(r'[^a-zA-Z0-9]', '', words[email_index - 1]).title()
                # Ignore common prepositions or non-name words
                if len(guess) > 1 and guess.lower() not in ['to', 'for', 'email', 'at', 'is', 'on', 'the', 'my']:
                    return guess
                    
        # Fallback: Capitalize the local part of the email address
        return email.split('@')[0].replace('.', ' ').title()

    async def resolve_contact(self, telegram_id: int, identifier: str) -> Optional[str]:
        """
        Resolves a conversational name (e.g., 'Ali', 'Boss') or partial email 
        to a full email address using the intelligent database search.
        """
        # If it looks like an email already, verify or return it directly
        if '@' in identifier:
            contacts = await self.db.find_contacts_by_email(telegram_id, identifier)
            if contacts:
                return contacts[0].get("email_address")
            return identifier

        # Otherwise, search the database by name/alias/company
        contacts = await self.db.search_contacts(telegram_id, identifier)
        if contacts:
            return contacts[0].get("email_address")
            
        return None

# Singleton instance to be used across the bot
contact_manager = ContactManager()