"""
Authentication API - OAuth 2.0 with Google
Handles login, callback, and session management
"""

import logging
from typing import Tuple, Optional
from google_auth_oauthlib.flow import Flow
from googleapiclient.discovery import build

from config import RENDER_URL, SCOPES, GEMINI_API_KEY
from db.models import (
    AuthSessionModel, LoginModel, UserModel, AdminModel,
    BlocklistModel
)

logger = logging.getLogger(__name__)

# Temporary storage for OAuth flows
oauth_sessions = {}


def get_login_url(telegram_id: int) -> str:
    """Generates login URL for Telegram users."""
    try:
        state_uuid = AuthSessionModel.create_session(telegram_id)
        
        flow = Flow.from_client_secrets_file(
            'credentials.json',
            scopes=SCOPES,
            redirect_uri=f"{RENDER_URL}/callback"
        )
        
        auth_url, _ = flow.authorization_url(
            prompt='consent',
            access_type='offline',
            state=state_uuid
        )
        
        oauth_sessions[state_uuid] = flow
        
        logger.info(f"Login URL created for user {telegram_id}")
        return auth_url
    except Exception as e:
        logger.error(f"Login URL generation error: {e}")
        return ""


def get_admin_login_url() -> str:
    """Generates login URL for Administrators."""
    try:
        state_uuid = AuthSessionModel.create_session(0)  # 0 = admin flag
        
        flow = Flow.from_client_secrets_file(
            'credentials.json',
            scopes=SCOPES,
            redirect_uri=f"{RENDER_URL}/callback"
        )
        
        auth_url, _ = flow.authorization_url(
            prompt='consent',
            access_type='offline',
            state=state_uuid
        )
        
        oauth_sessions[state_uuid] = flow
        
        logger.info("Admin login URL created")
        return auth_url
    except Exception as e:
        logger.error(f"Admin login URL generation error: {e}")
        return ""


def process_callback(code: str, state_uuid: str) -> Tuple[str, str]:
    """
    Processes Google OAuth callback.
    
    Returns: (status_type, result_data)
    - status_type: 'admin', 'user', 'error'
    - result_data: email (for admin), message (for user/error)
    """
    
    try:
        # Verify session
        telegram_id = AuthSessionModel.verify_session(state_uuid)
        
        if telegram_id is None:
            return "error", "Security Error: Session expired or invalid CSRF token."
        
        # Get flow from memory
        flow = oauth_sessions.get(state_uuid)
        if not flow:
            return "error", "Session expired. Please try logging in again."
        
        # Fetch token
        try:
            flow.fetch_token(code=code)
        except Exception as e:
            logger.error(f"Token fetch error: {e}")
            return "error", f"Failed to fetch token: {str(e)}"
        
        creds = flow.credentials
        
        # Get user info
        try:
            user_info_service = build('oauth2', 'v2', credentials=creds)
            user_info = user_info_service.userinfo().get().execute()
            email = user_info.get("email")
        except Exception as e:
            logger.error(f"User info fetch error: {e}")
            return "error", f"Failed to get user info: {str(e)}"
        
        # Clean memory
        if state_uuid in oauth_sessions:
            del oauth_sessions[state_uuid]
        
        # ===== ADMIN LOGIN =====
        if telegram_id == 0:
            if AdminModel.check_admin(email):
                logger.info(f"✅ Admin login successful: {email}")
                return "admin", email
            else:
                logger.warning(f"❌ Unauthorized admin login attempt: {email}")
                return "error", "Access Denied: You are not authorized as an Administrator."
        
        # ===== USER LOGIN =====
        
        # Check if email is blocked
        if BlocklistModel.block_check("email", email):
            logger.warning(f"Blocked email login attempt: {email}")
            return "error", "Access Denied: This email address has been blacklisted."
        
        # Save token
        token_json = {
            "token": creds.token,
            "refresh_token": creds.refresh_token,
            "token_uri": creds.token_uri,
            "client_id": creds.client_id,
            "client_secret": creds.client_secret,
            "scopes": creds.scopes
        }
        
        if LoginModel.save_login_data(telegram_id, email, token_json):
            logger.info(f"✅ User login successful: {telegram_id} ({email})")
            return "user", "Success! Your account has been successfully linked."
        else:
            logger.error(f"Failed to save login data for user {telegram_id}")
            return "error", "Failed to save login data. Please try again."
    
    except Exception as e:
        logger.error(f"Callback processing error: {e}")
        return "error", f"Authentication failed: {str(e)}"


def validate_admin_email(email: str) -> bool:
    """Validates if email is an admin."""
    return AdminModel.check_admin(email)


def get_admin_role(email: str) -> str:
    """Gets admin role."""
    return AdminModel.get_admin_role(email)