import asyncio
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
import uvicorn
from config import settings
from auth import router as auth_router
from admin import router as admin_router
from user import router as user_router
from telegram_handler import telegram_handler
from voice_handler import voice_handler

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan manager."""
    # Startup
    print("Starting AI Email Assistant...")

    # Setup Telegram bot
    try:
        await telegram_handler.setup_bot()
        print("Telegram bot initialized")
    except Exception as e:
        print(f"Failed to initialize Telegram bot: {e}")

    # Check voice capabilities
    voice_status = await voice_handler.get_voice_status()
    print(f"Voice capabilities: {voice_status}")

    yield

    # Shutdown
    print("Shutting down AI Email Assistant...")

# Create FastAPI app
app = FastAPI(
    title="AI Email Assistant",
    description="Intelligent email management with AI-powered assistance",
    version="1.0.0",
    lifespan=lifespan
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(
    auth_router,
    prefix="/api/auth",
    tags=["Authentication"]
)

app.include_router(
    admin_router,
    prefix="/api/admin",
    tags=["Admin"]
)

app.include_router(
    user_router,
    prefix="/api/user",
    tags=["User"]
)

@app.get("/")
async def root():
    """Root endpoint."""
    return {
        "message": "AI Email Assistant API",
        "version": "1.0.0",
        "status": "running"
    }

@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {
        "status": "healthy",
        "timestamp": settings.get_utc_now()
    }

@app.post("/webhook/telegram")
async def telegram_webhook(request: Request):
    """Telegram webhook endpoint."""
    try:
        update_data = await request.json()
        await telegram_handler.process_webhook(update_data)
        return {"status": "ok"}
    except Exception as e:
        print(f"Webhook error: {e}")
        raise HTTPException(status_code=500, detail="Webhook processing failed")

@app.post("/webhook/oauth/callback")
async def oauth_callback_webhook(request: Request):
    """Handle OAuth callback via webhook."""
    try:
        data = await request.json()
        # Process OAuth callback
        # This would exchange code for tokens and update user
        return {"status": "processed"}
    except Exception as e:
        print(f"OAuth callback error: {e}")
        raise HTTPException(status_code=500, detail="OAuth processing failed")

@app.get("/voice/status")
async def voice_status():
    """Get voice processing status."""
    try:
        status = await voice_handler.get_voice_status()
        return status
    except Exception as e:
        print(f"Voice status error: {e}")
        raise HTTPException(status_code=500, detail="Failed to get voice status")

@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """Global exception handler."""
    print(f"Unhandled exception: {exc}")
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal server error"}
    )

if __name__ == "__main__":
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=settings.PORT,
        reload=settings.DEBUG,
        log_level="info"
    )
