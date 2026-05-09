from fastapi import APIRouter, Depends, HTTPException
from db.models import db_manager
from typing import List, Dict, Any

router = APIRouter()

async def verify_admin(user_id: str):
    user = await db_manager.get_user(int(user_id))
    if not user or user['role'] not in ['admin', 'super_admin']:
        raise HTTPException(status_code=403, detail="Not authorized")
    return user

@router.get("/stats")
async def get_stats(admin = Depends(verify_admin)):
    # Get system stats
    users_count = len(await db_manager.client.table("users").select("id").execute().data)
    emails_count = len(await db_manager.client.table("conversation_history").select("id").execute().data)
    
    return {
        "total_users": users_count,
        "total_emails_processed": emails_count,
        "active_sessions": len(await db_manager.client.table("auth_sessions").select("id").execute().data)
    }

@router.get("/users")
async def get_users(admin = Depends(verify_admin)):
    users = await db_manager.client.table("users").select("*").execute().data
    return users

@router.post("/block/{telegram_id}")
async def block_user(telegram_id: int, admin = Depends(verify_admin)):
    # Add to blocked_users
    await db_manager.client.table("blocked_users").insert({"telegram_id": telegram_id}).execute()
    return {"message": "User blocked"}

@router.delete("/block/{telegram_id}")
async def unblock_user(telegram_id: int, admin = Depends(verify_admin)):
    await db_manager.client.table("blocked_users").delete().eq("telegram_id", telegram_id).execute()
    return {"message": "User unblocked"}