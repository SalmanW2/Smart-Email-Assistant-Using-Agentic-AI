from fastapi import APIRouter, Depends, Header, HTTPException, Query
from pydantic import BaseModel, EmailStr
from db.models import db_manager
from typing import Dict, List, Optional
from datetime import datetime, timedelta

router = APIRouter()

# --- Pydantic Models for Validation ---
class AdminLoginPayload(BaseModel):
    email: EmailStr
    password: str

class SetPasswordPayload(BaseModel):
    email: EmailStr
    password: str

class AddAdminPayload(BaseModel):
    email: EmailStr
    role: str = "admin"

class PermissionPayload(BaseModel):
    is_verified: bool
    ai_allowed: bool
    voice_allowed: bool
    block_days: int = 0  # 0 means permanent if blocked
    reason: str = "Blocked by Admin"

async def get_current_admin(x_admin_email: str | None = Header(None)) -> Dict:
    if not x_admin_email:
        raise HTTPException(status_code=401, detail="Missing admin header")
    try:
        admins = await db_manager.get_admin_users()
        if admins is None: admins = []
    except Exception as e:
        raise HTTPException(status_code=500, detail="Database timeout/error")
        
    safe_email = x_admin_email.strip().lower()
    admin = next((entry for entry in admins if entry.get("email", "").strip().lower() == safe_email), None)
    
    if not admin:
        raise HTTPException(status_code=401, detail="Not authorized") 
    return admin

# --- Authentication Endpoints ---

@router.post("/login")
async def admin_login(payload: AdminLoginPayload):
    """Manual login for admins using email and password."""
    is_valid = await db_manager.verify_admin_password(payload.email, payload.password)
    if not is_valid:
        raise HTTPException(status_code=401, detail="Invalid email or password")
    
    role = await db_manager.get_admin_role(payload.email)
    return {"status": "success", "email": payload.email, "role": role}

@router.post("/set-password")
async def set_admin_password(payload: SetPasswordPayload, admin: Dict = Depends(get_current_admin)):
    """Set or update admin password."""
    if admin.get("email") != payload.email and admin.get("role") != "super_admin":
        raise HTTPException(status_code=403, detail="Cannot change another user's password")
    
    success = await db_manager.set_admin_password(payload.email, payload.password)
    if not success:
        raise HTTPException(status_code=500, detail="Failed to set password")
    return {"message": "Password set successfully"}

@router.get("/role")
async def get_role(admin: Dict = Depends(get_current_admin)):
    """Simple role check for frontend routing."""
    return {"role": admin.get("role", "admin")}

@router.get("/stats")
async def get_stats(admin: Dict = Depends(get_current_admin)):
    """Fetch all dashboard counters, including new STT and Scheduled Emails stats."""
    try:
        all_users = await db_manager.get_all_users() or []
        total_users = len(all_users)
        verified_users = sum(1 for u in all_users if u.get("is_verified"))
        
        try:
            # Note: Requires get_all_blocked_users in models.py
            blocked_users_list = await db_manager.get_all_blocked_users()
            blocked_count = len(blocked_users_list) if blocked_users_list else 0
        except Exception:
            blocked_count = 0
            
        admins_list = await db_manager.get_admin_users() or []
        
        # New Stats: Conversations
        try:
            history = await db_manager.get_all_conversation_history() or []
            total_conversations = len(history)
        except:
            total_conversations = 0

        # New Stats: STT Usage
        try:
            stt_res = await db_manager.db.run(lambda: db_manager.db.client.table("stt_usage").select("*").execute())
            stt_usage = stt_res.data if getattr(stt_res, 'data', None) else []
            total_stt_seconds_used = sum(item.get("duration_seconds", 0) for item in stt_usage)
        except:
            total_stt_seconds_used = 0

        # New Stats: Scheduled Emails
        try:
            sched_res = await db_manager.db.run(lambda: db_manager.db.client.table("scheduled_emails").select("*").execute())
            scheduled_emails = sched_res.data if getattr(sched_res, 'data', None) else []
            total_scheduled_emails = len(scheduled_emails)
        except:
            total_scheduled_emails = 0
        
        return {
            "total_users": total_users,
            "verified_users": verified_users,
            "blocked_users": blocked_count,
            "total_admins": len(admins_list),
            "total_conversations": total_conversations,
            "total_scheduled_emails": total_scheduled_emails,
            "total_stt_seconds_used": total_stt_seconds_used,
            "status": "online"
        }
    except Exception:
        return {
            "total_users": 0, "verified_users": 0, "blocked_users": 0, "total_admins": 0,
            "total_conversations": 0, "total_scheduled_emails": 0, "total_stt_seconds_used": 0, "status": "offline"
        }

@router.get("/users")
async def get_users(admin: Dict = Depends(get_current_admin)):
    """List all registered bot users."""
    return await db_manager.get_all_users() or []

@router.post("/users/{telegram_id}/permissions")
async def update_user_permissions(telegram_id: int, payload: PermissionPayload, admin: Dict = Depends(get_current_admin)):
    """Unified endpoint to handle Approve, Block, and Restrictions (AI/Voice)."""
    try:
        def _update():
            # 1. Update core user flags
            db_manager.db.client.table("users").update({
                "is_verified": payload.is_verified,
                "ai_allowed": payload.ai_allowed,
                "voice_allowed": payload.voice_allowed
            }).eq("telegram_id", telegram_id).execute()

            # 2. Handle Blocklist logic
            if not payload.is_verified:
                expires_at = None
                if payload.block_days > 0:
                    expires_at = (datetime.utcnow() + timedelta(days=payload.block_days)).isoformat()
                
                existing = db_manager.db.client.table("blocked_users").select("*").eq("block_value", str(telegram_id)).execute()
                if not existing.data:
                    db_manager.db.client.table("blocked_users").insert({
                        "block_type": "telegram_id",
                        "block_value": str(telegram_id),
                        "reason": payload.reason,
                        "expires_at": expires_at
                    }).execute()
                else:
                    db_manager.db.client.table("blocked_users").update({
                        "expires_at": expires_at,
                        "reason": payload.reason
                    }).eq("block_value", str(telegram_id)).execute()
            else:
                # If verified, ensure they are NOT in blocklist
                db_manager.db.client.table("blocked_users").delete().eq("block_value", str(telegram_id)).execute()

        await db_manager.db.run(_update)
        return {"message": "User permissions updated successfully"}
    except Exception as e:
        print(f"Permission update error: {e}")
        raise HTTPException(status_code=500, detail="Database Error: " + str(e))    

@router.get("/admins")
async def get_admins(admin: Dict = Depends(get_current_admin)):
    """List all admin users."""
    return await db_manager.get_admin_users() or []

@router.post("/admins")
async def add_new_admin(payload: AddAdminPayload, admin: Dict = Depends(get_current_admin)):
    """Add a new admin email to the system."""
    if admin.get("role") != "super_admin":
        raise HTTPException(status_code=403, detail="Super Admin access required")
    success = await db_manager.add_admin_user(payload.email, payload.role, added_by=admin.get("email"))
    if not success:
        raise HTTPException(status_code=500, detail="Failed to add admin")
    return {"message": "Admin added successfully"}

@router.delete("/admins/{id_or_email}")
async def remove_admin(id_or_email: str, admin: Dict = Depends(get_current_admin)):
    """Remove admin privileges."""
    if admin.get("role") != "super_admin":
        raise HTTPException(status_code=403, detail="Super Admin access required")
    success = await db_manager.remove_admin_user(id_or_email)
    if not success:
        raise HTTPException(status_code=500, detail="Failed to remove admin")
    return {"message": "Admin removed"}

@router.get("/blocks")
async def get_all_blocks(admin: Dict = Depends(get_current_admin)):
    """List all blocked identifiers."""
    try:
        # Note: Requires get_all_blocked_users in models.py
        return await db_manager.get_all_blocked_users() or []
    except Exception:
        return []

@router.delete("/blocks/{id_or_telegram_id}")
async def unblock_user(id_or_telegram_id: str, admin: Dict = Depends(get_current_admin)):
    """Remove a user from the blocklist."""
    try:
        # Check if it's a telegram_id (numeric) or UUID string
        if id_or_telegram_id.isdigit():
            success = await db_manager.unblock_user(int(id_or_telegram_id))
        else:
            await db_manager.db.run(lambda: db_manager.db.client.table("blocked_users").delete().eq("id", id_or_telegram_id).execute())
            success = True
            
        if not success:
            raise HTTPException(status_code=500, detail="Failed to unblock user")
        return {"message": "User unblocked"}
    except Exception:
        raise HTTPException(status_code=500, detail="Failed to process unblock request")

@router.post("/logout")
async def logout():
    """Logout handler."""
    return {"message": "Logged out successfully"}

# ==========================================
# NEW FEATURES DATA EXPOSURE
# ==========================================
@router.get("/scheduled_emails")
async def get_scheduled_emails(admin: Dict = Depends(get_current_admin)):
    """Fetch all scheduled emails for monitoring."""
    try:
        res = await db_manager.db.run(lambda: db_manager.db.client.table("scheduled_emails").select("*").order("created_at", desc=True).execute())
        return {"scheduled_emails": res.data if getattr(res, 'data', None) else []}
    except Exception as e:
        print(f"Error fetching scheduled emails: {e}")
        raise HTTPException(status_code=500, detail="Internal Server Error")

@router.get("/stt_usage")
async def get_stt_usage(admin: Dict = Depends(get_current_admin)):
    """Fetch speech-to-text analytics and duration tracking."""
    try:
        res = await db_manager.db.run(lambda: db_manager.db.client.table("stt_usage").select("*").order("created_at", desc=True).execute())
        return {"stt_usage": res.data if getattr(res, 'data', None) else []}
    except Exception as e:
        print(f"Error fetching STT usage: {e}")
        raise HTTPException(status_code=500, detail="Internal Server Error")
        
@router.get("/saved_attachments")
async def get_saved_attachments(admin: Dict = Depends(get_current_admin)):
    """Fetch logs of files and documents permanently memorized by AI."""
    try:
        res = await db_manager.db.run(lambda: db_manager.db.client.table("saved_attachments").select("*").order("created_at", desc=True).execute())
        return {"saved_attachments": res.data if getattr(res, 'data', None) else []}
    except Exception as e:
        print(f"Error fetching saved attachments: {e}")
        raise HTTPException(status_code=500, detail="Internal Server Error")