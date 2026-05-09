from datetime import datetime
from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import RedirectResponse
from google_auth_oauthlib.flow import Flow
from db.models import db_manager
from config import settings
import json

router = APIRouter()

with open("credentials.json", "r", encoding="utf-8") as f:
    client_config = json.load(f)

SCOPES = [
    "https://www.googleapis.com/auth/gmail.modify",
    "https://www.googleapis.com/auth/userinfo.email",
]

@router.get("/login")
async def login(token: str = Query(...)):
    session = await db_manager.get_auth_session(token)
    if not session:
        raise HTTPException(status_code=404, detail="Invalid login token")

    expires_at = session.get("expires_at")
    if expires_at and datetime.fromisoformat(expires_at) < datetime.utcnow():
        raise HTTPException(status_code=410, detail="Login token expired")

    flow = Flow.from_client_config(
        client_config,
        scopes=SCOPES,
        redirect_uri=str(settings.REDIRECT_URI),
    )
    authorization_url, _ = flow.authorization_url(
        access_type="offline",
        include_granted_scopes="true",
        state=token,
        prompt="consent",
    )
    return RedirectResponse(authorization_url)

@router.get("/callback")
async def callback(code: str, state: str):
    session = await db_manager.get_auth_session(state)
    if not session:
        raise HTTPException(status_code=400, detail="Invalid authorization state")

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

    user = await db_manager.get_user(session["telegram_id"])
    if user:
        await db_manager.upsert_user_token(session["telegram_id"], user.get("email", ""), auth_token)
    else:
        await db_manager.create_user(session["telegram_id"], email=None, auth_token=auth_token)

    await db_manager.delete_auth_session(state)
    return RedirectResponse(str(settings.FRONTEND_URL) + "/dashboard")
