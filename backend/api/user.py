from fastapi import APIRouter, HTTPException
from db.models import db_manager
from pydantic import BaseModel, EmailStr
from typing import Optional
import httpx
from config import settings

router = APIRouter()

# --- Pydantic Models for Validation ---
class UserPreferences(BaseModel):
    ai_mode: Optional[bool] = None
    voice_preference: Optional[str] = None
    auto_check_enabled: Optional[bool] = None

class ContactFormMessage(BaseModel):
    email: EmailStr
    message: str

@router.get("/preferences/{telegram_id}")
async def get_preferences(telegram_id: int):
    try:
        user = await db_manager.get_user(telegram_id)
        if not user:
            raise HTTPException(status_code=404, detail="User not found")
    except Exception:
        raise HTTPException(status_code=500, detail="Database error")
    
    try:
        prefs = await db_manager.get_user_preferences(telegram_id) or {}
    except Exception:
        prefs = {}
    
    return {
        "ai_mode": prefs.get("ai_mode_enabled", user.get("ai_mode_enabled", True)),
        "voice_preference": prefs.get("voice_preference", "text"),
        "auto_check_enabled": prefs.get("auto_check_enabled", True)
    }

@router.put("/preferences/{telegram_id}")
async def update_preferences(telegram_id: int, prefs: UserPreferences):
    updates = {}
    if prefs.ai_mode is not None:
        updates["ai_mode_enabled"] = prefs.ai_mode
    if prefs.voice_preference is not None:
        updates["voice_preference"] = prefs.voice_preference
    if prefs.auto_check_enabled is not None:
        updates["auto_check_enabled"] = prefs.auto_check_enabled
    
    try:
        success = await db_manager.update_user_preferences(telegram_id, updates)
        if not success:
            raise HTTPException(status_code=404, detail="User not found")
    except Exception:
        raise HTTPException(status_code=500, detail="Database error")
    
    return {"message": "Preferences updated successfully"}

@router.get("/contacts/{telegram_id}")
async def get_contacts(telegram_id: int):
    """Retrieve top contacts for the user."""
    try:
        from db.contacts import contact_manager
        contacts = await contact_manager.get_user_contacts(telegram_id)
        return contacts
    except Exception as e:
        print(f"Error fetching contacts: {e}")
        return []

@router.post("/public/contact")
async def submit_contact_form(form_data: ContactFormMessage):
    """
    Public endpoint for contact form submissions.
    Saves message to DB and notifies owner via Telegram.
    """
    try:
        # Save to database
        await db_manager.db.run(
            lambda: db_manager.db.client.table("contact_messages").insert({
                "sender_email": form_data.email,
                "message_text": form_data.message,
                "status": "pending",
            }).execute()
        )
        
        # Send notification to owner via Telegram
        owner_id = settings.OWNER_TELEGRAM_ID
        if owner_id:
            notification_text = (
                f"📩 *New Contact Form Submission*\n\n"
                f"*From:* `{form_data.email}`\n\n"
                f"*Message:*\n{form_data.message}"
            )
            url = f"https://api.telegram.org/bot{settings.BOT_TOKEN}/sendMessage"
            async with httpx.AsyncClient(timeout=10) as client:
                await client.post(url, json={
                    "chat_id": owner_id,
                    "text": notification_text,
                    "parse_mode": "Markdown",
                })
        
        return {"success": True, "message": "Your message has been sent successfully!"}
    
    except Exception as e:
        print(f"Contact form error: {e}")
        raise HTTPException(status_code=500, detail="Failed to submit message. Please try again later.")