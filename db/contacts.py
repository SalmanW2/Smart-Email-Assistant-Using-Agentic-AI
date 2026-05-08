"""
Contact Relationship Mapping
Handles storing and retrieving contacts with advanced relationship tracking
"""

import logging
from typing import Optional, List, Dict, Any
from config import SUPABASE_URL, SUPABASE_KEY, get_utc_now
from supabase import create_client

supabase = create_client(SUPABASE_URL, SUPABASE_KEY)
logger = logging.getLogger(__name__)

class ContactManager:
    """Manages user contacts and relationships."""
    
    @staticmethod
    def add_or_update_contact(
        telegram_id: int,
        email_address: str,
        contact_name: Optional[str] = None,
        contact_alias: Optional[str] = None,
        relationship_type: Optional[str] = None,
        tags: Optional[List[str]] = None,
        context_topics: Optional[List[str]] = None
    ) -> bool:
        """Adds or updates a contact."""
        try:
            # Check if contact exists
            existing = supabase.table("contacts").select(
                "id,frequency_of_contact"
            ).eq("telegram_id", telegram_id).eq(
                "email_address", email_address
            ).execute()
            
            data = {
                "telegram_id": telegram_id,
                "email_address": email_address,
                "contact_name": contact_name,
                "contact_alias": contact_alias,
                "relationship_type": relationship_type,
                "tags": tags or [],
                "context_topics": context_topics or [],
                "updated_at": get_utc_now()
            }
            
            if existing.data:
                # Update frequency
                data["frequency_of_contact"] = existing.data[0].get("frequency_of_contact", 0) + 1
                data["last_email_date"] = get_utc_now()
                supabase.table("contacts").update(data).eq(
                    "id", existing.data[0]["id"]
                ).execute()
            else:
                # New contact
                data["frequency_of_contact"] = 1
                data["last_email_date"] = get_utc_now()
                data["created_at"] = get_utc_now()
                supabase.table("contacts").insert(data).execute()
            
            return True
        except Exception as e:
            logger.error(f"Contact add/update error: {e}")
            return False

    @staticmethod
    def get_contact(telegram_id: int, email_address: str) -> Optional[Dict]:
        """Fetches a specific contact."""
        try:
            res = supabase.table("contacts").select(
                "*"
            ).eq("telegram_id", telegram_id).eq(
                "email_address", email_address
            ).execute()
            return res.data[0] if res.data else None
        except Exception as e:
            logger.error(f"Contact fetch error: {e}")
            return None

    @staticmethod
    def search_contact_by_alias(telegram_id: int, alias: str) -> Optional[Dict]:
        """Searches contact by alias (e.g., 'Boss', 'HR')."""
        try:
            res = supabase.table("contacts").select(
                "*"
            ).eq("telegram_id", telegram_id).ilike(
                "contact_alias", f"%{alias}%"
            ).execute()
            return res.data[0] if res.data else None
        except Exception as e:
            logger.error(f"Alias search error: {e}")
            return None

    @staticmethod
    def search_contact_by_name(telegram_id: int, name: str) -> Optional[Dict]:
        """Searches contact by name."""
        try:
            res = supabase.table("contacts").select(
                "*"
            ).eq("telegram_id", telegram_id).ilike(
                "contact_name", f"%{name}%"
            ).limit(1).execute()
            return res.data[0] if res.data else None
        except Exception as e:
            logger.error(f"Name search error: {e}")
            return None

    @staticmethod
    def get_all_contacts(telegram_id: int) -> List[Dict]:
        """Gets all contacts for a user."""
        try:
            res = supabase.table("contacts").select(
                "*"
            ).eq("telegram_id", telegram_id).order(
                "frequency_of_contact", desc=True
            ).execute()
            return res.data
        except Exception as e:
            logger.error(f"Contacts fetch error: {e}")
            return []

    @staticmethod
    def get_frequent_contacts(telegram_id: int, limit: int = 10) -> List[Dict]:
        """Gets most frequent contacts."""
        try:
            res = supabase.table("contacts").select(
                "*"
            ).eq("telegram_id", telegram_id).order(
                "frequency_of_contact", desc=True
            ).limit(limit).execute()
            return res.data
        except Exception as e:
            logger.error(f"Frequent contacts fetch error: {e}")
            return []

    @staticmethod
    def add_tag_to_contact(telegram_id: int, email_address: str, tag: str) -> bool:
        """Adds a tag to a contact."""
        try:
            contact = ContactManager.get_contact(telegram_id, email_address)
            if not contact:
                return False
            
            tags = contact.get("tags", [])
            if tag not in tags:
                tags.append(tag)
            
            supabase.table("contacts").update({"tags": tags}).eq(
                "id", contact["id"]
            ).execute()
            return True
        except Exception as e:
            logger.error(f"Tag add error: {e}")
            return False

    @staticmethod
    def add_topic_to_contact(telegram_id: int, email_address: str, topic: str) -> bool:
        """Adds a conversation topic to a contact."""
        try:
            contact = ContactManager.get_contact(telegram_id, email_address)
            if not contact:
                return False
            
            topics = contact.get("context_topics", [])
            if topic not in topics:
                topics.append(topic)
            
            supabase.table("contacts").update({"context_topics": topics}).eq(
                "id", contact["id"]
            ).execute()
            return True
        except Exception as e:
            logger.error(f"Topic add error: {e}")
            return False

    @staticmethod
    def suggest_contacts(telegram_id: int, query: str, limit: int = 5) -> List[Dict]:
        """Suggests contacts based on name or alias query."""
        try:
            # Try alias first
            by_alias = supabase.table("contacts").select(
                "*"
            ).eq("telegram_id", telegram_id).ilike(
                "contact_alias", f"%{query}%"
            ).limit(limit).execute()
            
            if by_alias.data:
                return by_alias.data
            
            # Try name
            by_name = supabase.table("contacts").select(
                "*"
            ).eq("telegram_id", telegram_id).ilike(
                "contact_name", f"%{query}%"
            ).limit(limit).execute()
            
            return by_name.data if by_name.data else []
        except Exception as e:
            logger.error(f"Contact suggestion error: {e}")
            return []

    @staticmethod
    def auto_extract_emails(telegram_id: int, text: str, current_topic: str = "General") -> List[str]:
        """Auto-extracts email addresses from text and tracks them."""
        import re
        email_pattern = r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}'
        emails = re.findall(email_pattern, text)
        
        extracted = []
        for email in emails:
            # Add or update contact with topic
            ContactManager.add_or_update_contact(
                telegram_id=telegram_id,
                email_address=email,
                context_topics=[current_topic]
            )
            extracted.append(email)
        
        return extracted

    @staticmethod
    def delete_contact(telegram_id: int, email_address: str) -> bool:
        """Deletes a contact."""
        try:
            supabase.table("contacts").delete().eq(
                "telegram_id", telegram_id
            ).eq("email_address", email_address).execute()
            return True
        except Exception as e:
            logger.error(f"Contact delete error: {e}")
            return False