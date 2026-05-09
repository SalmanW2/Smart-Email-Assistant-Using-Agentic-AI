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
    user = await db_manager.get_user(telegram_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    return {
        "ai_mode": user["ai_mode"],
        "voice_preference": user["voice_preference"]
    }

@router.put("/preferences/{telegram_id}")
async def update_preferences(telegram_id: int, prefs: UserPreferences):
    updates = {}
    if prefs.ai_mode is not None:
        updates["ai_mode"] = prefs.ai_mode
    if prefs.voice_preference is not None:
        updates["voice_preference"] = prefs.voice_preference
    
    success = await db_manager.update_user(telegram_id, updates)
    if not success:
        raise HTTPException(status_code=404, detail="User not found")
    
    return {"message": "Preferences updated"}

@router.get("/contacts/{telegram_id}")
async def get_contacts(telegram_id: int):
    from db.contacts import contact_manager
    contacts = await contact_manager.get_top_contacts(str(telegram_id))
    return contacts