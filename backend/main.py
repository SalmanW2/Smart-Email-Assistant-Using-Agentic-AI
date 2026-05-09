from fastapi import FastAPI, Request, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
from telegram import Update
from bot.telegram_handler import TelegramBotManager
from api.auth import router as auth_router
from api.admin import router as admin_router
from config import settings

bot_manager = TelegramBotManager()

@asynccontextmanager
async def lifespan(app: FastAPI):
    await bot_manager.start()
    yield
    await bot_manager.stop()

app = FastAPI(title="Smart Email Assistant", version="1.0.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.FRONTEND_URL],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth_router, prefix="/api/auth", tags=["auth"])
app.include_router(admin_router, prefix="/api/admin", tags=["admin"])

@app.post("/webhook")
async def telegram_webhook(request: Request):
    payload = await request.json()
    if not bot_manager.application or not bot_manager.application.bot:
        raise HTTPException(status_code=503, detail="Telegram bot is not initialized")

    update = Update.de_json(payload, bot_manager.application.bot)
    await bot_manager.application.process_update(update)
    return {"ok": True}

@app.get("/")
async def root() -> dict[str, str]:
    return {"message": "Smart Email Assistant API"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=settings.PORT)
