import os
import asyncio
import httpx
import logging
import uvicorn
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from telegram import Update
from bot.telegram_handler import bot_handler_instance
from api import auth, admin, user
from config import BOT_TOKEN, WEBHOOK_URL, RENDER_URL

logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

async def keep_awake():
    """Background task to ping the server to prevent sleep on free Render tier."""
    url = f"{RENDER_URL}/ping"
    async with httpx.AsyncClient() as client:
        while True:
            await asyncio.sleep(14 * 60) # 14 minutes
            try:
                await client.get(url)
            except Exception:
                pass

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Initialize Telegram Bot & Webhook
    await bot_handler_instance.ptb_app.initialize()
    await bot_handler_instance.ptb_app.bot.set_webhook(url=f"{WEBHOOK_URL}/webhook")
    await bot_handler_instance.ptb_app.start()
    logger.info("✅ Telegram Webhook synchronized successfully.")
    
    # Start anti-sleep background process
    ping_task = asyncio.create_task(keep_awake())
    
    yield
    
    # Graceful Shutdown
    ping_task.cancel()
    await bot_handler_instance.ptb_app.stop()
    await bot_handler_instance.ptb_app.shutdown()
    logger.info("✅ Bot shutdown gracefully.")

app = FastAPI(lifespan=lifespan)

# CORS for React Frontend (Allowing your local Vite server and Render URL)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include React API Routes
app.include_router(auth.router)
app.include_router(admin.router)
app.include_router(user.router)

@app.get("/ping")
async def ping():
    return {"status": "Render is Awake!"}

@app.post("/webhook")
async def telegram_webhook(request: Request):
    try:
        data = await request.json()
        update = Update.de_json(data, bot_handler_instance.ptb_app.bot)
        await bot_handler_instance.ptb_app.process_update(update)
        return {"ok": True}
    except Exception as e:
        logger.error(f"Webhook Error: {e}")
        return {"ok": False}

if __name__ == "__main__":
    port = int(os.getenv("PORT", 10000))
    uvicorn.run("main:app", host="0.0.0.0", port=port)