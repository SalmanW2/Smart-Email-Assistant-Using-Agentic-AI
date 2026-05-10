import asyncio
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, HTMLResponse, RedirectResponse
import uvicorn
from config import settings

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
# Ensure frontend can talk to backend
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- REGISTER ROUTERS ---
# All logic is now handled in these modular files
app.include_router(auth_router, prefix="/api/auth", tags=["Authentication"])
app.include_router(admin_router, prefix="/api/admin", tags=["Admin"])
app.include_router(user_router, prefix="/api/user", tags=["User"])

# --- CORE SYSTEM ENDPOINTS ---

@app.get("/", response_class=HTMLResponse)
async def root():
    """Root endpoint with basic UI."""
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
async def root_callback_redirect(request: Request):
    """Catches Google's root callback and redirects it to the correct auth router."""
    query_params = request.url.query
    return RedirectResponse(url=f"/api/auth/callback?{query_params}")

@app.get("/health")
async def health_check():
    """Health check for Render/Deployment monitoring."""
    return {
        "status": "healthy",
        "timestamp": settings.get_utc_now()
    }

@app.post("/webhook/telegram")
async def telegram_webhook(request: Request):
    """Handles real-time updates from Telegram."""
    try:
        update_data = await request.json()
        await telegram_handler.process_webhook(update_data)
        return {"status": "ok"}
    except Exception as e:
        print(f"🔥 Telegram Webhook Error: {e}")
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