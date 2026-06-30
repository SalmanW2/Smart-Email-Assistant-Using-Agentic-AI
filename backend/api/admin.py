import jwt
import httpx
import asyncio
from fastapi import APIRouter, Depends, Header, HTTPException, Query
from pydantic import BaseModel, EmailStr
from typing import Dict, List, Optional
from datetime import datetime, timedelta
from db.models import db_manager
from config import settings

router = APIRouter()

# --- JWT Configuration ---
SECRET_KEY = getattr(settings, "JWT_SECRET", settings.BOT_TOKEN)
ALGORITHM = "HS256"

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

class PasswordChangeRequest(BaseModel):
    current_password: Optional[str] = ""
    new_password: str
    
# --- Helper: Telegram Notification ---
async def send_telegram_notification(telegram_id: int, message: str, reply_markup: dict = None):
    """Sends a background notification directly to the user via Telegram API."""
    url = f"https://api.telegram.org/bot{settings.BOT_TOKEN}/sendMessage"
    payload = {"chat_id": telegram_id, "text": message, "parse_mode": "Markdown"}
    if reply_markup:
        payload["reply_markup"] = reply_markup
        
    try:
        async with httpx.AsyncClient() as client:
            await client.post(url, json=payload)
    except Exception as e:
        print(f"Failed to send telegram notification: {e}")

# --- Secure Admin Dependency ---
async def get_current_admin(
    authorization: str | None = Header(None), 
    x_admin_email: str | None = Header(None)
) -> Dict:
    email = None
    
    # 1. Try JWT Bearer Token first
    if authorization and authorization.startswith("Bearer "):
        token = authorization.split(" ")[1]
        try:
            payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
            email = payload.get("sub")
        except jwt.ExpiredSignatureError:
            raise HTTPException(status_code=401, detail="Token has expired")
        except jwt.PyJWTError:
            raise HTTPException(status_code=401, detail="Invalid token")

    # 2. Fallback to raw email header
    if not email and x_admin_email:
        email = x_admin_email
        
    if not email:
        raise HTTPException(status_code=401, detail="Missing authentication")
        
    try:
        admins = await db_manager.get_admin_users()
        if admins is None: admins = []
    except Exception as e:
        raise HTTPException(status_code=500, detail="Database timeout/error")
        
    safe_email = email.strip().lower()
    admin = next((entry for entry in admins if entry.get("email", "").strip().lower() == safe_email), None)
    
    if not admin:
        raise HTTPException(status_code=401, detail="Not authorized") 
    return admin

# --- Authentication Endpoints ---

from fastapi.security import OAuth2PasswordRequestForm

@router.post("/login")
async def admin_login(form_data: OAuth2PasswordRequestForm = Depends()):
    is_valid = await db_manager.verify_admin_password(form_data.username, form_data.password)
    if not is_valid:
        raise HTTPException(status_code=401, detail="Invalid email or password")
    
    role = await db_manager.get_admin_role(form_data.username)
    
    expire = datetime.utcnow() + timedelta(hours=24)
    to_encode = {"sub": form_data.username, "role": role, "exp": expire}
    token = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    
    return {
        "status": "success", 
        "token": token,  
        "email": form_data.username, 
        "role": role
    }

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

@router.get("/cache-stats")
async def get_cache_stats(admin: Dict = Depends(get_current_admin)):
    from bot.gmail_client import GmailClient
    return {
        "hits": GmailClient.cache_hits,
        "misses": GmailClient.cache_misses,
        "user_count": len(GmailClient._token_cache)
    }

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
        
        try:
            history = await db_manager.get_all_conversation_history() or []
            total_conversations = len(history)
        except:
            total_conversations = 0

        try:
            stt_res = await db_manager.db.run(lambda: db_manager.db.client.table("stt_usage").select("*").execute())
            stt_usage = stt_res.data if getattr(stt_res, 'data', None) else []
            total_stt_seconds_used = sum(item.get("duration_seconds", 0) for item in stt_usage)
        except:
            total_stt_seconds_used = 0

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
    return await db_manager.get_all_users() or []

@router.post("/users/{telegram_id}/permissions")
async def update_user_permissions(telegram_id: int, payload: PermissionPayload, admin: Dict = Depends(get_current_admin)):
    try:
        def _update():
            db_manager.db.client.table("users").update({
                "is_verified": payload.is_verified,
                "ai_allowed": payload.ai_allowed,
                "voice_allowed": payload.voice_allowed
            }).eq("telegram_id", telegram_id).execute()

            if not payload.is_verified:
                expires_at = None
                if payload.block_days > 0:
                    expires_at = (datetime.utcnow() + timedelta(days=payload.block_days)).isoformat()
                
                existing = db_manager.db.client.table("blocked_users").select("*").eq("block_value", str(telegram_id)).execute()
                if not existing.data:
                    db_manager.db.client.table("blocked_users").insert({
                        "block_type": "telegram",
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
                db_manager.db.client.table("blocked_users").delete().eq("block_value", str(telegram_id)).execute()

        await db_manager.db.run(_update)
        db_manager._invalidate_cache(["all_users", "all_blocked_users", "active_auto_check_users"])
        
        # --- DYNAMIC NOTIFICATION & BUTTON LOGIC ---
        admin_email = admin.get("email", "System Administrator")
        user = await db_manager.get_user(telegram_id)
        has_auth_token = bool(user and user.get("auth_token"))
        reply_markup = None

        if payload.is_verified:
            if has_auth_token:
                msg = f"🎉 *Account Approved!*\nYour access to the AI Email Assistant has been restored.\n\n👤 *Action by:* {admin_email}"
                reply_markup = {"inline_keyboard": [[{"text": "🔙 Go to Main Menu", "callback_data": "menu_main"}]]}
            else:
                msg = f"🎉 *Account Approved!*\nYour application is accepted. Please link your Gmail account to start using the assistant.\n\n👤 *Action by:* {admin_email}"
                state_uuid = await db_manager.create_auth_session(telegram_id)
                login_url = f"{settings.APP_URL}/api/auth/telegram_login?state={state_uuid}&telegram_id={telegram_id}"
                reply_markup = {"inline_keyboard": [[{"text": "🔗 Connect Google Workspace", "url": login_url}]]}
                
            if not payload.ai_allowed or not payload.voice_allowed:
                msg += "\n\n⚠️ *Note:* Some advanced features might be restricted."
        else:
            if payload.block_days > 0:
                msg = f"🚫 *Account Suspended*\nYour access has been temporarily suspended for {payload.block_days} days.\n\n👤 *Action by:* {admin_email}\n*Reason:* {payload.reason}"
            else:
                msg = f"🚫 *Account Blocked*\nYour access has been permanently revoked.\n\n👤 *Action by:* {admin_email}\n*Reason:* {payload.reason}"
        
        asyncio.create_task(send_telegram_notification(telegram_id, msg, reply_markup))
        
        return {"message": "User permissions updated successfully"}
    except Exception as e:
        print(f"Permission update error: {e}")
        raise HTTPException(status_code=500, detail="Database Error: " + str(e))    

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
        telegram_id = None
        if id_or_telegram_id.isdigit():
            telegram_id = int(id_or_telegram_id)
            success = await db_manager.unblock_user(telegram_id)
        else:
            block_record = await db_manager.db.run(lambda: db_manager.db.client.table("blocked_users").select("block_value").eq("id", id_or_telegram_id).execute())
            if block_record.data:
                telegram_id = int(block_record.data[0]["block_value"])
                
            await db_manager.db.run(lambda: db_manager.db.client.table("blocked_users").delete().eq("id", id_or_telegram_id).execute())
            db_manager._invalidate_cache(["all_users", "all_blocked_users", "active_auto_check_users"])
            success = True
            
        if not success:
            raise HTTPException(status_code=500, detail="Failed to unblock user")
            
        if telegram_id:
            msg = "✅ *Account Restored!*\nYour restriction has been lifted by the Admin."
            kb = {"inline_keyboard": [[{"text": "🔙 Go to Main Menu", "callback_data": "menu_main"}]]}
            asyncio.create_task(send_telegram_notification(telegram_id, msg, kb))

        return {"message": "User unblocked"}
    except Exception as e:
        print(f"Unblock error: {e}")
        raise HTTPException(status_code=500, detail="Failed to process unblock request")

@router.post("/logout")
async def logout():
    return {"message": "Logged out successfully"}

@router.get("/scheduled_emails")
async def get_scheduled_emails(admin: Dict = Depends(get_current_admin)):
    try:
        res = await db_manager.db.run(lambda: db_manager.db.client.table("scheduled_emails").select("*").order("created_at", desc=True).execute())
        return {"scheduled_emails": res.data if getattr(res, 'data', None) else []}
    except Exception as e:
        print(f"Error fetching scheduled emails: {e}")
        raise HTTPException(status_code=500, detail="Internal Server Error")

@router.get("/stt_usage")
async def get_stt_usage(admin: Dict = Depends(get_current_admin)):
    try:
        res = await db_manager.db.run(lambda: db_manager.db.client.table("stt_usage").select("*").order("created_at", desc=True).execute())
        return {"stt_usage": res.data if getattr(res, 'data', None) else []}
    except Exception as e:
        print(f"Error fetching STT usage: {e}")
        raise HTTPException(status_code=500, detail="Internal Server Error")
        
@router.get("/saved_attachments")
async def get_saved_attachments(admin: Dict = Depends(get_current_admin)):
    try:
        res = await db_manager.db.run(lambda: db_manager.db.client.table("saved_attachments").select("*").order("created_at", desc=True).execute())
        return {"saved_attachments": res.data if getattr(res, 'data', None) else []}
    except Exception as e:
        print(f"Error fetching saved attachments: {e}")
        raise HTTPException(status_code=500, detail="Internal Server Error")

@router.get("/contact_messages")
async def get_contact_messages(admin: Dict = Depends(get_current_admin)):
    """Get all public contact form messages."""
    try:
        res = await db_manager.db.run(
            lambda: db_manager.db.client.table("contact_messages")
                    .select("*").order("created_at", desc=True).execute()
        )
        return res.data if getattr(res, 'data', None) else []
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.patch("/contact_messages/{msg_id}")
async def update_contact_message_status(
    msg_id: str,
    admin: Dict = Depends(get_current_admin)
):
    """Mark a contact message as reviewed."""
    try:
        await db_manager.db.run(
            lambda: db_manager.db.client.table("contact_messages").update({
                "status": "reviewed",
                "reviewed_at": datetime.utcnow().isoformat(),
                "reviewed_by": admin.get("email")
            }).eq("id", msg_id).execute()
        )
        return {"message": "Marked as reviewed"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# ✨ 100% CORRECT & COMPATIBLE CHANGE PASSWORD WITH SUPABASE BYPASS
@router.post("/change-password")
async def change_password(request: PasswordChangeRequest, admin: Dict = Depends(get_current_admin)):
    email = admin.get("email")
    if not email:
        raise HTTPException(status_code=401, detail="Invalid admin session")

    # Get admins to check if there's a password set
    admins = await db_manager.get_admin_users() or []
    admin_user = next((entry for entry in admins if entry.get("email", "").strip().lower() == email.strip().lower()), None)
    
    if not admin_user:
        raise HTTPException(status_code=404, detail="Admin not found")

    # Check password only if request contains current_password (manual verification)
    if request.current_password:
        is_valid = await db_manager.verify_admin_password(email, request.current_password)
        if not is_valid:
            raise HTTPException(status_code=400, detail="Current password is incorrect")

    # Update database via existing Supabase manager (completely async and relational-free)
    success = await db_manager.set_admin_password(email, request.new_password)
    if not success:
        raise HTTPException(status_code=500, detail="Failed to update password")
        
    return {"message": "Password updated successfully"}