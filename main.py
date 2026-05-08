"""
Main FastAPI Application
Entry point for the entire Smart Email Assistant application
"""

import asyncio
import httpx
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware

from telegram import Update
from telegram.ext import Application

from config import BOT_TOKEN, RENDER_URL
from db.models import UserModel, LoginModel
from auth import get_login_url, get_admin_login_url, process_callback
from bot.telegram_handler import bot_handler
from frontend import frontend_router
from api.user import user_router
from api.admin import admin_router

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


# ===== BACKGROUND TASKS =====

async def keep_awake():
    """Pings server every 14 minutes to prevent sleep on free tier."""
    url = f"{RENDER_URL}/ping"
    async with httpx.AsyncClient() as client:
        while True:
            try:
                await asyncio.sleep(14 * 60)  # 14 minutes
                await client.get(url)
                logger.info("✅ Keep-alive ping sent")
            except Exception as e:
                logger.error(f"Ping error: {e}")


# ===== APPLICATION LIFECYCLE =====

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Manages FastAPI application lifecycle."""
    
    # ===== STARTUP =====
    logger.info("🚀 Starting Smart Email Assistant...")
    
    # Initialize Telegram bot
    try:
        await bot_handler.ptb_app.initialize()
        await bot_handler.ptb_app.bot.delete_webhook(drop_pending_updates=True)
        await asyncio.sleep(1)
        await bot_handler.ptb_app.bot.set_webhook(url=f"{RENDER_URL}/{BOT_TOKEN}")
        logger.info("✅ Webhook synchronized successfully")
    except Exception as e:
        logger.error(f"⚠️ Webhook Error: {e}")
    
    # Start bot
    try:
        await bot_handler.ptb_app.start()
        logger.info("✅ Telegram bot started")
    except Exception as e:
        logger.error(f"Bot start error: {e}")
    
    # Schedule background jobs
    bot_handler.ptb_app.job_queue.run_repeating(
        bot_handler.check_new_emails,
        interval=60,
        first=10
    )
    logger.info("✅ Email check job scheduled (every 60 seconds)")
    
    bot_handler.ptb_app.job_queue.run_repeating(
        bot_handler.auto_ping,
        interval=840,  # 14 minutes
        first=60
    )
    logger.info("✅ Keep-alive job scheduled (every 14 minutes)")
    
    # Start keep-alive task
    ping_task = asyncio.create_task(keep_awake())
    
    logger.info("✅ Smart Email Assistant fully initialized and online")
    
    yield
    
    # ===== SHUTDOWN =====
    logger.info("🛑 Shutting down...")
    
    ping_task.cancel()
    
    try:
        if bot_handler.ptb_app.running:
            await bot_handler.ptb_app.stop()
            await bot_handler.ptb_app.shutdown()
            logger.info("✅ Bot shutdown gracefully")
    except RuntimeError as e:
        logger.info(f"Bot shutdown note: {e}")
    except Exception as e:
        logger.error(f"Shutdown error: {e}")
    
    logger.info("✅ Shutdown complete")


# ===== CREATE FASTAPI APP =====

app = FastAPI(
    title="Smart Email Assistant",
    description="AI-powered Telegram bot for Gmail management",
    version="2.0.0",
    lifespan=lifespan
)

# ===== CORS CONFIGURATION =====

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ===== INCLUDE ROUTERS =====

app.include_router(frontend_router)
app.include_router(user_router)
app.include_router(admin_router)

# ===== ENDPOINTS =====

@app.get("/")
async def root():
    """Root endpoint."""
    return {"status": "Smart Email Assistant API is running"}


@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {
        "status": "ok",
        "service": "Smart Email Assistant",
        "version": "2.0.0"
    }


@app.get("/ping")
async def ping():
    """Keep-alive ping endpoint."""
    return {"status": "Render is Awake!"}


# ===== TELEGRAM WEBHOOK =====

@app.post(f"/{BOT_TOKEN}")
async def telegram_webhook(request: Request):
    """Telegram webhook endpoint."""
    try:
        data = await request.json()
        update = Update.de_json(data, bot_handler.ptb_app.bot)
        await bot_handler.ptb_app.process_update(update)
        return {"status": "ok"}
    except Exception as e:
        logger.error(f"Webhook error: {e}")
        return {"status": "error", "message": str(e)}


# ===== OAUTH CALLBACK =====

@app.get("/callback")
async def google_callback(request: Request):
    """Google OAuth callback handler."""
    try:
        code = request.query_params.get("code")
        state_uuid = request.query_params.get("state")
        
        if not code or not state_uuid:
            return RedirectResponse(
                url="/callback_success?msg=Invalid Request&success=false"
            )
        
        # Process OAuth
        status_type, result_data = process_callback(code, state_uuid)
        
        # Route based on status
        if status_type == "admin":
            # Admin login successful
            response = RedirectResponse(url="/admin/dashboard", status_code=302)
            response.set_cookie(key="admin_session", value=result_data, max_age=86400)
            logger.info(f"✅ Admin login: {result_data}")
            return response
        
        elif status_type == "error" and "Admin" in result_data:
            # Admin unauthorized
            logger.warning(f"❌ Admin unauthorized: {result_data}")
            return RedirectResponse(
                url=f"/callback_success?msg={result_data}&success=false&is_admin_error=true"
            )
        
        elif status_type == "user":
            # User login successful
            logger.info(f"✅ User login successful")
            return RedirectResponse(
                url=f"/callback_success?msg={result_data}&success=true"
            )
        
        else:
            # Standard error
            logger.error(f"Callback error: {result_data}")
            return RedirectResponse(
                url=f"/callback_success?msg={result_data}&success=false"
            )
    
    except Exception as e:
        logger.error(f"Callback processing error: {e}")
        return RedirectResponse(
            url=f"/callback_success?msg=Callback failed&success=false"
        )


# ===== ERROR HANDLERS =====

@app.exception_handler(Exception)
async def general_exception_handler(request: Request, exc: Exception):
    """Global exception handler."""
    logger.error(f"Unhandled exception: {exc}")
    return {
        "status": "error",
        "message": "An unexpected error occurred",
        "detail": str(exc)
    }


# ===== STARTUP EVENT =====

@app.on_event("startup")
async def startup_event():
    """Runs on application startup."""
    logger.info("=== STARTUP EVENT ===")
    logger.info(f"RENDER_URL: {RENDER_URL}")
    logger.info(f"BOT_TOKEN: {BOT_TOKEN[:10]}...")


# ===== SHUTDOWN EVENT =====

@app.on_event("shutdown")
async def shutdown_event():
    """Runs on application shutdown."""
    logger.info("=== SHUTDOWN EVENT ===")


# ===== UVICORN RUNNER =====

if __name__ == "__main__":
    import uvicorn
    import os
    
    port = int(os.getenv("PORT", 10000))
    
    logger.info(f"🚀 Starting Uvicorn on port {port}")
    
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=port,
        reload=False,
        log_level="info"
    )