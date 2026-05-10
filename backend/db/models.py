import asyncio
import json
from typing import Any, Dict, Optional, List
from supabase import create_client, Client
from config import settings
import hashlib

class SupabaseDB:
    def __init__(self) -> None:
        self.client: Client = create_client(settings.SUPABASE_URL, settings.SUPABASE_SERVICE_ROLE_KEY)

    async def run(self, action):
        return await asyncio.to_thread(action)

class DBManager:
    def __init__(self) -> None:
        self.db = SupabaseDB()

    # HELPER: Supabase ke NoneType crash ko rokne ke liye
    def _safe_data(self, result):
        return getattr(result, 'data', None) if result else None

    async def get_user(self, telegram_id: int) -> Optional[Dict[str, Any]]:
        try:
            result = await self.db.run(lambda: self.db.client.table("users").select("*").eq("telegram_id", telegram_id).maybe_single().execute())
            return self._safe_data(result)
        except Exception as e:
            print(f"DB Error in get_user: {e}")
            return None

    async def create_user(self, telegram_id: int, email: Optional[str] = None, auth_token: Optional[Dict] = None) -> bool:
        try:
            data = {
                "telegram_id": telegram_id,
                "email": email,
                "auth_token": auth_token,
                "is_verified": False
            }
            await self.db.run(lambda: self.db.client.table("users").insert(data).execute())
            return True
        except Exception as e:
            print(f"DB Error in create_user: {e}")
            return False

    async def upsert_user_token(self, telegram_id: int, email: str, auth_token: Dict) -> bool:
        try:
            await self.db.run(lambda: self.db.client.table("users").update({
                "email": email,
                "auth_token": auth_token
            }).eq("telegram_id", telegram_id).execute())
            return True
        except Exception as e:
            print(f"DB Error in upsert_user_token: {e}")
            return False

    async def get_auth_session(self, state_uuid: str) -> Optional[Dict[str, Any]]:
        try:
            result = await self.db.run(lambda: self.db.client.table("auth_sessions").select("*").eq("state_uuid", state_uuid).maybe_single().execute())
            # Fallback agar "state" column use ho raha ho
            if not result or not hasattr(result, 'data') or not result.data:
                result = await self.db.run(lambda: self.db.client.table("auth_sessions").select("*").eq("state", state_uuid).maybe_single().execute())
            return self._safe_data(result)
        except Exception as e:
            print(f"DB Error in get_auth_session: {e}")
            return None

    async def create_auth_session(self, telegram_id: int) -> str:
        try:
            import uuid
            state_uuid = str(uuid.uuid4())
            await self.db.run(lambda: self.db.client.table("auth_sessions").insert({
                "state_uuid": state_uuid,
                "state": state_uuid,  # Saving in both fields to be safe with older schema
                "telegram_id": telegram_id
            }).execute())
            return state_uuid
        except Exception as e:
            print(f"DB Error in create_auth_session: {e}")
            return ""

    async def save_auth_session(self, state_uuid: str, telegram_id: int, email: str) -> bool:
        try:
            await self.db.run(lambda: self.db.client.table("auth_sessions").insert({
                "state_uuid": state_uuid,
                "state": state_uuid,
                "telegram_id": telegram_id,
                "email": email
            }).execute())
            return True
        except Exception as e:
            print(f"DB Error in save_auth_session: {e}")
            return False

    async def delete_auth_session(self, state_uuid: str) -> bool:
        try:
            await self.db.run(lambda: self.db.client.table("auth_sessions").delete().eq("state_uuid", state_uuid).execute())
            await self.db.run(lambda: self.db.client.table("auth_sessions").delete().eq("state", state_uuid).execute())
            return True
        except Exception as e:
            print(f"DB Error in delete_auth_session: {e}")
            return False

    async def get_user_preferences(self, telegram_id: int) -> Optional[Dict[str, Any]]:
        try:
            result = await self.db.run(lambda: self.db.client.table("user_preferences").select("*").eq("telegram_id", telegram_id).maybe_single().execute())
            return self._safe_data(result)
        except Exception as e:
            print(f"DB Error in get_user_preferences: {e}")
            return None

    async def update_user_preferences(self, telegram_id: int, prefs: Dict[str, Any]) -> bool:
        try:
            await self.db.run(lambda: self.db.client.table("user_preferences").upsert({
                "telegram_id": telegram_id,
                **prefs
            }).execute())
            return True
        except Exception as e:
            print(f"DB Error in update_user_preferences: {e}")
            return False

    async def is_blocked(self, block_type: str, value: str) -> bool:
        try:
            result = await self.db.run(lambda: self.db.client.table("blocked_users").select("*").eq("block_type", block_type).eq("block_value", str(value)).execute())
            data = self._safe_data(result)
            return len(data) > 0 if data else False
        except Exception as e:
            print(f"DB Error in is_blocked: {e}")
            return False

    async def get_all_users(self) -> List[Dict[str, Any]]:
        try:
            result = await self.db.run(lambda: self.db.client.table("users").select("*").order("created_at", desc=True).execute())
            return self._safe_data(result) or []
        except Exception as e:
            print(f"DB Error in get_all_users: {e}")
            return []

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
            return True
        except Exception as e:
            print(f"DB Error in update_user_status: {e}")
            return False

    async def get_admin_users(self) -> List[Dict[str, Any]]:
        try:
            result = await self.db.run(lambda: self.db.client.table("admin_users").select("*").order("created_at", desc=True).execute())
            return self._safe_data(result) or []
        except Exception as e:
            print(f"DB Error in get_admin_users: {e}")
            return []

    async def check_admin(self, email: str) -> bool:
        try:
            result = await self.db.run(lambda: self.db.client.table("admin_users").select("*").eq("email", email).execute())
            data = self._safe_data(result)
            return len(data) > 0 if data else False
        except Exception as e:
            print(f"DB Error in check_admin: {e}")
            return False

    async def get_admin_role(self, email: str) -> str:
        try:
            result = await self.db.run(lambda: self.db.client.table("admin_users").select("role").eq("email", email).execute())
            data = self._safe_data(result)
            if data:
                return data[0].get("role", "admin")
            return "admin"
        except Exception as e:
            print(f"DB Error in get_admin_role: {e}")
            return "admin"

    async def add_admin_user(self, email: str, role: str = "admin", added_by: str = "system") -> bool:
        try:
            await self.db.run(lambda: self.db.client.table("admin_users").insert({
                "email": email,
                "role": role,
                "added_by": added_by
            }).execute())
            return True
        except Exception as e:
            print(f"DB Error in add_admin_user: {e}")
            return False

    async def remove_admin_user(self, email_or_id: str) -> bool:
        try:
            if "@" in email_or_id:
                await self.db.run(lambda: self.db.client.table("admin_users").delete().eq("email", email_or_id).execute())
            else:
                await self.db.run(lambda: self.db.client.table("admin_users").delete().eq("id", email_or_id).execute())
            return True
        except Exception as e:
            print(f"DB Error in remove_admin_user: {e}")
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
            print(f"DB Error in verify_admin_password: {e}")
            return False

    async def set_admin_password(self, email: str, password: str) -> bool:
        try:
            import os
            salt = os.urandom(16)
            pwd_hash = hashlib.pbkdf2_hmac('sha256', password.encode('utf-8'), salt, 100000)
            hashed_password = salt.hex() + ":" + pwd_hash.hex()
            await self.db.run(lambda: self.db.client.table("admin_users").update({"password_hash": hashed_password}).eq("email", email).execute())
            return True
        except Exception as e:
            print(f"DB Error in set_admin_password: {e}")
            return False

    async def block_user(self, telegram_id: int) -> bool:
        try:
            await self.db.run(lambda: self.db.client.table("blocked_users").insert({
                "block_type": "telegram",
                "block_value": str(telegram_id)
            }).execute())
            return True
        except Exception as e:
            print(f"DB Error in block_user: {e}")
            return False

    async def unblock_user(self, telegram_id: int) -> bool:
        try:
            await self.db.run(lambda: self.db.client.table("blocked_users").delete().eq("block_type", "telegram").eq("block_value", str(telegram_id)).execute())
            return True
        except Exception as e:
            print(f"DB Error in unblock_user: {e}")
            return False

    async def get_all_auth_sessions(self) -> List[Dict[str, Any]]:
        try:
            result = await self.db.run(lambda: self.db.client.table("auth_sessions").select("*").execute())
            return self._safe_data(result) or []
        except Exception as e:
            print(f"DB Error in get_all_auth_sessions: {e}")
            return []

    async def get_all_conversation_history(self) -> List[Dict[str, Any]]:
        try:
            result = await self.db.run(lambda: self.db.client.table("conversation_history").select("*").execute())
            return self._safe_data(result) or []
        except Exception as e:
            print(f"DB Error in get_all_conversation_history: {e}")
            return []

    async def get_user_by_email(self, email: str) -> Optional[Dict[str, Any]]:
        try:
            result = await self.db.run(lambda: self.db.client.table("users").select("*").eq("email", email).execute())
            data = self._safe_data(result)
            return data[0] if data else None
        except Exception as e:
            print(f"DB Error in get_user_by_email: {e}")
            return None

db_manager = DBManager()