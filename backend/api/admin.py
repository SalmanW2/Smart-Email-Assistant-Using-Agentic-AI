import os
import jwt
from datetime import datetime, timedelta, timezone
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel, EmailStr
from typing import Dict
from db.models import db_manager

router = APIRouter()
security = HTTPBearer()

# --- JWT Configuration ---
JWT_SECRET = os.getenv("JWT_SECRET", "super-secret-enterprise-key-321")
ALGORITHM = "HS256"

# --- Pydantic Models ---
class AdminLoginPayload(BaseModel):
    email: EmailStr
    password: str

class SetPasswordPayload(BaseModel):
    email: EmailStr
    password: str

class AddAdminPayload(BaseModel):
    email: EmailStr
    role: str = "admin"

# --- Decoupled JWT Dependency ---
async def get_current_admin(credentials: HTTPAuthorizationCredentials = Depends(security)) -> Dict:
    token = credentials.credentials
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[ALGORITHM])
        email = payload.get("sub")
        role = payload.get("role")
        if email is None:
            raise HTTPException(status_code=401, detail="Invalid token payload")
        return {"email": email, "role": role}
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Session expired. Please login again.")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid authentication token.")

# --- Pure JSON API Endpoints ---
@router.post("/login")
async def admin_login(payload: AdminLoginPayload):
    """Pure API endpoint returning JWT token."""
    is_valid = await db_manager.verify_admin_password(payload.email, payload.password)
    if not is_valid:
        raise HTTPException(status_code=401, detail="Invalid email or password")
    
    role = await db_manager.get_admin_role(payload.email)
    
    # Generate JWT Token (Expires in 24 hours)
    expire = datetime.now(timezone.utc) + timedelta(hours=24)
    token_data = {"sub": payload.email, "role": role, "exp": expire}
    access_token = jwt.encode(token_data, JWT_SECRET, algorithm=ALGORITHM)
    
    return {"status": "success", "token": access_token, "email": payload.email, "role": role}

@router.post("/set-password")
async def set_admin_password(payload: SetPasswordPayload, admin: Dict = Depends(get_current_admin)):
    if admin.get("email") != payload.email and admin.get("role") != "super_admin":
        raise HTTPException(status_code=403, detail="Cannot change another user's password")
    
    success = await db_manager.set_admin_password(payload.email, payload.password)
    if not success:
        raise HTTPException(status_code=500, detail="Failed to set password")
    return {"message": "Password set successfully"}

@router.get("/role")
async def get_role(admin: Dict = Depends(get_current_admin)):
    return {"role": admin.get("role", "admin")}

@router.get("/stats")
async def get_stats(admin: Dict = Depends(get_current_admin)):
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
    return await db_manager.get_all_users() or []

@router.post("/users/{telegram_id}/approve")
async def approve_user(telegram_id: int, admin: Dict = Depends(get_current_admin)):
    try:
        await db_manager.update_user_status(telegram_id, is_verified=True, status="approved")
        return {"message": "User approved successfully"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/users/{telegram_id}/block")
async def block_user(telegram_id: int, reason: str = Query("Blocked by Admin"), admin: Dict = Depends(get_current_admin)):
    try:
        await db_manager.update_user_status(telegram_id, is_verified=False, status="blocked", reason=reason)
        return {"message": "User blocked successfully"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/admins")
async def get_admins(admin: Dict = Depends(get_current_admin)):
    return await db_manager.get_admin_users() or []

@router.post("/admins")
async def add_new_admin(payload: AddAdminPayload, admin: Dict = Depends(get_current_admin)):
    if admin.get("role") != "super_admin":
        raise HTTPException(status_code=403, detail="Super Admin access required")
    success = await db_manager.add_admin_user(payload.email, payload.role, added_by=admin.get("email"))
    if not success:
        raise HTTPException(status_code=500, detail="Failed to add admin")
    return {"message": "Admin added successfully"}

@router.delete("/admins/{id_or_email}")
async def remove_admin(id_or_email: str, admin: Dict = Depends(get_current_admin)):
    if admin.get("role") != "super_admin":
        raise HTTPException(status_code=403, detail="Super Admin access required")
    success = await db_manager.remove_admin_user(id_or_email)
    if not success:
        raise HTTPException(status_code=500, detail="Failed to remove admin")
    return {"message": "Admin removed"}

@router.get("/blocks")
async def get_all_blocks(admin: Dict = Depends(get_current_admin)):
    try:
        return await db_manager.get_all_blocked_users() or []
    except Exception:
        return []

@router.delete("/blocks/{id_or_telegram_id}")
async def unblock_user(id_or_telegram_id: str, admin: Dict = Depends(get_current_admin)):
    try:
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
    return {"message": "Logged out successfully"}