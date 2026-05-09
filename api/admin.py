from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from db.models import DBManager, supabase

router = APIRouter(prefix="/api/admin", tags=["Admin"])

def verify_admin(email: str):
    admin_data = DBManager.is_admin(email)
    if not admin_data:
        raise HTTPException(status_code=403, detail="Not authorized")
    return admin_data

@router.get("/stats")
async def get_dashboard_stats(email: str):
    """Fetches system statistics for the Super Admin."""
    verify_admin(email)
    
    users_count = supabase.table("users").select("id", count="exact").execute().count
    summaries_count = supabase.table("conversation_summaries").select("id", count="exact").execute().count
    
    return {
        "total_users": users_count,
        "total_ai_interactions": summaries_count,
        "status": "healthy"
    }

@router.get("/users")
async def get_all_users(email: str):
    verify_admin(email)
    response = supabase.table("users").select("telegram_id, first_name, is_verified, ai_mode_enabled").execute()
    return response.data