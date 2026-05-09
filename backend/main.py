from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
import asyncio
from bot.telegram_handler import setup_bot
from api.auth import router as auth_router
from api.admin import router as admin_router
from api.user import router as user_router
from config import config

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    bot_task = asyncio.create_task(setup_bot())
    yield
    # Shutdown
    bot_task.cancel()
    try:
        await bot_task
    except asyncio.CancelledError:
        pass

app = FastAPI(title="Smart Email Assistant", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[config.FRONTEND_URL],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth_router, prefix="/auth", tags=["auth"])
app.include_router(admin_router, prefix="/admin", tags=["admin"])
app.include_router(user_router, prefix="/user", tags=["user"])

@app.get("/")
async def root():
    return {"message": "Smart Email Assistant API"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=config.PORT)