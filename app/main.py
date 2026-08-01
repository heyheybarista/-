import os
from pathlib import Path
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.sessions import SessionMiddleware
from app.config import get_settings
from app.database import init_db
from app.routers import pipeline, participant, admin

STATIC_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "static")
settings = get_settings()

# Schema 迁移已完成，删除临时重置代码


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


# Participant page — serve participant.html at /a/{token} so the frontend JS can parse the token from the URL path
@app.get("/a/{token:path}")
async def serve_participant_page(token: str):
    return FileResponse(os.path.join(STATIC_DIR, "participant.html"))

# Static files (frontend) — keep after all routes so routes take priority
app.mount("/", StaticFiles(directory=STATIC_DIR, html=True), name="static")
