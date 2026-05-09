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

# --- Auth Dependency ---
async def get_current_admin(x_admin_email: str | None = Header(None)) -> Dict:
    if not x_admin_email:
        raise HTTPException(status_code=401, detail="Missing admin header")
    try:
        admins = await db_manager.get_admin_users()
    except Exception:
        admins = []
    admin = next((entry for entry in admins if entry.get("email") == x_admin_email), None)
    if not admin:
        raise HTTPException(status_code=403, detail="Not authorized")
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
async def set_admin_password(payload: SetPasswordPayload):
    """Set or update admin password after first Google OAuth login."""
    is_admin = await db_manager.check_admin(payload.email)
    if not is_admin:
        raise HTTPException(status_code=403, detail="Only recognized admins can set passwords")
    
    success = await db_manager.set_admin_password(payload.email, payload.password)
    if not success:
        raise HTTPException(status_code=500, detail="Failed to set password")
    return {"message": "Password set successfully"}

@router.get("/role")
async def get_role(x_admin_email: str | None = Header(None)):
    """Simple role check for frontend routing."""
    if not x_admin_email:
        raise HTTPException(status_code=401, detail="Missing admin header")
    try:
        role = await db_manager.get_admin_role(x_admin_email)
        return {"role": role}
    except Exception:
        raise HTTPException(status_code=500, detail="Failed to get role")

# --- Dashboard & Stats ---

@router.get("/stats")
async def get_stats(admin: Dict = Depends(get_current_admin)):
    """Fetch all dashboard counters."""
    try:
        all_users = await db_manager.get_all_users() or []
        total_users = len(all_users)
        verified_users = sum(1 for u in all_users if u.get("is_verified"))
        
        # Try to get blocked users count
        try:
            blocked_users_list = await db_manager.get_all_blocked_users() # Needs implementation in models.py
            blocked_count = len(blocked_users_list) if blocked_users_list else 0
        except:
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

# --- User Management ---

@router.get("/users")
async def get_users(admin: Dict = Depends(get_current_admin)):
    """List all registered bot users."""
    return await db_manager.get_all_users() or []

@router.post("/users/{telegram_id}/approve")
async def approve_user(telegram_id: int, admin: Dict = Depends(get_current_admin)):
    """Approve a pending user."""
    success = await db_manager.update_user(telegram_id, {"is_verified": True})
    if not success:
        raise HTTPException(status_code=500, detail="Failed to approve user")
    return {"message": "User approved successfully"}

@router.post("/users/{telegram_id}/block")
async def block_user(telegram_id: int, reason: str = Query(""), admin: Dict = Depends(get_current_admin)):
    """Block a user from using the bot."""
    success = await db_manager.block_user(telegram_id)
    if not success:
        raise HTTPException(status_code=500, detail="Failed to block user")
    return {"message": "User blocked"}

# --- Admin Management ---

@router.get("/admins")
async def get_admins(admin: Dict = Depends(get_current_admin)):
    """List all admin users."""
    return await db_manager.get_admin_users() or []

@router.post("/admins")
async def add_new_admin(payload: AddAdminPayload, admin: Dict = Depends(get_current_admin)):
    """Add a new admin email to the system."""
    success = await db_manager.add_admin_user(payload.email, payload.role)
    if not success:
        raise HTTPException(status_code=500, detail="Failed to add admin")
    return {"message": "Admin added successfully"}

@router.delete("/admins/{email}")
async def remove_admin(email: str, admin: Dict = Depends(get_current_admin)):
    """Remove admin privileges from an email."""
    success = await db_manager.remove_admin_user(email)
    if not success:
        raise HTTPException(status_code=500, detail="Failed to remove admin")
    return {"message": "Admin removed"}

# --- Blocklist Management ---

@router.get("/blocks")
async def get_all_blocks(admin: Dict = Depends(get_current_admin)):
    """List all blocked identifiers."""
    try:
        return await db_manager.get_all_blocked_users() or []
    except:
        return []

@router.delete("/blocks/{telegram_id}")
async def unblock_user(telegram_id: int, admin: Dict = Depends(get_current_admin)):
    """Remove a user from the blocklist."""
    success = await db_manager.unblock_user(telegram_id)
    if not success:
        raise HTTPException(status_code=500, detail="Failed to unblock user")
    return {"message": "User unblocked"}

@router.post("/logout")
async def logout():
    return {"message": "Logged out successfully"}