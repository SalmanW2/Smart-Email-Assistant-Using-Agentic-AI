import os
import json
import logging
from fastapi import APIRouter, Request, HTTPException
from fastapi.responses import RedirectResponse
from google_auth_oauthlib.flow import Flow
from config import RENDER_URL, REDIRECT_URI, SCOPES
from db.models import DBManager

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/auth", tags=["Auth"])

def get_google_flow():
    return Flow.from_client_secrets_file(
        'credentials.json',
        scopes=SCOPES,
        redirect_uri=REDIRECT_URI
    )

@router.get("/login")
async def login(token: str):
    """Verifies the secure token and starts Google OAuth."""
    tg_id = DBManager.verify_auth_session(token)
    if not tg_id:
        raise HTTPException(status_code=400, detail="Security Error: Invalid or expired login token.")
    
    flow = get_google_flow()
    authorization_url, state = flow.authorization_url(
        access_type='offline',
        include_granted_scopes='true',
        prompt='consent',
        state=token # Pass our secure cipher token directly to Google
    )
    return RedirectResponse(url=authorization_url)

@router.get("/callback")
async def callback(request: Request, state: str, code: str):
    """Handles Google redirect, verifies token again, and saves data."""
    try:
        # 'state' is our secure token returned by Google
        tg_id = DBManager.verify_auth_session(state)
        if not tg_id:
            raise HTTPException(status_code=400, detail="Security Error: Session expired.")

        flow = get_google_flow()
        flow.fetch_token(authorization_response=str(request.url))
        credentials = flow.credentials

        token_data = {
            'token': credentials.token,
            'refresh_token': credentials.refresh_token,
            'token_uri': credentials.token_uri,
            'client_id': credentials.client_id,
            'client_secret': credentials.client_secret,
            'scopes': credentials.scopes
        }

        # Save token and delete the one-time session
        DBManager.create_or_update_user(telegram_id=tg_id, auth_token=token_data, is_verified=True)
        DBManager.delete_auth_session(state)
        
        # Redirect directly into the React Dashboard
        FRONTEND_URL = os.getenv("FRONTEND_URL", "http://localhost:5173")
        return RedirectResponse(url=f"{FRONTEND_URL}/dashboard?auth=success")
    
    except Exception as e:
        logger.error(f"OAuth Callback Error: {e}")
        raise HTTPException(status_code=400, detail="Authentication failed.")