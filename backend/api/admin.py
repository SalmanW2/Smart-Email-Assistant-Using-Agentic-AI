from fastapi import APIRouter, Depends, Header, HTTPException
from db.models import db_manager
from typing import Dict

router = APIRouter()

async def get_current_admin(x_admin_email: str | None = Header(None)) -> Dict:
    if not x_admin_email:
        raise HTTPException(status_code=401, detail="Missing admin header")

    admins = await db_manager.get_admin_users()
    admin = next((entry for entry in admins if entry.get("email") == x_admin_email), None)
    if not admin:
        raise HTTPException(status_code=403, detail="Not authorized")

    return admin

@router.get("/stats")
async def get_stats(admin: Dict = Depends(get_current_admin)):
    return {
        "total_users": await db_manager.count_table("users"),
        "total_emails_processed": await db_manager.count_table("conversation_history"),
        "active_sessions": await db_manager.count_table("auth_sessions"),
    }

@router.get("/users")
async def get_users(admin: Dict = Depends(get_current_admin)):
    return await db_manager.get_all_users()

@router.post("/block/{telegram_id}")
async def block_user(telegram_id: int, admin: Dict = Depends(get_current_admin)):
    def action():
        return db_manager.db.client.table("blocked_users").insert({"telegram_id": telegram_id}).execute()

    await db_manager.db.run(action)
    return {"message": "User blocked"}

@router.delete("/block/{telegram_id}")
async def unblock_user(telegram_id: int, admin: Dict = Depends(get_current_admin)):
    def action():
        return db_manager.db.client.table("blocked_users").delete().eq("telegram_id", telegram_id).execute()

    await db_manager.db.run(action)
    return {"message": "User unblocked"}