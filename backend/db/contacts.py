from db.models import db_manager
from typing import List, Dict, Any, Optional
import json

class ContactManager:
    def __init__(self):
        self.db = db_manager

    async def save_contact(self, user_id: str, name: str, email: str, role: str = None, frequency: int = 1, tags: List[str] = None) -> bool:
        # Check if contact exists
        existing = await self.get_contact_by_email(user_id, email)
        if existing:
            # Update frequency and merge tags
            new_freq = existing["frequency"] + frequency
            existing_tags = json.loads(existing.get("tags", "[]"))
            merged_tags = list(set(existing_tags + (tags or [])))
            updates = {
                "frequency": new_freq,
                "tags": json.dumps(merged_tags)
            }
            if role and not existing.get("role"):
                updates["role"] = role
            response = self.db.client.table("contacts").update(updates).eq("id", existing["id"]).execute()
            return len(response.data) > 0
        else:
            # Create new contact
            data = {
                "user_id": user_id,
                "name": name,
                "email": email,
                "role": role,
                "frequency": frequency,
                "tags": json.dumps(tags or [])
            }
            response = self.db.client.table("contacts").insert(data).execute()
            return len(response.data) > 0

    async def get_contact_by_email(self, user_id: str, email: str) -> Optional[Dict[str, Any]]:
        response = self.db.client.table("contacts").select("*").eq("user_id", user_id).eq("email", email).execute()
        return response.data[0] if response.data else None

    async def search_contacts(self, user_id: str, query: str) -> List[Dict[str, Any]]:
        # Search by name or email
        response = self.db.client.table("contacts").select("*").eq("user_id", user_id).or_(f"name.ilike.%{query}%,email.ilike.%{query}%").execute()
        return response.data

    async def get_top_contacts(self, user_id: str, limit: int = 10) -> List[Dict[str, Any]]:
        response = self.db.client.table("contacts").select("*").eq("user_id", user_id).order("frequency", desc=True).limit(limit).execute()
        return response.data

    async def update_contact_tags(self, contact_id: int, tags: List[str]) -> bool:
        response = self.db.client.table("contacts").update({"tags": json.dumps(tags)}).eq("id", contact_id).execute()
        return len(response.data) > 0

contact_manager = ContactManager()