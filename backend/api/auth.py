import json
import os
from typing import Any
import httpx
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import RedirectResponse, HTMLResponse
from google_auth_oauthlib.flow import Flow
from config import settings
from db.models import db_manager

# Fix for "Scope has changed" error
os.environ['OAUTHLIB_RELAX_TOKEN_SCOPE'] = '1'

router = APIRouter()

with open("credentials.json", "r", encoding="utf-8") as credential_file:
    client_config = json.load(credential_file)

SCOPES = [
    "https://www.googleapis.com/auth/gmail.modify",
    "https://www.googleapis.com/auth/userinfo.email",
]

@router.get("/telegram_login")
async def telegram_login(state: str, telegram_id: int):
    """Initiates Google OAuth for Telegram users (Bot)."""
    if telegram_id <= 0:
        raise HTTPException(status_code=400, detail="Invalid telegram_id")

    flow = Flow.from_client_config(
        client_config,
        scopes=SCOPES,
        redirect_uri=str(settings.REDIRECT_URI),
        autogenerate_code_verifier=False  
    )
    authorization_url, _ = flow.authorization_url(
        access_type="offline",
        include_granted_scopes="true",
        state=state,
        prompt="consent",
    )
    return RedirectResponse(url=authorization_url)

@router.get("/admin_google_login")
async def admin_google_login():
    """Initiates Google OAuth for Admin Dashboard."""
    state_uuid = await db_manager.create_auth_session(0) 
    
    flow = Flow.from_client_config(
        client_config,
        scopes=SCOPES,
        redirect_uri=str(settings.REDIRECT_URI),
        autogenerate_code_verifier=False  
    )
    authorization_url, _ = flow.authorization_url(
        access_type="offline",
        include_granted_scopes="true",
        state=f"admin_{state_uuid}",
        prompt="consent",
    )
    return RedirectResponse(url=authorization_url)

@router.get("/callback")
async def callback(code: str, state: str):
    """Handles Google OAuth Callback for both Admin and Telegram Users."""
    is_admin = state.startswith("admin_")
    db_state = state.replace("admin_", "") if is_admin else state

    session = await db_manager.get_auth_session(db_state)
    if not session and not is_admin:
        raise HTTPException(status_code=400, detail="Invalid or expired session state.")

    flow = Flow.from_client_config(
        client_config,
        scopes=SCOPES,
        redirect_uri=str(settings.REDIRECT_URI),
        state=state,
        autogenerate_code_verifier=False  
    )
    flow.fetch_token(code=code)
    creds = flow.credentials

    auth_token = {
        "token": creds.token,
        "refresh_token": creds.refresh_token,
        "expires_at": creds.expiry.isoformat() if creds.expiry else None,
        "token_uri": creds.token_uri,
        "client_id": creds.client_id,
        "client_secret": creds.client_secret,
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

    # Handle Admin Login Routing
    if is_admin:
        if email and await db_manager.check_admin(email):
            await db_manager.delete_auth_session(db_state)
            return RedirectResponse(url=f"{settings.FRONTEND_URL}/admin/dashboard?msg=Google+Login+Successful&email={email}")
        else:
            return RedirectResponse(url=f"{settings.FRONTEND_URL}/admin/login?error=Unauthorized+Admin+Email")
            
    # Handle Telegram Bot User Routing
    else:
        telegram_id = session.get("telegram_id")
        if telegram_id is None:
            raise HTTPException(status_code=400, detail="OAuth session missing Telegram identifier")

        existing_user = await db_manager.get_user(telegram_id)
        user_email = email or (existing_user.get("email") if existing_user else None)

        # FIXED: Preserve old refresh_token if Google skips sending it on re-login
        if existing_user and existing_user.get("auth_token"):
            old_token = existing_user.get("auth_token")
            if not auth_token.get("refresh_token") and old_token.get("refresh_token"):
                auth_token["refresh_token"] = old_token.get("refresh_token")

        if existing_user:
            await db_manager.upsert_user_token(telegram_id, user_email, auth_token)
        else:
            await db_manager.create_user(telegram_id, email=user_email, auth_token=auth_token)

        # FIXED: Delete ALL old useless UUIDs for this user to save Supabase DB space
        try:
            await db_manager.db.run(lambda: db_manager.db.client.table("auth_sessions").delete().eq("telegram_id", telegram_id).execute())
        except: pass

        return HTMLResponse("""
        <html><body style="font-family:sans-serif;text-align:center;padding-top:100px;background-color:#f8f9fa;">
            <div style="background:white;max-width:500px;margin:0 auto;padding:30px;border-radius:15px;box-shadow:0 4px 6px rgba(0,0,0,0.1);">
                <h1 style="color:#10b981;font-size:24px;">Authentication Successful ✅</h1>
                <p style="color:#475569;margin-top:15px;">Your Google Account has been securely connected to the Assistant.</p>
                <p style="color:#475569;margin-top:5px;font-weight:bold;">You may now close this tab and return to Telegram.</p>
            </div>
        </body></html>
        """)