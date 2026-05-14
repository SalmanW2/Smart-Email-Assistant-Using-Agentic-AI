import json
import logging
import asyncio
from google import genai
from config import settings
from db.models import db_manager

logger = logging.getLogger(__name__)

class ContactManager:
    def __init__(self):
        self.db = db_manager
        self.client = genai.Client(api_key=settings.GEMINI_API_KEY)

    async def get_contacts(self, telegram_id: int):
        """Fetch all saved contacts for a user."""
        try:
            res = await self.db.db.run(lambda: self.db.db.client.table("contacts").select("*").eq("telegram_id", telegram_id).execute())
            return getattr(res, 'data', [])
        except Exception as e:
            logger.error(f"Error fetching contacts: {e}")
            return []

    async def extract_contacts_from_text(self, telegram_id: int, text: str):
        """
        Background task: Uses Gemini Flash Lite to detect if the user mentioned
        a new contact name and email, and saves it to the database silently.
        """
        try:
            prompt = (
                "Extract any explicit name-to-email relationships mentioned in the text.\n"
                "Return ONLY a valid JSON array of objects. Example: [{\"name\": \"Boss\", \"email\": \"boss@company.com\"}].\n"
                "If no clear relationship is found, return an empty array [].\n\n"
                f"User Text: {text}"
            )
            
            response = await asyncio.to_thread(
                self.client.models.generate_content,
                model="gemini-2.5-flash-lite", # Ultra-fast and cheap model
                contents=prompt
            )
            
            json_str = response.text.replace('```json', '').replace('```', '').strip()
            contacts = json.loads(json_str)
            
            for c in contacts:
                name = c.get("name")
                email = c.get("email")
                if name and email and "@" in email:
                    # Upsert contact into database safely
                    await self.db.db.run(lambda: self.db.db.client.table("contacts").upsert({
                        "telegram_id": telegram_id,
                        "contact_alias": name,
                        "email_address": email,
                        "contact_name": name
                    }, on_conflict="telegram_id,email_address").execute())
                    logger.info(f"Learned new contact for {telegram_id}: {name} -> {email}")
                    
        except Exception as e:
            pass # Fail silently in background so it doesn't break the main flow

contact_manager = ContactManager()