import os
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.sessions import SessionMiddleware
from app.config import get_settings
from app.database import init_db
from app.routers import pipeline, participant, admin

STATIC_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "static")
settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    yield


app = FastAPI(title="停顿回溯标注工具", lifespan=lifespan)
app.add_middleware(SessionMiddleware, secret_key=settings.secret_key)

# Routers
app.include_router(pipeline.router, prefix="/api")
app.include_router(participant.router, prefix="/api")
app.include_router(admin.router, prefix="/api")


@app.get("/api/health")
async def health():
    return {"status": "ok"}


# Static files (frontend) — keep after all routes so routes take priority
app.mount("/", StaticFiles(directory=STATIC_DIR, html=True), name="static")
