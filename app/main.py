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

# 临时方案：启动时删除旧数据库以应用新 schema（移除 utterance_id 唯一约束）
# 生产环境应使用 Alembic 等迁移工具
_reset_flag = os.getenv("RESET_DB_ONCE")
if _reset_flag == "true":
    db_path = Path(settings.database_path)
    if db_path.exists():
        print(f"[临时] 删除旧数据库: {db_path}")
        db_path.unlink()
        print("[临时] 数据库已删除，将重建")


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
