from fastapi import APIRouter, HTTPException
from db.models import db_manager
from pydantic import BaseModel
from typing import Optional

router = APIRouter()

class UserPreferences(BaseModel):
    ai_mode: Optional[bool] = None
    voice_preference: Optional[str] = None

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
        "voice_preference": prefs.get("voice_preference", "text")
    }

@router.put("/preferences/{telegram_id}")
async def update_preferences(telegram_id: int, prefs: UserPreferences):
    updates = {}
    if prefs.ai_mode is not None:
        updates["ai_mode_enabled"] = prefs.ai_mode
    if prefs.voice_preference is not None:
        updates["voice_preference"] = prefs.voice_preference
    
    try:
        success = await db_manager.update_user_preferences(telegram_id, updates)
        if not success:
            raise HTTPException(status_code=404, detail="User not found")
    except Exception:
        raise HTTPException(status_code=500, detail="Database error")
    
    return {"message": "Preferences updated"}

@router.get("/contacts/{telegram_id}")
async def get_contacts(telegram_id: int):
    """Retrieve top contacts for the user."""
    try:
        from db.contacts import contact_manager
        # Fetching directly using the contact manager
        contacts = await contact_manager.get_user_contacts(telegram_id)
        return contacts
    except Exception as e:
        print(f"Error fetching contacts: {e}")
        return []