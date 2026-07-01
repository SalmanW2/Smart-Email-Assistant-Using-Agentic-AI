import os
import asyncio
import logging
from datetime import datetime, timezone
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, HTMLResponse, RedirectResponse, FileResponse
from fastapi.staticfiles import StaticFiles
import uvicorn
from config import settings

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# --- MODULAR IMPORTS ---
from api.auth import router as auth_router
from api.admin import router as admin_router
from api.user import router as user_router
from bot.telegram_handler import telegram_handler
from bot.voice_handler import voice_handler

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan manager - Initializes bot and voice on startup."""
    print("🚀 Starting AI Email Assistant Backend...")

    # Initialize Telegram bot
    try:
        await telegram_handler.setup_bot()
        print("✅ Telegram bot initialized")
    except Exception as e:
        print(f"❌ Failed to initialize Telegram bot: {e}")

    # Check voice capabilities
    try:
        voice_status = await voice_handler.get_voice_status()
        print(f"🎙️ Voice capabilities: {voice_status}")
    except Exception as e:
        print(f"⚠️ Voice initialization failed: {e}")

    yield
    print("🛑 Shutting down AI Email Assistant...")

# Create FastAPI app
app = FastAPI(
    title="AI Email Assistant",
    description="Intelligent email management with Agentic AI",
    version="1.1.0",
    lifespan=lifespan
)

# --- CORS MIDDLEWARE ---
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- REGISTER ROUTERS ---
# All logic is smoothly delegated to modular routers
app.include_router(auth_router, prefix="/auth", tags=["Authentication"])
app.include_router(admin_router, prefix="/admin", tags=["Admin"])
app.include_router(user_router, prefix="/user", tags=["User"])

# --- CORE SYSTEM ENDPOINTS ---

@app.get("/", response_class=HTMLResponse)
async def root():
    """Root endpoint. Serves frontend if available, else basic UI."""
    frontend_dist = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "frontend", "dist")
    index_path = os.path.join(frontend_dist, "index.html")
    if os.path.exists(index_path):
        return FileResponse(index_path)
        
    return """
    <html>
        <body style="font-family: Arial, sans-serif; text-align: center; padding-top: 100px; background-color: #f4f6f8;">
            <div style="background: white; max-width: 600px; margin: 0 auto; padding: 40px; border-radius: 12px; box-shadow: 0 4px 15px rgba(0,0,0,0.1);">
                <h1 style="color: #2563eb; font-size: 28px;">🚀 AI Email Assistant is Live</h1>
                <p style="color: #475569; font-size: 16px; margin-top: 10px;">The backend API service is operating perfectly.</p>
                <hr style="border: none; border-top: 1px solid #e2e8f0; margin: 20px 0;">
                <p style="color: #94a3b8; font-size: 14px;">Please use the Telegram Bot or Admin Dashboard to interact.</p>
            </div>
        </body>
    </html>
    """

@app.get("/callback")
async def google_callback_forwarder(request: Request):
    """
    Legacy Forwarder: Prevents Google OAuth from breaking if the Google Cloud 
    Console is still pointing to the root /callback instead of /api/auth/callback.
    """
    code = request.query_params.get("code")
    state = request.query_params.get("state")
    
    if code and state:
        return RedirectResponse(url=f"/api/auth/callback?code={code}&state={state}")
    
    return RedirectResponse(url="/api/auth/callback")

@app.get("/health")
async def health_check():
    """Health check for Deployment monitoring."""
    from db.models import db_manager
    
    db_status = "disconnected"
    try:
        # Simple DB check
        await db_manager.get_admin_users(use_cache=False)
        db_status = "connected"
    except Exception as e:
        logger.error(f"Database health check failed: {e}")
        db_status = f"error: {str(e)}"
        
    return {
        "status": "healthy" if db_status == "connected" else "degraded",
        "database": db_status,
        "timestamp": settings.get_utc_now()
    }

@app.post("/webhook/telegram")
async def telegram_webhook(request: Request, background_tasks: BackgroundTasks):
    """Handles real-time updates from Telegram."""
    try:
        update_data = await request.json()
        logger.info(f"Received webhook payload: {update_data}")
        
        async def process_update():
            try:
                await telegram_handler.process_webhook(update_data)
            except Exception as inner_e:
                logger.error(f"🔥 Background Webhook Error: {inner_e}", exc_info=True)
                
        background_tasks.add_task(process_update)
        return {"status": "ok"}
    except Exception as e:
        logger.error(f"🔥 Telegram Webhook Error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Webhook processing failed")

@app.post("/webhook/oauth/callback")
async def oauth_callback_webhook(request: Request):
    """Fallback handler for Google OAuth webhooks."""
    try:
        data = await request.json()
        return {"status": "processed", "detail": "Handled via modular auth"}
    except Exception as e:
        print(f"🔥 OAuth Callback Error: {e}")
        raise HTTPException(status_code=500, detail="OAuth processing failed")

@app.get("/voice/status")
async def voice_status():
    """Check voice processing availability."""
    try:
        return await voice_handler.get_voice_status()
    except Exception as e:
        raise HTTPException(status_code=500, detail="Failed to get voice status")

@app.post("/admin/logout")
async def admin_logout():
    """Admin logout endpoint fallback."""
    return {"message": "Logged out successfully"}

# --- FRONTEND STATIC & CATCH-ALL ROUTING ---
frontend_dist = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "frontend", "dist")
assets_dir = os.path.join(frontend_dist, "assets")

# Ensure directories exist so FastAPI StaticFiles doesn't crash on startup
os.makedirs(assets_dir, exist_ok=True)

# Mount the 'assets' directory to serve JS, CSS, etc.
app.mount("/assets", StaticFiles(directory=assets_dir), name="assets")

# Catch-all route for client-side routing (must be the LAST route before error handlers)
@app.get("/{full_path:path}")
async def serve_frontend(full_path: str):
    potential_path = os.path.join(frontend_dist, full_path)
    # Prevent directory traversal
    if not os.path.abspath(potential_path).startswith(os.path.abspath(frontend_dist)):
        return JSONResponse(status_code=403, content={"detail": "Forbidden"})
        
    if os.path.isfile(potential_path):
        return FileResponse(potential_path)
        
    index_path = os.path.join(frontend_dist, "index.html")
    if os.path.exists(index_path):
        return FileResponse(index_path)
        
    return JSONResponse(status_code=404, content={"detail": "Frontend build not found. Run build.sh"})

# --- GLOBAL ERROR HANDLER ---

@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """Prevents server from crashing by catching all unhandled errors."""
    print(f"❗ UNHANDLED ERROR: {exc}")
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal server error", "error": str(exc)}
    )

if __name__ == "__main__":
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=settings.PORT,
        reload=settings.DEBUG,
        log_level="info"
    )