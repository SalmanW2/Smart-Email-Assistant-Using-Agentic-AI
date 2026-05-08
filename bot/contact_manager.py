"""
Contact Manager - AI-powered contact suggestions and extraction
"""

import logging
import re
from typing import Optional, List, Tuple
from db.contacts import ContactManager
from db.memory import ConversationMemory

logger = logging.getLogger(__name__)


class AIContactSuggestion:
    """AI-powered contact suggestion system."""
    
    @staticmethod
    def extract_email_mention(text: str, telegram_id: int, current_topic: str = "General") -> Optional[Tuple[str, str]]:
        """
        Extracts email address from user text and suggests contact.
        Returns: (email, contact_display_name) or None
        """
        # Regex to find email patterns
        email_pattern = r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}'
        emails = re.findall(email_pattern, text)
        
        if emails:
            email = emails[0]
            contact = ContactManager.get_contact(telegram_id, email)
            
            if contact:
                # Update topic
                ContactManager.add_topic_to_contact(telegram_id, email, current_topic)
                display_name = contact.get("contact_alias") or contact.get("contact_name") or email
                return email, display_name
            else:
                # New email, add to contacts
                ContactManager.add_or_update_contact(
                    telegram_id=telegram_id,
                    email_address=email,
                    context_topics=[current_topic]
                )
                return email, email
        
        return None

    @staticmethod
    def find_contact_by_alias(text: str, telegram_id: int) -> Optional[Tuple[str, str]]:
        """
        Finds contact by alias mention (e.g., 'send to Boss')
        Returns: (email, contact_name) or None
        """
        text_lower = text.lower()
        
        # Get all contacts for this user
        contacts = ContactManager.get_all_contacts(telegram_id)
        
        for contact in contacts:
            alias = contact.get("contact_alias", "").lower()
            name = contact.get("contact_name", "").lower()
            
            if alias and alias in text_lower:
                return contact["email_address"], alias
            elif name and name in text_lower:
                return contact["email_address"], name
        
        return None

    @staticmethod
    def suggest_contact_for_compose(text: str, telegram_id: int) -> Optional[dict]:
        """
        Intelligent contact suggestion for email composition.
        Looks for: "send to [name/alias]"
        """
        patterns = [
            r'send\s+(?:an?\s+)?(?:email\s+)?to\s+(\w+)',
            r'email\s+to\s+(\w+)',
            r'compose\s+(?:email\s+)?to\s+(\w+)',
            r'reply\s+to\s+(\w+)',
        ]
        
        for pattern in patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                contact_query = match.group(1)
                
                # Try exact alias match first
                contact = ContactManager.search_contact_by_alias(telegram_id, contact_query)
                if contact:
                    return contact
                
                # Try name match
                contact = ContactManager.search_contact_by_name(telegram_id, contact_query)
                if contact:
                    return contact
                
                # Try suggestions
                suggestions = ContactManager.suggest_contacts(telegram_id, contact_query, limit=3)
                if suggestions:
                    return suggestions[0]
        
        return None

    @staticmethod
    def format_contact_display(contact: dict) -> str:
        """Formats contact for display."""
        alias = contact.get("contact_alias")
        name = contact.get("contact_name")
        email = contact.get("email_address")
        
        if alias:
            return f"{alias} ({name or email})"
        elif name:
            return f"{name} <{email}>"
        else:
            return email

    @staticmethod
    def generate_contact_suggestion_message(suggestions: List[dict]) -> str:
        """Generates suggestion message for user."""
        if not suggestions:
            return ""
        
        msg = "💡 Did you mean one of these contacts?\n"
        for i, contact in enumerate(suggestions[:5], 1):
            display = AIContactSuggestion.format_contact_display(contact)
            msg += f"{i}. {display}\n"
        
        return msg