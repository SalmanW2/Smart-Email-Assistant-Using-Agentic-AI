"""
Contact Manager — Smart Email Assistant
=======================================
Manages user-specific contact lists, relationships, and aliases.
Utilizes Google Gemini for intelligent entity extraction from conversational texts,
and interfaces directly with the Supabase database for persistent state.
"""

import json
import logging
import asyncio
from typing import List, Dict, Any
from google import genai
from config import settings
from db.models import db_manager

logger = logging.getLogger(__name__)

class ContactManager:
    def __init__(self) -> None:
        # Resolving the deep attribute chaining bug by mapping directly to the underlying SupabaseDB instance
        self.db = db_manager.db 
        
        # Initialize the Gemini client safely for background entity extraction
        self.client = genai.Client(api_key=settings.GEMINI_API_KEY) if settings.GEMINI_API_KEY else None

    async def get_contacts(self, telegram_id: int) -> List[Dict[str, Any]]:
        """
        Fetches the complete list of saved contacts for a specific user.
        Utilizes asynchronous lambda execution to prevent server blocking.
        """
        try:
            # Cleaned execution interface: self.db.run -> self.db.client
            res = await self.db.run(
                lambda: self.db.client.table("contacts")
                .select("*")
                .eq("telegram_id", telegram_id)
                .execute()
            )
            return getattr(res, 'data', [])
        except Exception as e:
            logger.error(f"Error fetching contacts for {telegram_id}: {e}")
            return []

    async def find_contacts_by_name(self, telegram_id: int, name: str) -> List[Dict[str, Any]]:
        """
        Smart Search Helper: Locates a contact's email address using their partial name or alias.
        This enables natural language drafting constraints (e.g., "Email John").
        """
        try:
            res = await self.db.run(
                lambda: self.db.client.table("contacts")
                .select("*")
                .eq("telegram_id", telegram_id)
                .ilike("contact_name", f"%{name}%")
                .execute()
            )
            return getattr(res, 'data', [])
        except Exception as e:
            logger.error(f"Error searching contact '{name}' for user {telegram_id}: {e}")
            return []

    async def extract_and_save_contacts(self, telegram_id: int, text: str) -> None:
        """
        Analyzes conversational text using Gemini to extract new contact details
        (Names and Email Addresses) and saves them asynchronously to the Supabase database.
        Fails silently in the background to prevent interrupting the main Telegram webhook flow.
        """
        if not self.client or not text:
            return

        try:
            prompt = (
                "Analyze the following text and extract any mentioned contacts (Names and Email Addresses). "
                "Return ONLY a valid JSON array of objects with 'name' and 'email' keys. "
                "Example: [{\"name\": \"John Doe\", \"email\": \"john@example.com\"}]. "
                "If no clear relationship or valid email format is found, return an empty array [].\n\n"
                f"User Text: {text}"
            )
            
            # Execute Gemini extraction in an asynchronous thread to prevent blocking
            response = await asyncio.to_thread(
                self.client.models.generate_content,
                model="gemini-2.5-flash",
                contents=prompt
            )
            
            # Sanitize the markdown JSON response payload
            json_str = response.text.replace('```json', '').replace('```', '').strip()
            if not json_str:
                return
            
            contacts = json.loads(json_str)
            
            for c in contacts:
                name = c.get("name")
                email = c.get("email")
                
                # Validate the integrity of the extracted email format
                if name and email and "@" in email:
                    # Upsert the newly discovered contact securely into the database
                    await self.db.run(
                        lambda: self.db.client.table("contacts").upsert({
                            "telegram_id": telegram_id,
                            "contact_alias": name,
                            "email_address": email,
                            "contact_name": name
                        }, on_conflict="telegram_id,email_address").execute()
                    )
                    logger.info(f"Learned and mapped new contact for {telegram_id}: {name} -> {email}")
                    
        except Exception as e:
            # Catch exceptions silently so the main UX remains unaffected by background extraction errors
            logger.warning(f"Background contact extraction skipped/failed: {e}")

# Singleton instance export for centralized access
contact_manager = ContactManager()