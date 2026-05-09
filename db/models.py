"""
Database Models and Helper Functions
Handles all Supabase interactions
"""

import logging
import uuid
import hashlib
import os
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any
from supabase import create_client, Client
from config import SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY, SUPABASE_KEY, get_utc_now, get_utc_date
_service_key = SUPABASE_SERVICE_ROLE_KEY or SUPABASE_KEY

# Initialize Supabase Client
supabase: Client = create_client(SUPABASE_URL, _service_key)
logger = logging.getLogger(__name__)

# ===== PASSWORD HASHING =====
def hash_password(password: str) -> str:
    """Hashes a password securely using SHA-256 and a random salt."""
    salt = os.urandom(16)
    pwd_hash = hashlib.pbkdf2_hmac('sha256', password.encode('utf-8'), salt, 100000)
    return salt.hex() + ":" + pwd_hash.hex()

def verify_hash(password: str, stored_hash: str) -> bool:
    """Verifies a password against a stored salted hash."""
    try:
        salt_hex, hash_hex = stored_hash.split(':')
        salt = bytes.fromhex(salt_hex)
        pwd_hash = hashlib.pbkdf2_hmac('sha256', password.encode('utf-8'), salt, 100000)
        return pwd_hash.hex() == hash_hex
    except Exception as e:
        logger.error(f"Hash verification failed: {e}")
        return False

# ===== USER MANAGEMENT =====
class UserModel:
    @staticmethod
    def handle_user_start(telegram_id: int, username: str, first_name: str) -> str:
        """Handles new user registration and returns their status."""
        # Check if blocked
        if UserModel.is_blocked("telegram", str(telegram_id)):
            return "blocked"
        
        try:
            # Check if user exists
            existing = supabase.table("users").select("*").eq("telegram_id", telegram_id).execute()
            
            if not existing.data:
                # Create new user
                supabase.table("users").insert({
                    "telegram_id": telegram_id,
                    "username": username,
                    "first_name": first_name,
                    "is_verified": False,
                    "ai_mode_enabled": True,
                    "created_at": get_utc_now()
                }).execute()
                
                # Create default preferences
                supabase.table("user_preferences").insert({
                    "telegram_id": telegram_id,
                    "ai_mode_enabled": True,
                    "auto_suggest_contacts": True,
                    "undo_window_seconds": 4,
                    "max_attachment_size_mb": 20
                }).execute()
                
                return "pending"
            
            is_verified = existing.data[0].get("is_verified", False)
            return "approved" if is_verified else "pending"
        except Exception as e:
            logger.error(f"User registration error: {e}")
            return "error"

    @staticmethod
    def is_blocked(block_type: str, value: str) -> bool:
        """Checks if a Telegram ID or Email is blocked."""
        try:
            res = supabase.table("blocked_users").select("*").eq("block_type", block_type).eq("block_value", str(value)).execute()
            return len(res.data) > 0
        except Exception as e:
            logger.error(f"Block check error: {e}")
            return False

    @staticmethod
    def update_user(telegram_id: int, data: Dict[str, Any]) -> bool:
        """Updates user information."""
        try:
            data["updated_at"] = get_utc_now()
            supabase.table("users").update(data).eq("telegram_id", telegram_id).execute()
            return True
        except Exception as e:
            logger.error(f"User update error: {e}")
            return False

    @staticmethod
    def get_user(telegram_id: int) -> Optional[Dict]:
        """Fetches user information."""
        try:
            res = supabase.table("users").select("*").eq("telegram_id", telegram_id).execute()
            return res.data[0] if res.data else None
        except Exception as e:
            logger.error(f"User fetch error: {e}")
            return None

    @staticmethod
    def update_last_activity(telegram_id: int) -> bool:
        """Updates user's last activity timestamp."""
        return UserModel.update_user(telegram_id, {"last_activity_at": get_utc_now()})

    @staticmethod
    def toggle_ai_mode(telegram_id: int, enabled: bool) -> bool:
        """Toggles AI mode for a user."""
        return UserModel.update_user(telegram_id, {"ai_mode_enabled": enabled})

    @staticmethod
    def set_voice_preference(telegram_id: int, preference: str) -> bool:
        """Sets user's voice preference (text, voice, both)."""
        return UserModel.update_user(telegram_id, {"voice_preference": preference})

# ===== AUTH SESSIONS =====
class AuthSessionModel:
    @staticmethod
    def create_session(telegram_id: int) -> str:
        """Creates an OAuth session and returns state UUID."""
        state_uuid = str(uuid.uuid4())
        try:
            supabase.table("auth_sessions").insert({
                "state_uuid": state_uuid,
                "telegram_id": telegram_id,
                "created_at": get_utc_now()
            }).execute()
            return state_uuid
        except Exception as e:
            logger.error(f"Session creation error: {e}")
            return ""

    @staticmethod
    def verify_session(state_uuid: str) -> Optional[int]:
        """Verifies session and returns telegram_id."""
        try:
            res = supabase.table("auth_sessions").select("telegram_id").eq("state_uuid", state_uuid).execute()
            if res.data:
                telegram_id = res.data[0]["telegram_id"]
                # Delete the session after verification
                supabase.table("auth_sessions").delete().eq("state_uuid", state_uuid).execute()
                return telegram_id
            return None
        except Exception as e:
            logger.error(f"Session verification error: {e}")
            return None

# ===== LOGIN & TOKEN =====
class LoginModel:
    @staticmethod
    def save_login_data(telegram_id: int, email: str, token_json: Dict) -> bool:
        """Saves OAuth token and email to user."""
        try:
            supabase.table("users").update({
                "email": email,
                "auth_token": token_json,
                "is_verified": True,
                "approved_at": get_utc_now(),
                "last_activity_at": get_utc_now()
            }).eq("telegram_id", telegram_id).execute()
            return True
        except Exception as e:
            logger.error(f"Login save error: {e}")
            return False

    @staticmethod
    def logout_user(telegram_id: int) -> bool:
        """Removes user token and logs action."""
        try:
            user = UserModel.get_user(telegram_id)
            if user and user.get("email"):
                supabase.table("users").update({
                    "auth_token": None,
                    "is_verified": False
                }).eq("telegram_id", telegram_id).execute()
                return True
            return False
        except Exception as e:
            logger.error(f"Logout error: {e}")
            return False

# ===== ADMIN MANAGEMENT =====
class AdminModel:
    @staticmethod
    def check_admin(email: str) -> bool:
        """Checks if email is an admin."""
        try:
            res = supabase.table("admin_users").select("*").eq("email", email).execute()
            return len(res.data) > 0
        except Exception as e:
            logger.error(f"Admin check error: {e}")
            return False

    @staticmethod
    def get_admin_role(email: str) -> str:
        """Gets admin role."""
        try:
            res = supabase.table("admin_users").select("role").eq("email", email).execute()
            if res.data:
                return res.data[0].get("role", "admin")
            return "admin"
        except Exception as e:
            logger.error(f"Role fetch error: {e}")
            return "admin"

    @staticmethod
    def set_admin_password(email: str, password: str) -> bool:
        """Sets admin password."""
        try:
            hashed = hash_password(password)
            supabase.table("admin_users").update({
                "password_hash": hashed
            }).eq("email", email).execute()
            return True
        except Exception as e:
            logger.error(f"Password set error: {e}")
            return False

    @staticmethod
    def verify_admin_password(email: str, password: str) -> bool:
        """Verifies admin password."""
        try:
            res = supabase.table("admin_users").select("password_hash").eq("email", email).execute()
            if res.data and res.data[0].get("password_hash"):
                return verify_hash(password, res.data[0]["password_hash"])
            return False
        except Exception as e:
            logger.error(f"Password verify error: {e}")
            return False

    @staticmethod
    def add_admin(email: str, role: str, added_by: str) -> bool:
        """Adds new admin."""
        try:
            supabase.table("admin_users").insert({
                "email": email,
                "role": role,
                "added_by": added_by,
                "created_at": get_utc_now()
            }).execute()
            return True
        except Exception as e:
            logger.error(f"Admin add error: {e}")
            return False

    @staticmethod
    def get_all_admins() -> List[Dict]:
        """Gets all admins."""
        try:
            res = supabase.table("admin_users").select("*").order("created_at", desc=True).execute()
            return res.data
        except Exception as e:
            logger.error(f"Admins fetch error: {e}")
            return []

    @staticmethod
    def remove_admin(admin_id: str) -> bool:
        """Removes admin."""
        try:
            supabase.table("admin_users").delete().eq("id", admin_id).execute()
            return True
        except Exception as e:
            logger.error(f"Admin remove error: {e}")
            return False

# ===== BLOCKLIST MANAGEMENT =====
class BlocklistModel:
    @staticmethod
    def block_user(block_type: str, block_value: str, reason: str, blocked_by: str = "system") -> bool:
        """Adds user to blocklist."""
        try:
            supabase.table("blocked_users").insert({
                "block_type": block_type,
                "block_value": str(block_value),
                "reason": reason,
                "blocked_by": blocked_by,
                "blocked_at": get_utc_now()
            }).execute()
            return True
        except Exception as e:
            logger.error(f"Block error: {e}")
            return False

    @staticmethod
    def unblock_user(block_type: str, block_value: str) -> bool:
        """Removes user from blocklist."""
        try:
            supabase.table("blocked_users").delete().eq("block_type", block_type).eq("block_value", str(block_value)).execute()
            return True
        except Exception as e:
            logger.error(f"Unblock error: {e}")
            return False

    @staticmethod
    def get_all_blocked() -> List[Dict]:
        """Gets all blocked records."""
        try:
            res = supabase.table("blocked_users").select("*").order("blocked_at", desc=True).execute()
            return res.data
        except Exception as e:
            logger.error(f"Blocked fetch error: {e}")
            return []

    @staticmethod
    def remove_blocked_record(record_id: str) -> bool:
        """Removes a specific blocked record."""
        try:
            supabase.table("blocked_users").delete().eq("id", record_id).execute()
            return True
        except Exception as e:
            logger.error(f"Record delete error: {e}")
            return False

# ===== USER MANAGEMENT FOR ADMIN =====
class UserAdminModel:
    @staticmethod
    def get_all_users() -> List[Dict]:
        """Gets all users for admin dashboard."""
        try:
            res = supabase.table("users").select("*").order("created_at", desc=True).execute()
            return res.data
        except Exception as e:
            logger.error(f"Users fetch error: {e}")
            return []

    @staticmethod
    def update_user_status(telegram_id: int, is_verified: bool, status: str, reason: str = "") -> bool:
        """Updates user verification status (admin action)."""
        try:
            data = {"is_verified": is_verified}
            
            if status == "approved":
                data["approved_at"] = get_utc_now()
                BlocklistModel.unblock_user("telegram", str(telegram_id))
            
            if status == "pending":
                data["approved_at"] = None
                BlocklistModel.unblock_user("telegram", str(telegram_id))
            
            supabase.table("users").update(data).eq("telegram_id", telegram_id).execute()
            
            if status == "blocked":
                BlocklistModel.block_user("telegram", str(telegram_id), reason, "admin")
            
            return True
        except Exception as e:
            logger.error(f"Status update error: {e}")
            return False