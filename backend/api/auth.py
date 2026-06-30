"""
Modular OAuth Router — Smart Email Assistant
===========================================
Manages the Google OAuth 2.0 flow for both Admin Dashboard users and Telegram bot users.

Features:
1. Supports separate user flows and admin dashboard JWT token exchange flows.
2. Google Email Validation: Dynamically resolves active Google Profile emails via the OAuth Userinfo API.
3. Refresh Token Preservation: Retains existing refresh tokens in the database on user re-authentication.
4. UI/UX Synchronicity: Clears stale Telegram login prompts and displays premium success alerts.
"""

import json
import os
import jwt
import httpx
import asyncio
import logging
from typing import Optional
from datetime import datetime, timezone, timedelta
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import RedirectResponse, HTMLResponse
from google_auth_oauthlib.flow import Flow

from config import settings
from db.models import db_manager

os.environ['OAUTHLIB_RELAX_TOKEN_SCOPE'] = '1'
router = APIRouter()
logger = logging.getLogger(__name__)

# Security & Session encryption key parameters
SECRET_KEY = getattr(settings, "JWT_SECRET", settings.BOT_TOKEN)
ALGORITHM  = "HS256"

SCOPES = [
    "https://www.googleapis.com/auth/gmail.modify",
    "https://www.googleapis.com/auth/userinfo.email",
]


def _get_client_config() -> dict:
    """
    Loads Google OAuth client configuration.
    Priority: GOOGLE_CREDENTIALS_JSON env var -> local credentials.json file.
    """
    if settings.GOOGLE_CREDENTIALS_JSON:
        import base64
        return json.loads(base64.b64decode(settings.GOOGLE_CREDENTIALS_JSON).decode('utf-8'))
    
    cred_path = os.path.join(os.path.dirname(__file__), "..", "credentials.json")
    cred_path = os.path.normpath(cred_path)
    if os.path.exists(cred_path):
        with open(cred_path, "r", encoding="utf-8") as f:
            return json.load(f)
    raise RuntimeError(
        "Google OAuth credentials not found. Please verify GOOGLE_CREDENTIALS_JSON environment variable."
    )


def _make_flow(state: Optional[str] = None) -> Flow:
    """Creates a configured OAuth flow instance."""
    flow = Flow.from_client_config(
        _get_client_config(),
        scopes=SCOPES,
        redirect_uri=str(settings.REDIRECT_URI),
        autogenerate_code_verifier=False,
    )
    return flow


async def _send_welcome_to_telegram(telegram_id: int):
    """Fallback welcome message direct delivery via raw HTTP requests."""
    url = f"https://api.telegram.org/bot{settings.BOT_TOKEN}/sendMessage"
    kb  = {"inline_keyboard": [[{"text": "🎛️ Go to Main Dashboard", "callback_data": "menu_main"}]]}
    payload = {
        "chat_id": telegram_id,
        "text": "✅ *Google Workspace Connected!*\n\nYour account is now securely linked. Return to the Main Dashboard to continue.",
        "parse_mode": "Markdown",
        "reply_markup": kb,
    }
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            await client.post(url, json=payload)
    except Exception as e:
        logger.error(f"Fallback welcome notifier delivery failed: {e}")


@router.get("/telegram_login")
async def telegram_login(state: str, telegram_id: int):
    """Initiates login flow by redirecting Telegram users to Google."""
    if telegram_id <= 0:
        raise HTTPException(status_code=400, detail="Invalid Telegram Identifier context.")
    
    flow = _make_flow()
    auth_url, _ = flow.authorization_url(
        access_type="offline",
        include_granted_scopes="true",
        state=state,
        prompt="consent",
    )
    return RedirectResponse(url=auth_url)


@router.get("/admin_google_login")
async def admin_google_login():
    """Initiates secure authorization session generation for Administrator Panel logins."""
    state_uuid = await db_manager.create_auth_session(0)
    flow = _make_flow()
    auth_url, _ = flow.authorization_url(
        access_type="offline",
        include_granted_scopes="true",
        state=f"admin_{state_uuid}",
        prompt="consent",
    )
    return RedirectResponse(url=auth_url)


@router.get("/callback")
async def callback(code: str, state: str):
    """
    Handles callbacks from Google's authorization servers.
    Validates token responses, performs email lookup, and routes context appropriately.
    """
    is_admin = state.startswith("admin_")
    db_state = state.replace("admin_", "") if is_admin else state

    # Session validation state check
    session = await db_manager.get_auth_session(db_state)
    if not session and not is_admin:
        raise HTTPException(status_code=400, detail="Invalid or expired session state.")

    try:
        # Perform Token exchange
        flow = _make_flow(state=state)
        await asyncio.to_thread(flow.fetch_token, code=code)
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

        # Resolve Google account email context
        email = None
        if auth_token["token"]:
            try:
                async with httpx.AsyncClient(timeout=20) as client:
                    resp = await client.get(
                        "https://www.googleapis.com/oauth2/v2/userinfo",
                        headers={"Authorization": f"Bearer {auth_token['token']}"},
                    )
                    resp.raise_for_status()
                    email = resp.json().get("email")
            except Exception as e:
                logger.error(f"Failed to fetch userinfo profile: {e}")
                email = None

        # ==========================================
        # 1. ADMIN FLOW PIPELINE
        # ==========================================
        if is_admin:
            if email and await db_manager.check_admin(email):
                role = await db_manager.get_admin_role(email)
                expire = datetime.utcnow() + timedelta(hours=24)
                
                # Generate Admin JWT Token
                token = jwt.encode(
                    {"sub": email, "role": role, "exp": expire},
                    SECRET_KEY,
                    algorithm=ALGORITHM
                )
                await db_manager.delete_auth_session(db_state)
                return RedirectResponse(
                    url=f"{settings.FRONTEND_URL}/admin/dashboard?token={token}&email={email}"
                )
            return RedirectResponse(
                url=f"{settings.FRONTEND_URL}/admin/login?error=Unauthorized+Admin+Email"
            )

        # ==========================================
        # 2. BOT USER FLOW PIPELINE
        # ==========================================
        telegram_id = session.get("telegram_id")
        if telegram_id is None:
            raise HTTPException(status_code=400, detail="OAuth session lacks valid Telegram identifier.")

        existing = await db_manager.get_user(telegram_id)
        user_email = email or (existing.get("email") if existing else None)

        # Securely preserve offline refresh_token if none is provided in current re-authorization
        if existing and existing.get("auth_token"):
            old = existing["auth_token"]
            if not auth_token.get("refresh_token") and old.get("refresh_token"):
                auth_token["refresh_token"] = old["refresh_token"]

        # Persist user mapping configuration to Supabase
        if existing:
            await db_manager.upsert_user_token(telegram_id, user_email, auth_token)
        else:
            await db_manager.create_user(telegram_id, email=user_email, auth_token=auth_token)

        # Remove used session entries
        try:
            await db_manager.db.run(
                lambda: db_manager.db.client.table("auth_sessions")
                .delete().eq("telegram_id", telegram_id).execute()
            )
        except Exception as session_err:
            logger.warning(f"Session cleanup failed: {session_err}")

        # Trigger reactive dashboard notifications on Telegram
        try:
            from bot.telegram_handler import telegram_handler
            asyncio.create_task(telegram_handler.notify_login_success(telegram_id))
        except Exception as bot_err:
            logger.warning(f"Direct callback handover failed ({bot_err}), reverting to fallback welcome note.")
            asyncio.create_task(_send_welcome_to_telegram(telegram_id))

        # Serve premium dark-themed success confirmation UI
        return HTMLResponse("""
        <!DOCTYPE html>
        <html lang="en" class="h-full bg-slate-900">
        <head>
            <meta charset="UTF-8">
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
            <title>Connection Successful — Smart Email Assistant</title>
            <script src="https://cdn.tailwindcss.com"></script>
        </head>
        <body class="h-full flex items-center justify-center p-4">
            <div class="max-w-md w-full bg-slate-800 rounded-3xl shadow-2xl p-8 text-center border border-slate-700/50">
                <div class="w-20 h-20 bg-emerald-500/10 rounded-full flex items-center justify-center mx-auto mb-6 border border-emerald-500/20">
                    <svg class="w-10 h-10 text-emerald-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2.5" d="M5 13l4 4L19 7"/>
                    </svg>
                </div>
                <h1 class="text-2xl font-bold text-white mb-2 tracking-tight">Access Link Established</h1>
                <p class="text-slate-400 mb-6 text-sm leading-relaxed">
                    Your Google Account has been securely verified and linked to your Agentic Assistant profile.
                </p>
                <div class="bg-indigo-500/10 border border-indigo-500/20 rounded-2xl p-4 mb-6">
                    <p class="text-sm text-indigo-300 font-medium">
                        🎉 Return to Telegram! Your Main Dashboard is ready.
                    </p>
                </div>
                <button
                    onclick="window.close()"
                    class="w-full bg-indigo-600 hover:bg-indigo-700 text-white font-semibold py-3.5 px-4 rounded-xl transition duration-200 shadow-lg text-sm"
                >
                    Close This Window
                </button>
            </div>
        </body>
        </html>
        """)

    except Exception as e:
        logger.error(f"Callback resolution error: {e}")
        raise HTTPException(status_code=500, detail=f"Authentication pipeline failure: {str(e)}")