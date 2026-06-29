import asyncio
from typing import List, Dict, Any, Optional
from config import settings
from db.models import db_manager


class ContactManager:
    def __init__(self):
        self.db = db_manager

    def _safe_data(self, result):
        return getattr(result, 'data', None) if result else None

    async def get_user_contacts(self, telegram_id: int) -> List[Dict[str, Any]]:
        """Get all contacts for a user."""
        try:
            result = await self.db.db.run(lambda: self.db.db.client.table("contacts")
                                         .select("id, contact_name, contact_alias, email_address")
                                         .eq("telegram_id", telegram_id)
                                         .order("contact_name")
                                         .execute())
            return self._safe_data(result) or []
        except Exception as e:
            print(f"DB Error in get_user_contacts: {e}")
            return []

    async def add_contact(self, telegram_id: int, name: str, email: str, phone: Optional[str] = None,
                         company: Optional[str] = None, notes: Optional[str] = None) -> bool:
        """Add a new contact for the user."""
        try:
            await self.db.db.run(lambda: self.db.db.client.table("contacts").insert({
                "telegram_id": telegram_id,
                "contact_name": name,
                "email_address": email,
                "phone": phone,
                "company": company,
                "notes": notes
            }).execute())
            return True
        except Exception as e:
            print(f"DB Error in add_contact: {e}")
            return False

    async def update_contact(self, contact_id: str, updates: Dict[str, Any]) -> bool:
        """Update an existing contact."""
        try:
            await self.db.db.run(lambda: self.db.db.client.table("contacts")
                                .update(updates)
                                .eq("id", contact_id)
                                .execute())
            return True
        except Exception as e:
            print(f"DB Error in update_contact: {e}")
            return False

    async def delete_contact(self, contact_id: str) -> bool:
        """Delete a contact."""
        try:
            await self.db.db.run(lambda: self.db.db.client.table("contacts")
                                .delete()
                                .eq("id", contact_id)
                                .execute())
            return True
        except Exception as e:
            print(f"DB Error in delete_contact: {e}")
            return False

    async def find_contacts_by_email(self, telegram_id: int, email: str) -> List[Dict[str, Any]]:
        """Find contacts by email address."""
        try:
            result = await self.db.db.run(lambda: self.db.db.client.table("contacts")
                                         .select("id, contact_name, contact_alias, email_address")
                                         .eq("telegram_id", telegram_id)
                                         .ilike("email_address", f"%{email}%")
                                         .execute())
            return self._safe_data(result) or []
        except Exception as e:
            print(f"DB Error in find_contacts_by_email: {e}")
            return []

    async def find_contacts_by_name(self, telegram_id: int, name: str) -> List[Dict[str, Any]]:
        """Find contacts by name."""
        try:
            result = await self.db.db.run(lambda: self.db.db.client.table("contacts")
                                         .select("id, contact_name, contact_alias, email_address")
                                         .eq("telegram_id", telegram_id)
                                         .ilike("contact_name", f"%{name}%")
                                         .execute())
            return self._safe_data(result) or []
        except Exception as e:
            print(f"DB Error in find_contacts_by_name: {e}")
            return []

    async def get_contact_by_id(self, contact_id: str) -> Optional[Dict[str, Any]]:
        """Get a specific contact by ID."""
        try:
            result = await self.db.db.run(lambda: self.db.db.client.table("contacts")
                                         .select("id, contact_name, contact_alias, email_address")
                                         .eq("id", contact_id)
                                         .maybe_single()
                                         .execute())
            return self._safe_data(result)
        except Exception as e:
            print(f"DB Error in get_contact_by_id: {e}")
            return None

    async def get_contact_relationships(self, telegram_id: int) -> List[Dict[str, Any]]:
        """Get contact relationships for mapping."""
        try:
            result = await self.db.db.run(lambda: self.db.db.client.table("contact_relationships")
                                         .select("*")
                                         .eq("telegram_id", telegram_id)
                                         .execute())
            return self._safe_data(result) or []
        except Exception as e:
            print(f"DB Error in get_contact_relationships: {e}")
            return []

    async def add_contact_relationship(self, telegram_id: int, contact_id: str, relationship_type: str,
                                      related_contact_id: str, notes: Optional[str] = None) -> bool:
        """Add a relationship between contacts."""
        try:
            await self.db.db.run(lambda: self.db.db.client.table("contact_relationships").insert({
                "telegram_id": telegram_id,
                "contact_id": contact_id,
                "relationship_type": relationship_type,
                "related_contact_id": related_contact_id,
                "notes": notes
            }).execute())
            return True
        except Exception as e:
            print(f"DB Error in add_contact_relationship: {e}")
            return False

    async def get_contact_network(self, telegram_id: int, contact_id: str) -> Dict[str, Any]:
        """Get the contact network for a specific contact."""
        try:
            contact = await self.get_contact_by_id(contact_id)
            if not contact:
                return {}

            relationships = await self.db.db.run(lambda: self.db.db.client.table("contact_relationships")
                                                .select("*")
                                                .or_(
                                                    f"contact_id.eq.{contact_id},related_contact_id.eq.{contact_id}"
                                                )
                                                .eq("telegram_id", telegram_id)
                                                .execute())

            network = {
                "contact": contact,
                "relationships": self._safe_data(relationships) or []
            }
            return network
        except Exception as e:
            print(f"DB Error in get_contact_network: {e}")
            return {}

    async def search_contacts(self, telegram_id: int, query: str) -> List[Dict[str, Any]]:
        """Search contacts by name, email, or company."""
        try:
            result = await self.db.db.run(lambda: self.db.db.client.table("contacts")
                                         .select("id, contact_name, contact_alias, email_address")
                                         .eq("telegram_id", telegram_id)
                                         .or_(
                                             f"contact_name.ilike.%{query}%,email_address.ilike.%{query}%,company.ilike.%{query}%"
                                         )
                                         .execute())
            return self._safe_data(result) or []
        except Exception as e:
            print(f"DB Error in search_contacts: {e}")
            return []

contact_manager = ContactManager()