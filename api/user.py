"""
User API Endpoints
Handles user-specific operations
"""

import logging
from fastapi import APIRouter, Request, Form, Response, HTTPException
from fastapi.responses import JSONResponse

from config import BOT_TOKEN
from db.models import UserModel, LoginModel
from db.memory import ConversationMemory
from db.contacts import ContactManager

logger = logging.getLogger(__name__)

user_router = APIRouter(prefix="/api/user", tags=["user"])


# ===== USER PROFILE ENDPOINTS =====

@user_router.get("/profile/{telegram_id}")
async def get_user_profile(telegram_id: int):
    """Gets user profile information."""
    try:
        user = UserModel.get_user(telegram_id)
        if not user:
            raise HTTPException(status_code=404, detail="User not found")
        
        return {
            "status": "ok",
            "data": {
                "telegram_id": user.get("telegram_id"),
                "first_name": user.get("first_name"),
                "username": user.get("username"),
                "email": user.get("email"),
                "ai_mode_enabled": user.get("ai_mode_enabled"),
                "voice_preference": user.get("voice_preference"),
                "created_at": user.get("created_at"),
                "last_activity_at": user.get("last_activity_at")
            }
        }
    except Exception as e:
        logger.error(f"Profile fetch error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@user_router.post("/profile/{telegram_id}/update")
async def update_user_profile(telegram_id: int, request: Request):
    """Updates user profile."""
    try:
        data = await request.json()
        
        update_data = {}
        if "ai_mode_enabled" in data:
            update_data["ai_mode_enabled"] = data["ai_mode_enabled"]
        if "voice_preference" in data:
            update_data["voice_preference"] = data["voice_preference"]
        
        if update_data:
            UserModel.update_user(telegram_id, update_data)
        
        return {"status": "ok", "message": "Profile updated"}
    except Exception as e:
        logger.error(f"Profile update error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ===== CONTACTS ENDPOINTS =====

@user_router.get("/contacts/{telegram_id}")
async def get_user_contacts(telegram_id: int):
    """Gets all user contacts."""
    try:
        contacts = ContactManager.get_all_contacts(telegram_id)
        
        return {
            "status": "ok",
            "count": len(contacts),
            "data": contacts
        }
    except Exception as e:
        logger.error(f"Contacts fetch error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@user_router.get("/contacts/{telegram_id}/frequent")
async def get_frequent_contacts(telegram_id: int, limit: int = 10):
    """Gets most frequent contacts."""
    try:
        contacts = ContactManager.get_frequent_contacts(telegram_id, limit)
        
        return {
            "status": "ok",
            "count": len(contacts),
            "data": contacts
        }
    except Exception as e:
        logger.error(f"Frequent contacts error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@user_router.post("/contacts/{telegram_id}/add")
async def add_contact(telegram_id: int, request: Request):
    """Adds or updates a contact."""
    try:
        data = await request.json()
        
        email = data.get("email_address")
        if not email:
            raise HTTPException(status_code=400, detail="Email required")
        
        success = ContactManager.add_or_update_contact(
            telegram_id=telegram_id,
            email_address=email,
            contact_name=data.get("contact_name"),
            contact_alias=data.get("contact_alias"),
            relationship_type=data.get("relationship_type"),
            tags=data.get("tags", []),
            context_topics=data.get("context_topics", [])
        )
        
        if success:
            return {"status": "ok", "message": "Contact added/updated"}
        else:
            raise HTTPException(status_code=500, detail="Failed to add contact")
    except Exception as e:
        logger.error(f"Contact add error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@user_router.delete("/contacts/{telegram_id}/{email}")
async def delete_contact(telegram_id: int, email: str):
    """Deletes a contact."""
    try:
        success = ContactManager.delete_contact(telegram_id, email)
        
        if success:
            return {"status": "ok", "message": "Contact deleted"}
        else:
            raise HTTPException(status_code=404, detail="Contact not found")
    except Exception as e:
        logger.error(f"Contact delete error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@user_router.get("/contacts/{telegram_id}/search")
async def search_contacts(telegram_id: int, query: str):
    """Searches contacts by name or alias."""
    try:
        suggestions = ContactManager.suggest_contacts(telegram_id, query, limit=10)
        
        return {
            "status": "ok",
            "count": len(suggestions),
            "data": suggestions
        }
    except Exception as e:
        logger.error(f"Contact search error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ===== CONVERSATION ENDPOINTS =====

@user_router.get("/conversation/{telegram_id}/recent")
async def get_recent_context(telegram_id: int, days: int = 1):
    """Gets recent conversation context."""
    try:
        context = ConversationMemory.get_recent_context(telegram_id, days)
        history = ConversationMemory.get_conversation_history(telegram_id, limit=10)
        
        return {
            "status": "ok",
            "context": context,
            "history": history
        }
    except Exception as e:
        logger.error(f"Context fetch error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@user_router.get("/conversation/{telegram_id}/history")
async def get_conversation_history(telegram_id: int, limit: int = 20):
    """Gets conversation history."""
    try:
        history = ConversationMemory.get_conversation_history(telegram_id, limit)
        
        return {
            "status": "ok",
            "count": len(history),
            "data": history
        }
    except Exception as e:
        logger.error(f"History fetch error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@user_router.get("/conversation/{telegram_id}/topic")
async def get_current_topic(telegram_id: int):
    """Gets current conversation topic."""
    try:
        topic = ConversationMemory.get_current_topic(telegram_id)
        
        return {
            "status": "ok",
            "topic": topic or "General"
        }
    except Exception as e:
        logger.error(f"Topic fetch error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@user_router.post("/conversation/{telegram_id}/topic")
async def update_current_topic(telegram_id: int, request: Request):
    """Updates current conversation topic."""
    try:
        data = await request.json()
        topic = data.get("topic", "General")
        
        success = ConversationMemory.update_current_topic(telegram_id, topic)
        
        if success:
            return {"status": "ok", "message": "Topic updated"}
        else:
            raise HTTPException(status_code=500, detail="Failed to update topic")
    except Exception as e:
        logger.error(f"Topic update error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ===== SETTINGS ENDPOINTS =====

@user_router.post("/settings/{telegram_id}/ai-mode")
async def toggle_ai_mode(telegram_id: int, request: Request):
    """Toggles AI mode."""
    try:
        data = await request.json()
        enabled = data.get("enabled", True)
        
        UserModel.toggle_ai_mode(telegram_id, enabled)
        
        return {
            "status": "ok",
            "message": f"AI Mode {'enabled' if enabled else 'disabled'}",
            "ai_mode_enabled": enabled
        }
    except Exception as e:
        logger.error(f"AI mode toggle error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@user_router.post("/settings/{telegram_id}/voice-preference")
async def set_voice_preference(telegram_id: int, request: Request):
    """Sets voice preference."""
    try:
        data = await request.json()
        preference = data.get("preference", "text")  # text, voice, both
        
        if preference not in ["text", "voice", "both"]:
            raise HTTPException(status_code=400, detail="Invalid preference")
        
        UserModel.set_voice_preference(telegram_id, preference)
        
        return {
            "status": "ok",
            "message": f"Voice preference set to {preference}",
            "voice_preference": preference
        }
    except Exception as e:
        logger.error(f"Voice preference error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@user_router.post("/logout/{telegram_id}")
async def logout_user(telegram_id: int):
    """Logs out user."""
    try:
        success = LoginModel.logout_user(telegram_id)
        
        if success:
            return {"status": "ok", "message": "Logged out successfully"}
        else:
            raise HTTPException(status_code=400, detail="Logout failed")
    except Exception as e:
        logger.error(f"Logout error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ===== HEALTH CHECK =====

@user_router.get("/health")
async def health_check():
    """Health check endpoint."""
    return {
        "status": "ok",
        "service": "User API"
    }