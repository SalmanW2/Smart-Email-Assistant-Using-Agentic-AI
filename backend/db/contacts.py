import json
from typing import Any, Dict, List, Optional
from db.models import db_manager

class ContactManager:
    def __init__(self) -> None:
        self.db = db_manager

    async def get_contact_by_email(self, telegram_id: int, email_address: str) -> Optional[Dict[str, Any]]:
        def action():
            return (
                self.db.db.client.table("contacts")
                .select("*")
                .eq("telegram_id", telegram_id)
                .eq("email_address", email_address)
                .maybe_single()
                .execute()
            )

        response = await self.db.db.run(action)
        return response.data if response.data else None

    async def save_contact(
        self,
        telegram_id: int,
        email_address: str,
        contact_name: str | None = None,
        contact_alias: str | None = None,
        frequency_of_contact: int = 1,
        tags: List[str] | None = None,
    ) -> bool:
        existing = await self.get_contact_by_email(telegram_id, email_address)
        tags = tags or []
        if existing:
            merged_tags = list({*json.loads(existing.get("tags", "[]")), *tags})
            payload = {
                "contact_name": contact_name or existing.get("contact_name"),
                "contact_alias": contact_alias or existing.get("contact_alias"),
                "frequency_of_contact": existing.get("frequency_of_contact", 0) + frequency_of_contact,
                "tags": json.dumps(merged_tags),
            }

            def action():
                return self.db.db.client.table("contacts").update(payload).eq("id", existing["id"]).execute()

            response = await self.db.db.run(action)
            return bool(response.data)

        payload = {
            "telegram_id": telegram_id,
            "email_address": email_address,
            "contact_name": contact_name or email_address.split("@")[0].replace('.', ' ').title(),
            "contact_alias": contact_alias,
            "frequency_of_contact": frequency_of_contact,
            "tags": json.dumps(tags),
        }

        def action():
            return self.db.db.client.table("contacts").insert(payload).execute()

        response = await self.db.db.run(action)
        return bool(response.data)

    async def search_contacts(self, telegram_id: int, query: str) -> List[Dict[str, Any]]:
        def action():
            return (
                self.db.db.client.table("contacts")
                .select("*")
                .eq("telegram_id", telegram_id)
                .or_(f"contact_name.ilike.%{query}%,contact_alias.ilike.%{query}%,email_address.ilike.%{query}%")
                .execute()
            )

        response = await self.db.db.run(action)
        return response.data or []

    async def get_top_contacts(self, telegram_id: int, limit: int = 10) -> List[Dict[str, Any]]:
        def action():
            return (
                self.db.db.client.table("contacts")
                .select("*")
                .eq("telegram_id", telegram_id)
                .order("frequency_of_contact", desc=True)
                .limit(limit)
                .execute()
            )

        response = await self.db.db.run(action)
        return response.data or []

    async def update_contact_tags(self, contact_id: str, tags: List[str]) -> bool:
        def action():
            return self.db.db.client.table("contacts").update({"tags": json.dumps(tags)}).eq("id", contact_id).execute()

        response = await self.db.db.run(action)
        return bool(response.data)

contact_manager = ContactManager()