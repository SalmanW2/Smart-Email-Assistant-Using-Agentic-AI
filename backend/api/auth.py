import json
import os
import jwt
import httpx
import asyncio
from datetime import datetime, timedelta
from fastapi import APIRouter, HTTPException
from fastapi.responses import RedirectResponse, HTMLResponse
from google_auth_oauthlib.flow import Flow
from config import settings
from db.models import db_manager

os.environ['OAUTHLIB_RELAX_TOKEN_SCOPE'] = '1'
router = APIRouter()

SECRET_KEY = getattr(settings, "JWT_SECRET", settings.BOT_TOKEN)
ALGORITHM  = "HS256"

SCOPES = [
    "https://www.googleapis.com/auth/gmail.modify",
    "https://www.googleapis.com/auth/userinfo.email",
]

def _get_client_config() -> dict:
    """
    Load Google OAuth credentials at call-time (not import-time).
    Priority: GOOGLE_CREDENTIALS_JSON env var → credentials.json file.
    On Render, set GOOGLE_CREDENTIALS_JSON to the full JSON string.
    """
    raw = os.environ.get("GOOGLE_CREDENTIALS_JSON", "").strip()
    if raw:
        return json.loads(raw)
    cred_path = os.path.join(os.path.dirname(__file__), "..", "credentials.json")
    cred_path = os.path.normpath(cred_path)
    if os.path.exists(cred_path):
        with open(cred_path, "r", encoding="utf-8") as f:
            return json.load(f)
    raise RuntimeError(
        "Google OAuth credentials not found. "
        "Set GOOGLE_CREDENTIALS_JSON environment variable on Render."
    )


def _make_flow(state: str | None = None) -> Flow:
    flow = Flow.from_client_config(
        _get_client_config(),
        scopes=SCOPES,
        redirect_uri=str(settings.REDIRECT_URI),
        autogenerate_code_verifier=False,
    )
    return flow


async def _send_welcome_to_telegram(telegram_id: int):
    url = f"https://api.telegram.org/bot{settings.BOT_TOKEN}/sendMessage"
    kb  = {"inline_keyboard": [[{"text": "🎛️ Go to Main Dashboard", "callback_data": "menu_main"}]]}
    payload = {
        "chat_id":    telegram_id,
        "text":       "✅ *Successfully Logged In!*\n\nYour Google Workspace is securely connected. Welcome to your AI Assistant!",
        "parse_mode": "Markdown",
        "reply_markup": kb,
    }
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            await client.post(url, json=payload)
    except Exception:
        pass


@router.get("/telegram_login")
async def telegram_login(state: str, telegram_id: int):
    if telegram_id <= 0:
        raise HTTPException(status_code=400, detail="Invalid telegram_id")
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
    is_admin = state.startswith("admin_")
    db_state = state.replace("admin_", "") if is_admin else state

    session = await db_manager.get_auth_session(db_state)
    if not session and not is_admin:
        raise HTTPException(status_code=400, detail="Invalid or expired session state.")

    flow = _make_flow(state=state)
    flow.fetch_token(code=code)
    creds = flow.credentials

    auth_token = {
        "token":         creds.token,
        "refresh_token": creds.refresh_token,
        "expires_at":    creds.expiry.isoformat() if creds.expiry else None,
        "token_uri":     creds.token_uri,
        "client_id":     creds.client_id,
        "client_secret": creds.client_secret,
        "scopes":        list(creds.scopes or []),
    }

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
        except Exception:
            email = None

    # ── Admin flow ──
    if is_admin:
        if email and await db_manager.check_admin(email):
            role   = await db_manager.get_admin_role(email)
            expire = datetime.utcnow() + timedelta(hours=24)
            token  = jwt.encode({"sub": email, "role": role, "exp": expire},
                                SECRET_KEY, algorithm=ALGORITHM)
            await db_manager.delete_auth_session(db_state)
            return RedirectResponse(
                url=f"{settings.FRONTEND_URL}/admin/dashboard?token={token}&email={email}"
            )
        return RedirectResponse(
            url=f"{settings.FRONTEND_URL}/admin/login?error=Unauthorized+Admin+Email"
        )

    # ── User flow ──
    telegram_id = session.get("telegram_id")
    if telegram_id is None:
        raise HTTPException(status_code=400, detail="OAuth session missing Telegram identifier")

    existing = await db_manager.get_user(telegram_id)
    user_email = email or (existing.get("email") if existing else None)

    # Preserve existing refresh_token if new creds didn't include one
    if existing and existing.get("auth_token"):
        old = existing["auth_token"]
        if not auth_token.get("refresh_token") and old.get("refresh_token"):
            auth_token["refresh_token"] = old["refresh_token"]

    if existing:
        await db_manager.upsert_user_token(telegram_id, user_email, auth_token)
    else:
        await db_manager.create_user(telegram_id, email=user_email, auth_token=auth_token)

    try:
        await db_manager.db.run(
            lambda: db_manager.db.client.table("auth_sessions")
                    .delete().eq("telegram_id", telegram_id).execute()
        )
    except Exception:
        pass

    asyncio.create_task(_send_welcome_to_telegram(telegram_id))

    return HTMLResponse("""
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Authentication Successful</title>
        <script src="https://cdn.tailwindcss.com"></script>
    </head>
    <body class="bg-gray-50 dark:bg-gray-900 flex items-center justify-center min-h-screen px-4 font-sans">
        <div class="max-w-md w-full bg-white dark:bg-gray-800 rounded-2xl shadow-xl p-8 text-center border border-gray-100 dark:border-gray-700">
            <div class="w-20 h-20 bg-green-100 dark:bg-green-900/30 rounded-full flex items-center justify-center mx-auto mb-6">
                <svg class="w-10 h-10 text-green-500" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M5 13l4 4L19 7"/>
                </svg>
            </div>
            <h1 class="text-2xl font-bold text-gray-900 dark:text-white mb-3">Login Successful!</h1>
            <p class="text-gray-500 dark:text-gray-400 mb-6 text-sm leading-relaxed">
                Your Google Account has been securely verified and linked to your AI Assistant.
            </p>
            <div class="bg-blue-50 dark:bg-blue-900/20 border border-blue-100 dark:border-blue-800/30 rounded-xl p-4 mb-6">
                <p class="text-sm text-blue-700 dark:text-blue-300 font-medium">
                    ✅ Go back to Telegram. Your Main Dashboard is ready.
                </p>
            </div>
            <button
                onclick="window.close()"
                class="w-full bg-gray-900 hover:bg-gray-800 dark:bg-white dark:hover:bg-gray-100 dark:text-gray-900 text-white font-semibold py-3.5 px-4 rounded-xl transition duration-200 shadow-sm text-sm"
            >
                Close This Window
            </button>
        </div>
    </body>
    </html>
    """)