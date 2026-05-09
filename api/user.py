from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from db.models import DBManager

router = APIRouter(prefix="/api/user", tags=["User"])

class PreferenceUpdate(BaseModel):
    telegram_id: int
    ai_mode_enabled: bool = None
    voice_preference: str = None

@router.get("/preferences/{telegram_id}")
async def get_preferences(telegram_id: int):
    """Fetches user preferences for the frontend dashboard."""
    prefs = DBManager.get_user_preferences(telegram_id)
    if not prefs:
        raise HTTPException(status_code=404, detail="Preferences not found")
    return prefs

@router.put("/preferences")
async def update_preferences(prefs: PreferenceUpdate):
    """Updates user settings from the React frontend."""
    update_data = {k: v for k, v in prefs.model_dump().items() if v is not None and k != "telegram_id"}
    result = DBManager.update_preferences(prefs.telegram_id, **update_data)
    return {"status": "success"}