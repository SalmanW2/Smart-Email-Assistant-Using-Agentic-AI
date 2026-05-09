from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import RedirectResponse
from google_auth_oauthlib.flow import Flow
from google.oauth2.credentials import Credentials
from db.models import db_manager
import uuid
from config import config
import json

router = APIRouter()

# Load client secrets
with open('credentials.json', 'r') as f:
    client_config = json.load(f)

@router.get("/login")
async def login(token: str):
    # Validate token (simplified - in production, store tokens in DB)
    flow = Flow.from_client_config(
        client_config,
        scopes=['https://www.googleapis.com/auth/gmail.modify'],
        redirect_uri=config.REDIRECT_URI
    )
    authorization_url, state = flow.authorization_url(
        access_type='offline',
        include_granted_scopes='true'
    )
    # Store state for validation
    return RedirectResponse(authorization_url)

@router.get("/callback")
async def callback(request: Request, code: str, state: str):
    flow = Flow.from_client_config(
        client_config,
        scopes=['https://www.googleapis.com/auth/gmail.modify'],
        redirect_uri=config.REDIRECT_URI
    )
    
    flow.fetch_token(code=code)
    creds = flow.credentials
    
    # Associate with user (simplified - use state to identify user)
    user_id = "placeholder"  # Get from state/token
    
    await db_manager.create_auth_session(
        user_id,
        creds.token,
        creds.refresh_token,
        creds.expiry.timestamp()
    )
    
    return RedirectResponse(f"{config.FRONTEND_URL}/dashboard")

@router.post("/logout")
async def logout(user_id: str):
    await db_manager.delete_auth_session(user_id)
    return {"message": "Logged out"}