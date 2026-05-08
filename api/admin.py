"""
Admin API Endpoints
Handles admin dashboard operations
"""

import logging
from fastapi import APIRouter, Request, Form, HTTPException
from fastapi.responses import JSONResponse

from db.models import (
    AdminModel, UserAdminModel, BlocklistModel,
    UserModel
)

logger = logging.getLogger(__name__)

admin_router = APIRouter(prefix="/api/admin", tags=["admin"])


# ===== USER MANAGEMENT =====

@admin_router.get("/users")
async def get_all_users():
    """Gets all users."""
    try:
        users = UserAdminModel.get_all_users()
        
        return {
            "status": "ok",
            "count": len(users),
            "data": users
        }
    except Exception as e:
        logger.error(f"Users fetch error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@admin_router.get("/users/{telegram_id}")
async def get_user(telegram_id: int):
    """Gets specific user."""
    try:
        user = UserModel.get_user(telegram_id)
        
        if not user:
            raise HTTPException(status_code=404, detail="User not found")
        
        return {
            "status": "ok",
            "data": user
        }
    except Exception as e:
        logger.error(f"User fetch error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@admin_router.post("/users/{telegram_id}/status")
async def update_user_status(telegram_id: int, request: Request):
    """Updates user verification status."""
    try:
        data = await request.json()
        is_verified = data.get("is_verified", False)
        status = data.get("status", "pending")  # pending, approved, blocked
        reason = data.get("reason", "")
        
        success = UserAdminModel.update_user_status(
            telegram_id, is_verified, status, reason
        )
        
        if success:
            return {
                "status": "ok",
                "message": f"User status updated to {status}"
            }
        else:
            raise HTTPException(status_code=500, detail="Failed to update status")
    except Exception as e:
        logger.error(f"Status update error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ===== BLOCKLIST MANAGEMENT =====

@admin_router.get("/blocklist")
async def get_blocklist():
    """Gets all blocked records."""
    try:
        blocked = BlocklistModel.get_all_blocked()
        
        return {
            "status": "ok",
            "count": len(blocked),
            "data": blocked
        }
    except Exception as e:
        logger.error(f"Blocklist fetch error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@admin_router.post("/blocklist/add")
async def block_user(request: Request):
    """Adds user to blocklist."""
    try:
        data = await request.json()
        
        block_type = data.get("block_type")  # telegram, email
        block_value = data.get("block_value")
        reason = data.get("reason", "No reason provided")
        blocked_by = data.get("blocked_by", "admin")
        
        if not block_type or not block_value:
            raise HTTPException(status_code=400, detail="Missing block_type or block_value")
        
        success = BlocklistModel.block_user(block_type, block_value, reason, blocked_by)
        
        if success:
            return {
                "status": "ok",
                "message": f"Blocked {block_type}: {block_value}"
            }
        else:
            raise HTTPException(status_code=500, detail="Failed to block user")
    except Exception as e:
        logger.error(f"Block error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@admin_router.post("/blocklist/remove/{record_id}")
async def remove_blocked_record(record_id: str):
    """Removes a blocked record."""
    try:
        success = BlocklistModel.remove_blocked_record(record_id)
        
        if success:
            return {
                "status": "ok",
                "message": "Block removed"
            }
        else:
            raise HTTPException(status_code=404, detail="Record not found")
    except Exception as e:
        logger.error(f"Remove block error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@admin_router.post("/blocklist/unblock")
async def unblock_user(request: Request):
    """Unblocks a user."""
    try:
        data = await request.json()
        
        block_type = data.get("block_type")
        block_value = data.get("block_value")
        
        if not block_type or not block_value:
            raise HTTPException(status_code=400, detail="Missing parameters")
        
        success = BlocklistModel.unblock_user(block_type, block_value)
        
        if success:
            return {
                "status": "ok",
                "message": "User unblocked"
            }
        else:
            raise HTTPException(status_code=404, detail="Record not found")
    except Exception as e:
        logger.error(f"Unblock error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ===== ADMIN MANAGEMENT =====

@admin_router.get("/admins")
async def get_all_admins():
    """Gets all admins."""
    try:
        admins = AdminModel.get_all_admins()
        
        return {
            "status": "ok",
            "count": len(admins),
            "data": admins
        }
    except Exception as e:
        logger.error(f"Admins fetch error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@admin_router.post("/admins/add")
async def add_admin(request: Request):
    """Adds new admin."""
    try:
        data = await request.json()
        
        email = data.get("email")
        role = data.get("role", "admin")
        added_by = data.get("added_by", "system")
        
        if not email:
            raise HTTPException(status_code=400, detail="Email required")
        
        if role not in ["admin", "super_admin"]:
            raise HTTPException(status_code=400, detail="Invalid role")
        
        # Check if already exists
        if AdminModel.check_admin(email):
            raise HTTPException(status_code=400, detail="Admin already exists")
        
        success = AdminModel.add_admin(email, role, added_by)
        
        if success:
            return {
                "status": "ok",
                "message": f"Admin {email} added with role {role}"
            }
        else:
            raise HTTPException(status_code=500, detail="Failed to add admin")
    except Exception as e:
        logger.error(f"Add admin error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@admin_router.delete("/admins/{admin_id}")
async def remove_admin(admin_id: str):
    """Removes admin."""
    try:
        success = AdminModel.remove_admin(admin_id)
        
        if success:
            return {
                "status": "ok",
                "message": "Admin removed"
            }
        else:
            raise HTTPException(status_code=404, detail="Admin not found")
    except Exception as e:
        logger.error(f"Remove admin error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ===== ADMIN PASSWORD MANAGEMENT =====

@admin_router.post("/password/set")
async def set_admin_password(request: Request, email: str = Form(...), password: str = Form(...)):
    """Sets admin password."""
    try:
        # Validate password strength
        if len(password) < 6 or len(password) > 10:
            raise HTTPException(status_code=400, detail="Password must be 6-10 characters")
        
        # Check if admin exists
        if not AdminModel.check_admin(email):
            raise HTTPException(status_code=404, detail="Admin not found")
        
        success = AdminModel.set_admin_password(email, password)
        
        if success:
            return {
                "status": "ok",
                "message": "Password set successfully"
            }
        else:
            raise HTTPException(status_code=500, detail="Failed to set password")
    except Exception as e:
        logger.error(f"Set password error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@admin_router.post("/password/verify")
async def verify_admin_password(request: Request, email: str = Form(...), password: str = Form(...)):
    """Verifies admin password."""
    try:
        is_valid = AdminModel.verify_admin_password(email, password)
        
        return {
            "status": "ok",
            "valid": is_valid
        }
    except Exception as e:
        logger.error(f"Verify password error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ===== STATISTICS =====

@admin_router.get("/stats")
async def get_admin_stats():
    """Gets admin dashboard statistics."""
    try:
        users = UserAdminModel.get_all_users()
        blocked = BlocklistModel.get_all_blocked()
        admins = AdminModel.get_all_admins()
        
        approved_count = sum(1 for u in users if u.get("is_verified"))
        pending_count = sum(1 for u in users if not u.get("is_verified"))
        
        return {
            "status": "ok",
            "stats": {
                "total_users": len(users),
                "approved_users": approved_count,
                "pending_users": pending_count,
                "blocked_records": len(blocked),
                "total_admins": len(admins)
            }
        }
    except Exception as e:
        logger.error(f"Stats error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ===== HEALTH CHECK =====

@admin_router.get("/health")
async def health_check():
    """Health check endpoint."""
    return {
        "status": "ok",
        "service": "Admin API"
    }