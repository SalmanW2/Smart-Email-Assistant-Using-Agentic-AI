import asyncio
import uuid
import os
import hashlib
import logging
from typing import Any, Dict, Optional, List
from supabase import create_client, Client
from cachetools import TTLCache
from config import settings

logger = logging.getLogger(__name__)

class SupabaseDB:
    def __init__(self) -> None:
        self.client: Client = create_client(settings.SUPABASE_URL, settings.SUPABASE_SERVICE_ROLE_KEY)

    async def run(self, action):
        return await asyncio.to_thread(action)

class DBManager:
    def __init__(self) -> None:
        self.db = SupabaseDB()
        # RAM Cache (TTL 120 seconds) to prevent "Errno 11: Resource temporarily unavailable"
        self.cache = TTLCache(maxsize=50, ttl=120)

    def _safe_data(self, result):
        return getattr(result, 'data', None) if result else None

    def _invalidate_cache(self, keys: List[str]):
        """Helper to clear specific caches when data is updated."""
        for key in keys:
            self.cache.pop(key, None)

    # ==========================================
    # USER MANAGEMENT & CACHING
    # ==========================================
    async def get_user(self, telegram_id: int) -> Optional[Dict[str, Any]]:
        try:
            result = await self.db.run(lambda: self.db.client.table("users").select("*").eq("telegram_id", telegram_id).maybe_single().execute())
            return self._safe_data(result)
        except Exception as e:
            logger.error(f"DB Error in get_user: {e}")
            return None

    async def create_user(self, telegram_id: int, email: Optional[str] = None, auth_token: Optional[Dict] = None, first_name: Optional[str] = None, username: Optional[str] = None) -> bool:
        try:
            data = {
                "telegram_id": telegram_id,
                "email": email,
                "auth_token": auth_token,
                "first_name": first_name,
                "username": username,
                "is_verified": False
            }
            # Insert User
            await self.db.run(lambda: self.db.client.table("users").insert(data).execute())
            
            # FIXED: Automatically create default user preferences
            try:
                prefs_data = {
                    "telegram_id": telegram_id,
                    "ai_mode_enabled": True,
                    "voice_preference": "text",
                    "auto_check_enabled": True
                }
                await self.db.run(lambda: self.db.client.table("user_preferences").insert(prefs_data).execute())
            except Exception as pref_e:
                logger.error(f"Could not create default preferences: {pref_e}")

            self._invalidate_cache(["all_users", "active_auto_check_users"])
            return True
        except Exception as e:
            logger.error(f"DB Error in create_user: {e}")
            return False

    async def upsert_user_token(self, telegram_id: int, email: str, auth_token: Dict) -> bool:
        try:
            await self.db.run(lambda: self.db.client.table("users").update({
                "email": email,
                "auth_token": auth_token
            }).eq("telegram_id", telegram_id).execute())
            self._invalidate_cache(["all_users", "active_auto_check_users"])
            return True
        except Exception as e:
            logger.error(f"DB Error in upsert_user_token: {e}")
            return False

    async def get_all_users(self, use_cache: bool = True) -> List[Dict[str, Any]]:
        """Cached: Prevents database overload from frequent admin dashboard / cron checks."""
        if use_cache and "all_users" in self.cache:
            return self.cache["all_users"]
        try:
            result = await self.db.run(lambda: self.db.client.table("users").select("*").order("created_at", desc=True).execute())
            data = self._safe_data(result) or []
            self.cache["all_users"] = data
            return data
        except Exception as e:
            logger.error(f"DB Error in get_all_users: {e}")
            return self.cache.get("all_users", [])

    async def get_user_by_email(self, email: str) -> Optional[Dict[str, Any]]:
        try:
            result = await self.db.run(lambda: self.db.client.table("users").select("*").eq("email", email).execute())
            data = self._safe_data(result)
            return data[0] if data else None
        except Exception as e:
            logger.error(f"DB Error in get_user_by_email: {e}")
            return None

    async def update_user_status(self, telegram_id: int, is_verified: bool, status: str, reason: str = "") -> bool:
        try:
            data = {"is_verified": is_verified}
            if status == "approved":
                data["approved_at"] = settings.get_utc_now()
            elif status == "blocked":
                await self.db.run(lambda: self.db.client.table("blocked_users").insert({
                    "block_type": "telegram",
                    "block_value": str(telegram_id),
                    "reason": reason
                }).execute())
                
            await self.db.run(lambda: self.db.client.table("users").update(data).eq("telegram_id", telegram_id).execute())
            self._invalidate_cache(["all_users", "all_blocked_users", "active_auto_check_users"])
            return True
        except Exception as e:
            logger.error(f"DB Error in update_user_status: {e}")
            return False

    async def get_active_auto_check_users(self) -> List[Dict[str, Any]]:
        """Smart cached fetching for Cron Job to significantly reduce database load."""
        if "active_auto_check_users" in self.cache:
            return self.cache["active_auto_check_users"]
        try:
            users_res = await self.db.run(lambda: self.db.client.table("users").select("*").eq("is_verified", True).execute())
            verified_users = self._safe_data(users_res) or []
            
            prefs_res = await self.db.run(lambda: self.db.client.table("user_preferences").select("telegram_id, auto_check_enabled").execute())
            prefs = {p["telegram_id"]: p.get("auto_check_enabled", True) for p in (self._safe_data(prefs_res) or [])}
            
            active_users = []
            for u in verified_users:
                if prefs.get(u["telegram_id"], True) and u.get("auth_token"):
                    active_users.append(u)
                    
            self.cache["active_auto_check_users"] = active_users
            return active_users
        except Exception as e:
            logger.error(f"DB Error in get_active_auto_check_users: {e}")
            return self.cache.get("active_auto_check_users", [])

    # ==========================================
    # AUTHENTICATION SESSIONS
    # ==========================================
    async def get_auth_session(self, state_uuid: str) -> Optional[Dict[str, Any]]:
        try:
            result = await self.db.run(lambda: self.db.client.table("auth_sessions").select("*").eq("state_uuid", state_uuid).maybe_single().execute())
            return self._safe_data(result)
        except Exception as e:
            logger.error(f"DB Error in get_auth_session: {e}")
            return None

    async def create_auth_session(self, telegram_id: int) -> str:
        try:
            state_uuid = str(uuid.uuid4())
            await self.db.run(lambda: self.db.client.table("auth_sessions").insert({
                "state_uuid": state_uuid,
                "telegram_id": telegram_id
            }).execute())
            return state_uuid
        except Exception as e:
            logger.error(f"DB Error in create_auth_session: {e}")
            return ""

    async def save_auth_session(self, state_uuid: str, telegram_id: int, email: str) -> bool:
        try:
            await self.db.run(lambda: self.db.client.table("auth_sessions").insert({
                "state_uuid": state_uuid,
                "telegram_id": telegram_id,
                "email": email
            }).execute())
            return True
        except Exception as e:
            logger.error(f"DB Error in save_auth_session: {e}")
            return False

    async def delete_auth_session(self, state_uuid: str) -> bool:
        try:
            await self.db.run(lambda: self.db.client.table("auth_sessions").delete().eq("state_uuid", state_uuid).execute())
            return True
        except Exception as e:
            logger.error(f"DB Error in delete_auth_session: {e}")
            return False

    async def get_all_auth_sessions(self) -> List[Dict[str, Any]]:
        try:
            result = await self.db.run(lambda: self.db.client.table("auth_sessions").select("*").execute())
            return self._safe_data(result) or []
        except Exception as e:
            logger.error(f"DB Error in get_all_auth_sessions: {e}")
            return []

    # ==========================================
    # USER PREFERENCES
    # ==========================================
    async def get_user_preferences(self, telegram_id: int) -> Optional[Dict[str, Any]]:
        try:
            result = await self.db.run(lambda: self.db.client.table("user_preferences").select("*").eq("telegram_id", telegram_id).maybe_single().execute())
            return self._safe_data(result)
        except Exception as e:
            logger.error(f"DB Error in get_user_preferences: {e}")
            return None

    async def update_user_preferences(self, telegram_id: int, prefs: Dict[str, Any]) -> bool:
        try:
            await self.db.run(lambda: self.db.client.table("user_preferences").upsert({
                "telegram_id": telegram_id,
                **prefs
            }, on_conflict="telegram_id").execute())
            self._invalidate_cache(["active_auto_check_users"])
            return True
        except Exception as e:
            logger.error(f"DB Error in update_user_preferences: {e}")
            return False

    # ==========================================
    # ADMIN MANAGEMENT & SECURITY
    # ==========================================
    async def get_admin_users(self, use_cache: bool = True) -> List[Dict[str, Any]]:
        if use_cache and "all_admins" in self.cache:
            return self.cache["all_admins"]
        try:
            result = await self.db.run(lambda: self.db.client.table("admin_users").select("*").order("created_at", desc=True).execute())
            data = self._safe_data(result) or []
            self.cache["all_admins"] = data
            return data
        except Exception as e:
            logger.error(f"DB Error in get_admin_users: {e}")
            return self.cache.get("all_admins", [])

    async def check_admin(self, email: str) -> bool:
        try:
            result = await self.db.run(lambda: self.db.client.table("admin_users").select("*").eq("email", email).execute())
            data = self._safe_data(result)
            return len(data) > 0 if data else False
        except Exception as e:
            logger.error(f"DB Error in check_admin: {e}")
            return False

    async def get_admin_role(self, email: str) -> str:
        try:
            result = await self.db.run(lambda: self.db.client.table("admin_users").select("role").eq("email", email).execute())
            data = self._safe_data(result)
            if data:
                return data[0].get("role", "admin")
            return "admin"
        except Exception as e:
            logger.error(f"DB Error in get_admin_role: {e}")
            return "admin"

    async def add_admin_user(self, email: str, role: str = "admin", added_by: str = "system") -> bool:
        try:
            await self.db.run(lambda: self.db.client.table("admin_users").insert({
                "email": email,
                "role": role,
                "added_by": added_by
            }).execute())
            self._invalidate_cache(["all_admins"])
            return True
        except Exception as e:
            logger.error(f"DB Error in add_admin_user: {e}")
            return False

    async def remove_admin_user(self, email_or_id: str) -> bool:
        try:
            if "@" in email_or_id:
                await self.db.run(lambda: self.db.client.table("admin_users").delete().eq("email", email_or_id).execute())
            else:
                await self.db.run(lambda: self.db.client.table("admin_users").delete().eq("id", email_or_id).execute())
            self._invalidate_cache(["all_admins"])
            return True
        except Exception as e:
            logger.error(f"DB Error in remove_admin_user: {e}")
            return False

    async def verify_admin_password(self, email: str, password: str) -> bool:
        try:
            result = await self.db.run(lambda: self.db.client.table("admin_users").select("password_hash").eq("email", email).execute())
            data = self._safe_data(result)
            if not data:
                return False
            stored_hash = data[0].get("password_hash")
            if not stored_hash or ":" not in stored_hash:
                return False
            
            salt_hex, hash_hex = stored_hash.split(':')
            salt = bytes.fromhex(salt_hex)
            pwd_hash = hashlib.pbkdf2_hmac('sha256', password.encode('utf-8'), salt, 100000)
            return pwd_hash.hex() == hash_hex
        except Exception as e:
            logger.error(f"DB Error in verify_admin_password: {e}")
            return False

    async def set_admin_password(self, email: str, password: str) -> bool:
        try:
            salt = os.urandom(16)
            pwd_hash = hashlib.pbkdf2_hmac('sha256', password.encode('utf-8'), salt, 100000)
            hashed_password = salt.hex() + ":" + pwd_hash.hex()
            await self.db.run(lambda: self.db.client.table("admin_users").update({"password_hash": hashed_password}).eq("email", email).execute())
            return True
        except Exception as e:
            logger.error(f"DB Error in set_admin_password: {e}")
            return False

    # ==========================================
    # BLOCK & UNBLOCK
    # ==========================================
    async def is_blocked(self, block_type: str, value: str) -> bool:
        try:
            result = await self.db.run(lambda: self.db.client.table("blocked_users").select("*").eq("block_type", block_type).eq("block_value", str(value)).execute())
            data = self._safe_data(result)
            return len(data) > 0 if data else False
        except Exception as e:
            logger.error(f"DB Error in is_blocked: {e}")
            return False

    async def block_user(self, telegram_id: int) -> bool:
        try:
            await self.db.run(lambda: self.db.client.table("blocked_users").insert({
                "block_type": "telegram",
                "block_value": str(telegram_id)
            }).execute())
            self._invalidate_cache(["all_blocked_users", "active_auto_check_users"])
            return True
        except Exception as e:
            logger.error(f"DB Error in block_user: {e}")
            return False

    async def unblock_user(self, telegram_id: int) -> bool:
        try:
            await self.db.run(lambda: self.db.client.table("blocked_users").delete().eq("block_type", "telegram").eq("block_value", str(telegram_id)).execute())
            self._invalidate_cache(["all_blocked_users", "active_auto_check_users"])
            return True
        except Exception as e:
            logger.error(f"DB Error in unblock_user: {e}")
            return False

    async def get_all_blocked_users(self, use_cache: bool = True) -> List[Dict[str, Any]]:
        if use_cache and "all_blocked_users" in self.cache:
            return self.cache["all_blocked_users"]
        try:
            result = await self.db.run(lambda: self.db.client.table("blocked_users").select("*").execute())
            data = self._safe_data(result) or []
            self.cache["all_blocked_users"] = data
            return data
        except Exception as e:
            logger.error(f"DB Error in get_all_blocked_users: {e}")
            return self.cache.get("all_blocked_users", [])

    # ==========================================
    # LOGGING & HISTORY (TTS)
    # ==========================================
    async def get_all_conversation_history(self) -> List[Dict[str, Any]]:
        try:
            result = await self.db.run(lambda: self.db.client.table("conversation_history").select("*").execute())
            return self._safe_data(result) or []
        except Exception as e:
            logger.error(f"DB Error in get_all_conversation_history: {e}")
            return []

    async def log_tts_usage(self, telegram_id: int, method: str, characters_generated: int) -> bool:
        """NEW: Helper to populate the tts_usage table correctly."""
        try:
            await self.db.run(lambda: self.db.client.table("tts_usage").insert({
                "telegram_id": telegram_id,
                "method": method,
                "characters_generated": characters_generated
            }).execute())
            return True
        except Exception as e:
            logger.error(f"DB Error in log_tts_usage: {e}")
            return False

db_manager = DBManager()