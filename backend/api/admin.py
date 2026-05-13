from fastapi import APIRouter, Depends, Header, HTTPException, Query
from pydantic import BaseModel, EmailStr
from db.models import db_manager
from typing import Dict, List, Optional

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

# --- Auth Dependency (No Auto-Logout on Timeout) ---
async def get_current_admin(x_admin_email: str | None = Header(None)) -> Dict:
    if not x_admin_email:
        raise HTTPException(status_code=401, detail="Missing admin header")
    try:
        admins = await db_manager.get_admin_users()
    except Exception as e:
        # Agar DB sleep ho, toh 500 error do taake frontend logout na kare
        raise HTTPException(status_code=500, detail="Database timeout/error")
        
    admin = next((entry for entry in admins if entry.get("email") == x_admin_email), None)
    if not admin:
        # Sirf 401 par frontend logout karega
        raise HTTPException(status_code=401, detail="Not authorized") 
    return admin

@router.delete("/blocks/{id_or_telegram_id}")
async def unblock_user(id_or_telegram_id: str, admin: Dict = Depends(get_current_admin)):
    """Remove a user from the blocklist correctly."""
    try:
        # Check if input is numeric (Telegram ID)
        if id_or_telegram_id.isdigit():
            success = await db_manager.unblock_user(int(id_or_telegram_id))
        else:
            # It's a record UUID from the table. 
            # We delete it directly from the blocked_users table using the database client.
            # Assuming db_manager has access to the client.
            from db.models import supabase
            res = supabase.table("blocked_users").delete().eq("id", id_or_telegram_id).execute()
            success = len(res.data) >= 0 # If no error, it's a success
            
        if not success:
            raise HTTPException(status_code=500, detail="Failed to unblock user")
            
        return {"message": "User unblocked"}
    except Exception as e:
        print(f"Unblock error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

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
    """Fetch all dashboard counters."""
    try:
        all_users = await db_manager.get_all_users() or []
        total_users = len(all_users)
        verified_users = sum(1 for u in all_users if u.get("is_verified"))
        
        try:
            blocked_users_list = await db_manager.get_all_blocked_users()
            blocked_count = len(blocked_users_list) if blocked_users_list else 0
        except Exception:
            blocked_count = 0
            
        admins_list = await db_manager.get_admin_users() or []
        
        return {
            "total_users": total_users,
            "verified_users": verified_users,
            "blocked_users": blocked_count,
            "total_admins": len(admins_list),
        }
    except Exception:
        return {"total_users": 0, "verified_users": 0, "blocked_users": 0, "total_admins": 0}

@router.get("/users")
async def get_users(admin: Dict = Depends(get_current_admin)):
    """List all registered bot users."""
    return await db_manager.get_all_users() or []

@router.post("/users/{telegram_id}/approve")
async def approve_user(telegram_id: int, admin: Dict = Depends(get_current_admin)):
    """Approve a pending user and remove from blocklist."""
    try:
        def _approve():
            # 1. Update is_verified to True
            db_manager.db.client.table("users").update({"is_verified": True}).eq("telegram_id", telegram_id).execute()
            # 2. Lazmi Blocklist se nikalein (Unrevoke)
            db_manager.db.client.table("blocked_users").delete().eq("block_value", str(telegram_id)).execute()

        await db_manager.db.run(_approve)
        return {"message": "User authorized and unblocked successfully"}
    except Exception as e:
        print(f"Approve error: {e}")
        raise HTTPException(status_code=500, detail="Backend Database Error: " + str(e))

@router.post("/users/{telegram_id}/block")
async def block_user(telegram_id: int, reason: str = Query("Blocked by Admin"), admin: Dict = Depends(get_current_admin)):
    """Block a user from using the bot."""
    try:
        def _block():
            # 1. Update user is_verified to False
            db_manager.db.client.table("users").update({"is_verified": False}).eq("telegram_id", telegram_id).execute()
            # 2. Blocklist mein daalein
            existing = db_manager.db.client.table("blocked_users").select("*").eq("block_value", str(telegram_id)).execute()
            if not existing.data:
                db_manager.db.client.table("blocked_users").insert({
                    "block_type": "telegram_id",
                    "block_value": str(telegram_id),
                    "reason": reason
                }).execute()

        await db_manager.db.run(_block)
        return {"message": "User access revoked successfully"}
    except Exception as e:
        print(f"Block error: {e}")
        raise HTTPException(status_code=500, detail="Backend Database Error: " + str(e))
    

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