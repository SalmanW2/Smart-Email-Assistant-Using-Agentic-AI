import asyncio
import json
from typing import Any, Dict, Optional
from supabase import create_client, Client
from config import settings

class SupabaseDB:
    def __init__(self) -> None:
        self.client: Client = create_client(str(settings.supabase_url), settings.supabase_key.get_secret_value())

    async def run(self, action):
        return await asyncio.to_thread(action)

class DBManager:
    def __init__(self) -> None:
        self.db = SupabaseDB()

    async def get_user(self, telegram_id: int) -> Optional[Dict[str, Any]]:
        def action():
            return self.db.client.table("users").select("*").eq("telegram_id", telegram_id).maybe_single().execute()

        response = await self.db.run(action)
        return response.data if response.data else None

    async def create_user(self, telegram_id: int, email: str | None = None, auth_token: dict | None = None) -> Dict[str, Any]:
        user_payload = {
            "telegram_id": telegram_id,
            "email": email,
            "auth_token": auth_token,
            "is_verified": bool(auth_token),
            "ai_mode_enabled": True,
        }

        def action():
            return self.db.client.table("users").insert(user_payload).execute()

        response = await self.db.run(action)
        return response.data[0]

    async def upsert_user_token(self, telegram_id: int, email: str, auth_token: dict) -> Optional[Dict[str, Any]]:
        payload = {
            "telegram_id": telegram_id,
            "email": email,
            "auth_token": auth_token,
            "is_verified": True,
            "ai_mode_enabled": True,
        }

        def action():
            return self.db.client.table("users").upsert(payload, on_conflict="telegram_id").execute()

        response = await self.db.run(action)
        return response.data[0] if response.data else None

    async def update_user(self, telegram_id: int, updates: Dict[str, Any]) -> bool:
        def action():
            return self.db.client.table("users").update(updates).eq("telegram_id", telegram_id).execute()

        response = await self.db.run(action)
        return bool(response.data)

    async def get_auth_session(self, state_uuid: str) -> Optional[Dict[str, Any]]:
        def action():
            return self.db.client.table("auth_sessions").select("*").eq("state_uuid", state_uuid).maybe_single().execute()

        response = await self.db.run(action)
        return response.data if response.data else None

    async def create_auth_session(self, state_uuid: str, telegram_id: int, expires_at: str) -> Dict[str, Any]:
        payload = {
            "state_uuid": state_uuid,
            "telegram_id": telegram_id,
            "expires_at": expires_at,
        }

        def action():
            return self.db.client.table("auth_sessions").insert(payload).execute()

        response = await self.db.run(action)
        return response.data[0]

    async def delete_auth_session(self, state_uuid: str) -> bool:
        def action():
            return self.db.client.table("auth_sessions").delete().eq("state_uuid", state_uuid).execute()

        response = await self.db.run(action)
        return bool(response.data)

    async def get_user_preferences(self, telegram_id: int) -> Optional[Dict[str, Any]]:
        def action():
            return self.db.client.table("user_preferences").select("*").eq("telegram_id", telegram_id).maybe_single().execute()

        response = await self.db.run(action)
        return response.data if response.data else None

    async def update_user_preferences(self, telegram_id: int, updates: Dict[str, Any]) -> bool:
        def action():
            return self.db.client.table("user_preferences").update(updates).eq("telegram_id", telegram_id).execute()

        response = await self.db.run(action)
        return bool(response.data)

    async def get_admin_users(self) -> list[Dict[str, Any]]:
        def action():
            return self.db.client.table("admin_users").select("*").execute()

        response = await self.db.run(action)
        return response.data or []

    async def is_blocked(self, telegram_id: int) -> bool:
        def action():
            return self.db.client.table("blocked_users").select("*").eq("telegram_id", telegram_id).execute()

        response = await self.db.run(action)
        return bool(response.data)

    async def get_user_by_id(self, user_id: str) -> Optional[Dict[str, Any]]:
        def action():
            return self.db.client.table("users").select("*").eq("id", user_id).maybe_single().execute()

        response = await self.db.run(action)
        return response.data if response.data else None

    async def get_admin_emails(self) -> list[str]:
        def action():
            return self.db.client.table("admin_users").select("email").execute()

        response = await self.db.run(action)
        return [row["email"] for row in (response.data or [])]

    async def get_summary_history_count(self, telegram_id: int) -> int:
        def action():
            return self.db.client.table("conversation_summaries").select("id", count="exact").eq("telegram_id", telegram_id).execute()

        response = await self.db.run(action)
        return int(response.count or 0)

    async def get_all_users(self) -> list[Dict[str, Any]]:
        def action():
            return self.db.client.table("users").select("*").execute()

        response = await self.db.run(action)
        return response.data or []

    async def count_table(self, table_name: str, filters: Dict[str, Any] | None = None) -> int:
        def action():
            query = self.db.client.table(table_name).select("id", count="exact")
            if filters:
                for key, value in filters.items():
                    query = query.eq(key, value)
            return query.execute()

        response = await self.db.run(action)
        return int(response.count or 0)

    async def upsert_user_preferences(self, telegram_id: int, updates: Dict[str, Any]) -> bool:
        payload = {
            "telegram_id": telegram_id,
            **updates,
        }

        def action():
            return self.db.client.table("user_preferences").upsert(payload, on_conflict="telegram_id").execute()

        response = await self.db.run(action)
        return bool(response.data)


db_manager = DBManager()