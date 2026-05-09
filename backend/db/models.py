from supabase import create_client, Client
from config import config
from typing import Optional, Dict, Any
import json

class DBManager:
    def __init__(self):
        self.client: Client = create_client(config.SUPABASE_URL, config.SUPABASE_KEY)

    async def get_user(self, telegram_id: int) -> Optional[Dict[str, Any]]:
        response = self.client.table("users").select("*").eq("telegram_id", telegram_id).execute()
        return response.data[0] if response.data else None

    async def create_user(self, telegram_id: int, username: str, first_name: str, last_name: str = None) -> Dict[str, Any]:
        user_data = {
            "telegram_id": telegram_id,
            "username": username,
            "first_name": first_name,
            "last_name": last_name,
            "role": "user",
            "ai_mode": True,
            "voice_preference": "text"
        }
        response = self.client.table("users").insert(user_data).execute()
        return response.data[0]

    async def update_user(self, telegram_id: int, updates: Dict[str, Any]) -> bool:
        response = self.client.table("users").update(updates).eq("telegram_id", telegram_id).execute()
        return len(response.data) > 0

    async def get_auth_session(self, user_id: str) -> Optional[Dict[str, Any]]:
        response = self.client.table("auth_sessions").select("*").eq("user_id", user_id).execute()
        return response.data[0] if response.data else None

    async def create_auth_session(self, user_id: str, access_token: str, refresh_token: str, expires_at: int) -> Dict[str, Any]:
        session_data = {
            "user_id": user_id,
            "access_token": access_token,
            "refresh_token": refresh_token,
            "expires_at": expires_at
        }
        response = self.client.table("auth_sessions").insert(session_data).execute()
        return response.data[0]

    async def update_auth_session(self, user_id: str, access_token: str, refresh_token: str, expires_at: int) -> bool:
        updates = {
            "access_token": access_token,
            "refresh_token": refresh_token,
            "expires_at": expires_at
        }
        response = self.client.table("auth_sessions").update(updates).eq("user_id", user_id).execute()
        return len(response.data) > 0

    async def delete_auth_session(self, user_id: str) -> bool:
        response = self.client.table("auth_sessions").delete().eq("user_id", user_id).execute()
        return len(response.data) > 0

    async def get_admin_users(self) -> list:
        response = self.client.table("admin_users").select("*").execute()
        return response.data

    async def is_blocked(self, telegram_id: int) -> bool:
        response = self.client.table("blocked_users").select("*").eq("telegram_id", telegram_id).execute()
        return len(response.data) > 0

db_manager = DBManager()