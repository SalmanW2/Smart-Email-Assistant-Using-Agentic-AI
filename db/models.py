from supabase import create_client, Client
from config import SUPABASE_URL, SUPABASE_KEY, get_utc_now
import logging
import uuid

logger = logging.getLogger(__name__)

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

class DBManager:
    @staticmethod
    def get_user(telegram_id: int):
        response = supabase.table("users").select("*").eq("telegram_id", telegram_id).execute()
        return response.data[0] if response.data else None

    @staticmethod
    def create_or_update_user(telegram_id: int, **kwargs):
        user_data = {
            "telegram_id": telegram_id,
            "updated_at": get_utc_now(),
            **kwargs
        }
        return supabase.table("users").upsert(user_data, on_conflict="telegram_id").execute()

    @staticmethod
    def is_admin(email: str):
        response = supabase.table("admin_users").select("role").eq("email", email).execute()
        return response.data[0] if response.data else None

    @staticmethod
    def get_user_preferences(telegram_id: int):
        response = supabase.table("user_preferences").select("*").eq("telegram_id", telegram_id).execute()
        if not response.data:
            default_prefs = {"telegram_id": telegram_id}
            res = supabase.table("user_preferences").insert(default_prefs).execute()
            return res.data[0]
        return response.data[0]

    @staticmethod
    def update_preferences(telegram_id: int, **kwargs):
        kwargs["updated_at"] = get_utc_now()
        return supabase.table("user_preferences").update(kwargs).eq("telegram_id", telegram_id).execute()

    @staticmethod
    def create_auth_session(telegram_id: int) -> str:
        """Generates a secure, one-time UUID for login."""
        state_uuid = str(uuid.uuid4())
        supabase.table("auth_sessions").insert({
            "state_uuid": state_uuid,
            "telegram_id": telegram_id
        }).execute()
        return state_uuid

    @staticmethod
    def verify_auth_session(state_uuid: str):
        """Checks if the UUID is valid and returns the associated Telegram ID."""
        res = supabase.table("auth_sessions").select("telegram_id").eq("state_uuid", state_uuid).execute()
        return res.data[0]["telegram_id"] if res.data else None

    @staticmethod
    def delete_auth_session(state_uuid: str):
        """Deletes the UUID after successful login."""
        supabase.table("auth_sessions").delete().eq("state_uuid", state_uuid).execute()