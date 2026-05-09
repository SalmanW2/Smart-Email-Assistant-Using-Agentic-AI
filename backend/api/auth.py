import json
from datetime import datetime, timezone
from typing import Any
import httpx
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from google_auth_oauthlib.flow import Flow
from config import settings
from db.models import db_manager

router = APIRouter()

with open("credentials.json", "r", encoding="utf-8") as credential_file:
    client_config = json.load(credential_file)

SCOPES = [
    "https://www.googleapis.com/auth/gmail.modify",
    "https://www.googleapis.com/auth/userinfo.email",
]

class AuthStartPayload(BaseModel):
    telegram_id: int

@router.post("/login")
async def login(payload: AuthStartPayload):
    if payload.telegram_id <= 0:
        raise HTTPException(status_code=400, detail="telegram_id must be a positive integer")

    user = await db_manager.get_user(payload.telegram_id)
    if not user:
        await db_manager.create_user(payload.telegram_id)

    state_uuid = await db_manager.create_auth_session(payload.telegram_id)
    if not state_uuid:
        raise HTTPException(status_code=500, detail="Unable to create authentication session")

    flow = Flow.from_client_config(
        client_config,
        scopes=SCOPES,
        redirect_uri=str(settings.REDIRECT_URI),
    )
    authorization_url, _ = flow.authorization_url(
        access_type="offline",
        include_granted_scopes="true",
        state=state_uuid,
        prompt="consent",
    )

    return {
        "login_url": authorization_url,
        "state": state_uuid,
    }

@router.get("/callback")
async def callback(code: str, state: str):
    session = await db_manager.get_auth_session(state)
    if not session:
        raise HTTPException(status_code=400, detail="Invalid or expired state")

    flow = Flow.from_client_config(
        client_config,
        scopes=SCOPES,
        redirect_uri=str(settings.REDIRECT_URI),
        state=state,
    )
    flow.fetch_token(code=code)
    creds = flow.credentials

    auth_token = {
        "token": creds.token,
        "refresh_token": creds.refresh_token,
        "expires_at": creds.expiry.isoformat() if creds.expiry else None,
        "token_uri": creds.token_uri,
        "scopes": list(creds.scopes or []),
    }

    email = None
    if auth_token["token"]:
        try:
            async with httpx.AsyncClient(timeout=20) as client:
                response = await client.get(
                    "https://www.googleapis.com/oauth2/v2/userinfo",
                    headers={"Authorization": f"Bearer {auth_token['token']}"},
                )
                response.raise_for_status()
                email = response.json().get("email")
        except Exception:
            email = None

    if session["telegram_id"] is None:
        raise HTTPException(status_code=400, detail="OAuth session missing Telegram identifier")

    existing_user = await db_manager.get_user(session["telegram_id"])
    user_email = email or (existing_user.get("email") if existing_user else None)

    if existing_user:
        await db_manager.upsert_user_token(session["telegram_id"], user_email, auth_token)
    else:
        await db_manager.create_user(session["telegram_id"], email=user_email, auth_token=auth_token)

    await db_manager.delete_auth_session(state)
    return {
        "status": "success",
        "message": "Google authorization completed.",
        "redirect_url": f"{settings.FRONTEND_URL}/dashboard",
        "expires_at": auth_token["expires_at"],
    }
