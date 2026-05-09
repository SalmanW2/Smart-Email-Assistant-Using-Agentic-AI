from db.models import supabase
from config import get_utc_now

class ContactManager:
    @staticmethod
    def upsert_contact(telegram_id: int, email: str, name: str = None, alias: str = None, relationship: str = None):
        existing = supabase.table("contacts").select("frequency_of_contact, tags").eq("telegram_id", telegram_id).eq("email_address", email).execute()
        
        freq = 1
        tags = []
        if existing.data:
            freq = existing.data[0].get("frequency_of_contact", 0) + 1
            tags = existing.data[0].get("tags", [])

        contact_data = {
            "telegram_id": telegram_id,
            "email_address": email,
            "contact_name": name,
            "contact_alias": alias,
            "relationship_type": relationship,
            "frequency_of_contact": freq,
            "tags": tags,
            "updated_at": get_utc_now()
        }
        
        # Strip None values to prevent null overwrites
        contact_data = {k: v for k, v in contact_data.items() if v is not None}
        return supabase.table("contacts").upsert(contact_data, on_conflict="telegram_id, email_address").execute()

    @staticmethod
    def search_contact_by_alias(telegram_id: int, query: str):
        response = (
            supabase.table("contacts")
            .select("*")
            .eq("telegram_id", telegram_id)
            .or_(f"contact_name.ilike.%{query}%,contact_alias.ilike.%{query}%,relationship_type.ilike.%{query}%")
            .order("frequency_of_contact", desc=True)
            .execute()
        )
        return response.data

    @staticmethod
    def update_context_topics(telegram_id: int, email: str, new_topic: str):
        existing = supabase.table("contacts").select("context_topics").eq("telegram_id", telegram_id).eq("email_address", email).execute()
        
        topics = []
        if existing.data:
            topics = existing.data[0].get("context_topics", [])
            if new_topic and new_topic not in topics:
                topics.append(new_topic)
                topics = topics[-5:]  # Keep only the 5 most recent topics
                
        return supabase.table("contacts").update({"context_topics": topics}).eq("telegram_id", telegram_id).eq("email_address", email).execute()