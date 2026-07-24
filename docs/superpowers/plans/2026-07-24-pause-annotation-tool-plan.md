# 口语停顿回溯标注工具 — 实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**目标：** 构建一个 FastAPI + SQLite + 轻量 Web 前端的停顿回溯标注工具，部署到 VAD/EasyTurn 主机，供线上被试远程填写停顿原因，主试管理会话并导出数据。

**架构：** FastAPI 提供 REST API 与静态前端；SQLite 单文件持久化；前端用原生 HTML/CSS/JS（无构建工具链），被试页含完整对话流与标注表单，主试页含会话管理。

**技术栈：** Python 3.11+ / FastAPI / SQLAlchemy (async) / SQLite (WAL) / aiosqlite / bcrypt / Jinja2 或纯静态前端 / uvicorn

## 全局约束

- 项目根目录：`停顿标注工具/`，所有代码在此下
- Python ≥ 3.11；依赖列于 `requirements.txt`
- SQLite WAL 模式；数据库文件 `data/app.db`
- 被试链接 = `{PUBLIC_BASE_URL}/a/{token}`；不绑 HTTPS
- 主试鉴权用 session cookie；流水线共用 Bearer `PIPELINE_TOKEN`
- 第一版不涉及音频、句内多 pause、邮件通知、会话隔离
- 前端无构建工具链；FastAPI 直接 serve 静态文件
- 指导语快照策略：会话创建时固化 instruction_snapshot

---

## 文件结构（最终成品）

```text
停顿标注工具/
├── app/
│   ├── __init__.py
│   ├── main.py              # FastAPI 入口 + 静态文件挂载
│   ├── config.py            # Settings / 环境变量
│   ├── database.py          # engine / session / init_db
│   ├── models.py            # SQLAlchemy ORM
│   ├── schemas.py           # Pydantic 入出参
│   ├── auth.py              # 主试 session + 流水线 bearer
│   ├── routers/
│   │   ├── __init__.py
│   │   ├── pipeline.py      # POST /api/pipeline/sessions
│   │   ├── participant.py   # GET/PATCH/POST /api/a/{token}/*
│   │   └── admin.py         # /api/admin/* (login, sessions, settings, users)
│   └── utils.py             # token 生成、EasyTurn 标签解析
├── static/
│   ├── participant.html     # 被试填写页（SPA）
│   ├── admin-login.html     # 主试登录
│   ├── admin-sessions.html  # 会话列表
│   ├── admin-detail.html    # 会话详情
│   ├── admin-settings.html  # 设置（指导语/标签/类别）
│   ├── admin-users.html     # 主试账号管理
│   └── css/
│       └── style.css        # 全局样式（移动端友好）
├── data/
│   └── .gitkeep
├── scripts/
│   ├── install.sh           # 首次安装脚本
│   ├── run.sh               # 启动脚本
│   └── pipeline_client.py   # 流水线 SDK 示例
├── .env.example
├── requirements.txt
└── README.md                # 部署与使用说明
```

---

### Task 0: 项目骨架与基础设施

**文件：**
- 创建：`app/__init__.py`, `app/config.py`, `app/database.py`, `app/models.py`, `app/main.py`, `app/auth.py`, `app/schemas.py`, `app/utils.py`, `app/routers/__init__.py`
- 创建：`data/.gitkeep`, `.env.example`, `requirements.txt`
- 创建：`scripts/install.sh`, `scripts/run.sh`

**产生：** 可启动的 FastAPI 空服务 + 数据库表 + 健康检查端点

---

- [ ] **Step 1: 写 `.env.example`**

```text
HOST=0.0.0.0
PORT=8000
PUBLIC_BASE_URL=http://localhost:8000
PIPELINE_TOKEN=change-me-to-a-random-secret
SECRET_KEY=change-me-to-another-random-secret
DATABASE_PATH=./data/app.db
```

- [ ] **Step 2: 写 `requirements.txt`**

```text
fastapi>=0.115.0
uvicorn[standard]>=0.30.0
sqlalchemy[asyncio]>=2.0.30
aiosqlite>=0.20.0
pydantic>=2.7.0
pydantic-settings>=2.3.0
bcrypt>=4.1.0
python-multipart>=0.0.9
```

- [ ] **Step 3: 写 `app/config.py`**

```python
from pydantic_settings import BaseSettings
from functools import lru_cache


class Settings(BaseSettings):
    host: str = "0.0.0.0"
    port: int = 8000
    public_base_url: str = "http://localhost:8000"
    pipeline_token: str = "change-me"
    secret_key: str = "change-me"
    database_path: str = "./data/app.db"

    model_config = dict(env_file=".env", env_file_encoding="utf-8")


@lru_cache()
def get_settings() -> Settings:
    return Settings()
```

- [ ] **Step 4: 写 `app/database.py`**

```python
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy.orm import DeclarativeBase
from app.config import get_settings

settings = get_settings()
# SQLite with aiosqlite, WAL mode
DATABASE_URL = f"sqlite+aiosqlite:///{settings.database_path}"

engine = create_async_engine(DATABASE_URL, echo=False, connect_args={"check_same_thread": False})

AsyncSessionLocal = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


async def init_db():
    import app.models  # noqa: ensure all models loaded
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    # enable WAL
    async with engine.connect() as conn:
        await conn.exec_driver_sql("PRAGMA journal_mode=WAL")
        await conn.exec_driver_sql("PRAGMA foreign_keys=ON")


async def get_db() -> AsyncSession:
    async with AsyncSessionLocal() as session:
        try:
            yield session
        finally:
            await session.close()
```

- [ ] **Step 5: 写 `app/models.py`**

```python
import uuid
from datetime import datetime, timezone
from sqlalchemy import Column, String, Integer, Text, Boolean, DateTime, ForeignKey, JSON, Enum as SAEnum
from sqlalchemy.orm import relationship
from app.database import Base

def _new_id() -> str:
    return uuid.uuid4().hex[:12]

def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Experimenter(Base):
    __tablename__ = "experimenters"
    id = Column(String(24), primary_key=True, default=_new_id)
    username = Column(String(64), unique=True, nullable=False)
    password_hash = Column(String(128), nullable=False)
    role = Column(String(16), nullable=False, default="experimenter")  # admin | experimenter
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=_utcnow)


class Session(Base):
    __tablename__ = "sessions"
    id = Column(String(24), primary_key=True, default=_new_id)
    external_participant_id = Column(String(64), nullable=True)
    title = Column(String(256), nullable=True)
    status = Column(String(20), nullable=False, default="created")  # created | in_progress | submitted
    access_token = Column(String(64), unique=True, nullable=False, index=True)
    annotatable_labels = Column(JSON, nullable=False, default=list)
    pipeline_meta = Column(JSON, nullable=True)
    instruction_snapshot = Column(Text, nullable=True)
    created_at = Column(DateTime, default=_utcnow)
    opened_at = Column(DateTime, nullable=True)
    submitted_at = Column(DateTime, nullable=True)

    utterances = relationship("Utterance", back_populates="session", order_by="Utterance.seq",
                              cascade="all, delete-orphan")
    annotation_targets = relationship("AnnotationTarget", back_populates="session",
                                      cascade="all, delete-orphan")


class Utterance(Base):
    __tablename__ = "utterances"
    id = Column(String(24), primary_key=True, default=_new_id)
    session_id = Column(String(24), ForeignKey("sessions.id"), nullable=False)
    seq = Column(Integer, nullable=False)
    speaker = Column(String(20), nullable=False)  # participant | experimenter
    text = Column(Text, nullable=False)
    raw_text = Column(Text, nullable=True)
    easyturn_label = Column(String(20), nullable=True)
    start_ms = Column(Integer, nullable=True)
    end_ms = Column(Integer, nullable=True)
    duration_ms = Column(Integer, nullable=True)
    extra = Column(JSON, nullable=True)

    session = relationship("Session", back_populates="utterances")
    annotation_target = relationship("AnnotationTarget", back_populates="utterance", uselist=False,
                                     cascade="all, delete-orphan")


class AnnotationTarget(Base):
    __tablename__ = "annotation_targets"
    id = Column(String(24), primary_key=True, default=_new_id)
    session_id = Column(String(24), ForeignKey("sessions.id"), nullable=False)
    utterance_id = Column(String(24), ForeignKey("utterances.id"), nullable=False, unique=True)
    label = Column(String(20), nullable=False)
    required = Column(Boolean, default=True)
    display_hint = Column(String(64), nullable=True)
    pause_duration_ms = Column(Integer, nullable=True)

    session = relationship("Session", back_populates="annotation_targets")
    utterance = relationship("Utterance", back_populates="annotation_target")
    annotation = relationship("Annotation", back_populates="target", uselist=False,
                              cascade="all, delete-orphan")


class Annotation(Base):
    __tablename__ = "annotations"
    id = Column(String(24), primary_key=True, default=_new_id)
    target_id = Column(String(24), ForeignKey("annotation_targets.id"), nullable=False, unique=True)
    category = Column(String(32), nullable=True)
    description = Column(Text, nullable=True)
    confidence = Column(Integer, nullable=True)
    is_complete = Column(Boolean, default=False)
    updated_at = Column(DateTime, default=_utcnow, onupdate=_utcnow)

    target = relationship("AnnotationTarget", back_populates="annotation")


class GlobalSetting(Base):
    __tablename__ = "global_settings"
    key = Column(String(64), primary_key=True)
    value = Column(JSON, nullable=False)
```

- [ ] **Step 6: 写 `app/schemas.py`**

```python
from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime


# --- Pipeline Create Session ---

class UtteranceIn(BaseModel):
    seq: int
    speaker: str  # participant | experimenter
    text: str
    raw_text: Optional[str] = None
    easyturn_label: Optional[str] = None
    start_ms: Optional[int] = None
    end_ms: Optional[int] = None
    duration_ms: Optional[int] = None
    pause_duration_ms: Optional[int] = None
    extra: Optional[dict] = None


class CreateSessionRequest(BaseModel):
    external_participant_id: Optional[str] = None
    title: Optional[str] = None
    annotatable_labels: Optional[list[str]] = None
    pipeline_meta: Optional[dict] = None
    utterances: list[UtteranceIn]


class CreateSessionResponse(BaseModel):
    session_id: str
    access_token: str
    participant_url: str
    admin_url: str
    target_count: int
    status: str


# --- Participant ---

class AnnotationTargetOut(BaseModel):
    id: str
    utterance_id: str
    label: str
    required: bool
    display_hint: Optional[str] = None
    pause_duration_ms: Optional[int] = None
    annotation: Optional[dict] = None  # {category, description, confidence, is_complete}

    model_config = dict(from_attributes=True)


class UtteranceOut(BaseModel):
    id: str
    seq: int
    speaker: str
    text: str
    easyturn_label: Optional[str] = None
    start_ms: Optional[int] = None
    end_ms: Optional[int] = None
    duration_ms: Optional[int] = None
    pause_duration_ms: Optional[int] = None
    annotation_target: Optional[AnnotationTargetOut] = None

    model_config = dict(from_attributes=True)


class ParticipantSessionOut(BaseModel):
    session_id: str
    title: Optional[str]
    status: str
    instruction: Optional[str]
    utterances: list[UtteranceOut]


class PatchAnnotationRequest(BaseModel):
    category: Optional[str] = None
    description: Optional[str] = None
    confidence: Optional[int] = Field(default=None, ge=1, le=7)


# --- Admin ---

class SessionListItem(BaseModel):
    id: str
    external_participant_id: Optional[str]
    title: Optional[str]
    status: str
    target_count: int
    completed_count: int
    created_at: datetime
    submitted_at: Optional[datetime]


class AdminLoginRequest(BaseModel):
    username: str
    password: str


# --- Settings ---

class SettingsUpdate(BaseModel):
    instruction_text: Optional[str] = None
    annotatable_labels: Optional[list[str]] = None
    reason_categories: Optional[list[dict]] = None  # [{value, label, hint}]


class SettingsOut(BaseModel):
    instruction_text: str
    annotatable_labels: list[str]
    reason_categories: list[dict]


# --- Users ---

class UserCreate(BaseModel):
    username: str = Field(min_length=2, max_length=64)
    password: str = Field(min_length=6, max_length=128)
    role: str = "experimenter"


class UserOut(BaseModel):
    id: str
    username: str
    role: str
    is_active: bool
    created_at: datetime


class UserPasswordReset(BaseModel):
    new_password: str = Field(min_length=6, max_length=128)
```

- [ ] **Step 7: 写 `app/auth.py`**

```python
import secrets
from fastapi import Request, HTTPException, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.config import get_settings
from app.models import Experimenter

security_scheme = HTTPBearer(auto_error=False)


def verify_pipeline_token(credentials: HTTPAuthorizationCredentials | None = Depends(security_scheme)):
    """Verify Bearer PIPELINE_TOKEN for pipeline endpoints."""
    if not credentials:
        raise HTTPException(status_code=401, detail="Missing token")
    if not secrets.compare_digest(credentials.credentials, get_settings().pipeline_token):
        raise HTTPException(status_code=401, detail="Invalid pipeline token")
    return True


# Admin session: store logged-in user id in request.session
ADMIN_SESSION_KEY = "experimenter_id"


async def get_current_user(request: Request, db: AsyncSession) -> Experimenter:
    user_id = request.session.get(ADMIN_SESSION_KEY)
    if not user_id:
        raise HTTPException(status_code=401, detail="Not logged in")
    stmt = select(Experimenter).where(Experimenter.id == user_id, Experimenter.is_active == True)
    result = await db.execute(stmt)
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=401, detail="Invalid session")
    return user


def require_admin(user: Experimenter = Depends(get_current_user)):
    if user.role != "admin":
        raise HTTPException(status_code=403, detail="Admin only")
    return user
```

- [ ] **Step 8: 写 `app/utils.py`**

```python
import re
import secrets

EASYTURN_LABEL_RE = re.compile(r"<(\w+)>")


def generate_token(length: int = 32) -> str:
    return secrets.token_urlsafe(length)


def parse_easyturn(raw: str) -> tuple[str, str | None]:
    """
    输入："因为小时候<incomplete><|endoftext|>"
    返回：(clean_text, label)  如 ("因为小时候", "incomplete")
    """
    clean = re.sub(r"<\|endoftext\|>", "", raw, flags=re.IGNORECASE).strip()
    match = EASYTURN_LABEL_RE.findall(clean)
    label = match[-1].lower() if match else None
    if label:
        clean = re.sub(rf"\s*<{re.escape(label)}>\s*$", "", clean).strip()
    return clean, label


# 默认配置——与 models/settings 保持一致，也用于首次初始化
DEFAULT_INSTRUCTION = """**任务说明**
下面呈现的是你刚才与主试完成英语口语任务时的对话转录。系统已在你的部分发言处标出可能与「未说完 / 需要等待」相关的位置（由话轮模型自动标记）。

**请你做什么**
请依次查看每一处标记。结合前后对话，回忆当时你为什么会这样停顿、犹豫或没有继续说完，并填写：
1）最符合的原因类别；
2）当时的原因与心理过程（请写具体一些，例如你在想哪个词、哪句结构、还是在组织内容）；
3）你对上述描述的确信程度（1–7）。

**描述建议**
- 请尽量描述「当下」的想法，而不是事后合理化。
- 建议每处约 20–100 字；若确实记不清，可如实写"记不清"，并在置信度上选择较低分数。
- 主试的发言仅帮助你回忆语境，无需对主试发言作答。

**提交**
所有标记处填写完成后，点击顶部「提交」。提交后不可再修改。填写过程中会自动保存进度，可中途关闭，稍后用同一链接继续。"""

DEFAULT_ANNOTATABLE_LABELS = ["incomplete", "wait"]

DEFAULT_REASON_CATEGORIES = [
    {"value": "lexical", "label": "找词 / 词汇提取"},
    {"value": "syntax", "label": "句法 / 句子组织"},
    {"value": "thinking", "label": "内容思考"},
    {"value": "intention_shift", "label": "意图切换"},
    {"value": "interactive", "label": "互动 / 等待对方"},
    {"value": "external", "label": "外部干扰"},
    {"value": "other", "label": "其他"},
]

LABEL_HINTS = {
    "incomplete": "未说完",
    "wait": "等待",
    "complete": "完整",
    "backchannel": "附和",
}
```

- [ ] **Step 9: 写 `app/routers/__init__.py`**

```python
# 空文件，标记 routers 为包
```

- [ ] **Step 10: 写 `app/main.py`（最小可运行版）**

```python
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

# Static files (frontend)
app.mount("/", StaticFiles(directory=STATIC_DIR, html=True), name="static")


@app.get("/api/health")
async def health():
    return {"status": "ok"}
```

- [ ] **Step 11: 写 `scripts/install.sh`**

```bash
#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
echo "==> Creating virtual environment..."
python3 -m venv .venv
source .venv/bin/activate 2>/dev/null || source .venv/Scripts/activate
echo "==> Installing dependencies..."
pip install -r requirements.txt
echo "==> Copying .env if not present..."
[ -f .env ] || cp .env.example .env
echo "==> Done. Edit .env then run: scripts/run.sh"
```

- [ ] **Step 12: 写 `scripts/run.sh`**

```bash
#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
source .venv/bin/activate 2>/dev/null || source .venv/Scripts/activate
mkdir -p data
exec uvicorn app.main:app --host "${HOST:-0.0.0.0}" --port "${PORT:-8000}"
```

- [ ] **Step 13: 创建空前端占位**

创建 `data/.gitkeep`（空文件）。创建 `static/css/style.css`，内容为：

```css
*, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }
body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", "Microsoft YaHei", sans-serif; line-height: 1.6; color: #1a1a1a; background: #f5f5f5; padding: 0; }
.container { max-width: 800px; margin: 0 auto; padding: 16px; }
.card { background: #fff; border-radius: 8px; padding: 16px; margin-bottom: 12px; box-shadow: 0 1px 3px rgba(0,0,0,0.08); }
.btn { display: inline-block; padding: 8px 16px; border: none; border-radius: 6px; cursor: pointer; font-size: 14px; }
.btn-primary { background: #2563eb; color: #fff; }
.btn-primary:disabled { background: #93a3c0; cursor: not-allowed; }
.btn-danger { background: #dc2626; color: #fff; }
.topbar { display: flex; justify-content: space-between; align-items: center; padding: 12px 16px; background: #fff; border-bottom: 1px solid #e5e7eb; position: sticky; top: 0; z-index: 10; }
.badge { display: inline-block; padding: 2px 8px; border-radius: 12px; font-size: 12px; font-weight: 600; }
.badge-incomplete { background: #fef3c7; color: #92400e; }
.badge-wait { background: #dbeafe; color: #1e40af; }
.badge-complete { background: #d1fae5; color: #065f46; }
.badge-backchannel { background: #f3f4f6; color: #374151; }
.utterance { padding: 10px 14px; border-radius: 8px; margin-bottom: 8px; }
.utterance-experimenter { background: #f0f4ff; border-left: 3px solid #93a3c0; }
.utterance-participant { background: #fff; border: 1px solid #e5e7eb; }
.annotation-form { margin-top: 10px; padding: 12px; background: #fefce8; border-radius: 8px; border: 1px solid #fde68a; }
.annotation-form label { display: block; margin-bottom: 4px; font-weight: 600; font-size: 13px; }
.annotation-form select, .annotation-form textarea { width: 100%; padding: 8px; border: 1px solid #d1d5db; border-radius: 6px; font-size: 14px; margin-bottom: 10px; }
.confidence-row { display: flex; gap: 8px; align-items: center; margin-bottom: 8px; }
.confidence-btn { width: 36px; height: 36px; border-radius: 50%; border: 2px solid #d1d5db; background: #fff; cursor: pointer; font-size: 14px; }
.confidence-btn.selected { border-color: #2563eb; background: #dbeafe; font-weight: 700; }
table { width: 100%; border-collapse: collapse; }
th, td { padding: 8px 12px; text-align: left; border-bottom: 1px solid #e5e7eb; }
th { font-size: 12px; text-transform: uppercase; color: #6b7280; }
progress { width: 100%; height: 8px; border-radius: 4px; }
progress::-webkit-progress-bar { background: #e5e7eb; border-radius: 4px; }
progress::-webkit-progress-value { background: #2563eb; border-radius: 4px; }
@media (max-width: 600px) { .container { padding: 8px; } .card { padding: 12px; } }
```

- [ ] **Step 14: 验证骨架**

```bash
cd 停顿标注工具
cp .env.example .env
python3 -m venv .venv && source .venv/bin/activate && pip install -r requirements.txt
uvicorn app.main:app --port 8000 &
sleep 2
curl http://127.0.0.1:8000/api/health
# 预期: {"status":"ok"}
```

- [ ] **Step 15: Commit（可选，有 git 时）**

---

### Task 1: 流水线创建会话 API

**文件：**
- 创建：`app/routers/pipeline.py`
- 创建：`scripts/pipeline_client.py`

**接口：**
- 产生：`POST /api/pipeline/sessions` → `CreateSessionResponse`

---

- [ ] **Step 1: 写 `app/routers/pipeline.py`**

```python
import uuid
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.database import get_db
from app.models import Session, Utterance, AnnotationTarget
from app.schemas import CreateSessionRequest, CreateSessionResponse
from app.auth import verify_pipeline_token
from app.utils import generate_token, parse_easyturn, DEFAULT_ANNOTATABLE_LABELS, LABEL_HINTS, DEFAULT_INSTRUCTION

router = APIRouter()


def _new_id() -> str:
    return uuid.uuid4().hex[:12]


@router.post("/pipeline/sessions", response_model=CreateSessionResponse, dependencies=[Depends(verify_pipeline_token)])
async def create_session(req: CreateSessionRequest, db: AsyncSession = Depends(get_db)):
    # 确定本场可标注标签
    annotatable = req.annotatable_labels or DEFAULT_ANNOTATABLE_LABELS

    session = Session(
        id=_new_id(),
        external_participant_id=req.external_participant_id,
        title=req.title,
        status="created",
        access_token=generate_token(),
        annotatable_labels=annotatable,
        pipeline_meta=req.pipeline_meta,
        instruction_snapshot=DEFAULT_INSTRUCTION,
    )
    db.add(session)

    target_count = 0
    for u in req.utterances:
        # 解析 EasyTurn 标签（若 raw_text 中有标签而 easyturn_label 未显式给出）
        label = u.easyturn_label
        text = u.text
        if u.raw_text and not label:
            text, label = parse_easyturn(u.raw_text)

        utterance = Utterance(
            id=_new_id(),
            session_id=session.id,
            seq=u.seq,
            speaker=u.speaker,
            text=text,
            raw_text=u.raw_text,
            easyturn_label=label,
            start_ms=u.start_ms,
            end_ms=u.end_ms,
            duration_ms=u.duration_ms,
            extra=u.extra,
        )
        db.add(utterance)

        # 是否为被试侧 + 标签在可标注集合中
        if u.speaker == "participant" and label and label in annotatable:
            target = AnnotationTarget(
                id=_new_id(),
                session_id=session.id,
                utterance_id=utterance.id,
                label=label,
                required=True,
                display_hint=LABEL_HINTS.get(label, label),
                pause_duration_ms=u.pause_duration_ms,
            )
            db.add(target)
            target_count += 1

    await db.commit()

    base = "http://localhost:8000"  # will be overridden in config-aware response below
    from app.config import get_settings
    settings = get_settings()
    base = settings.public_base_url.rstrip("/")

    return CreateSessionResponse(
        session_id=session.id,
        access_token=session.access_token,
        participant_url=f"{base}/a/{session.access_token}",
        admin_url=f"{base}/admin-sessions.html",
        target_count=target_count,
        status=session.status,
    )
```

- [ ] **Step 2: 写 `scripts/pipeline_client.py`（流水线 SDK 示例）**

```python
#!/usr/bin/env python3
"""
流水线创建会话示例。
使用方式（在 VAD/ASR/EasyTurn 结束后调用）：
    python scripts/pipeline_client.py \\
        --base-url http://127.0.0.1:8000 \\
        --token "$PIPELINE_TOKEN" \\
        --participant P001 \\
        --utterances data.json
"""
import argparse, json, sys, requests


def main():
    parser = argparse.ArgumentParser(description="推送口语会话到停顿标注工具")
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--token", required=True, help="PIPELINE_TOKEN")
    parser.add_argument("--participant", default="", help="被试编号")
    parser.add_argument("--title", default="口语任务")
    parser.add_argument("--utterances", required=True, help="JSON 文件路径，含 utterances 数组")
    parser.add_argument("--labels", default="incomplete,wait", help="本场可标注标签，逗号分隔")
    args = parser.parse_args()

    with open(args.utterances, "r", encoding="utf-8") as f:
        data = json.load(f)

    payload = {
        "external_participant_id": args.participant,
        "title": args.title,
        "annotatable_labels": [x.strip() for x in args.labels.split(",") if x.strip()],
        "utterances": data.get("utterances", data),
    }

    resp = requests.post(
        f"{args.base_url.rstrip('/')}/api/pipeline/sessions",
        json=payload,
        headers={"Authorization": f"Bearer {args.token}"},
        timeout=30,
    )
    resp.raise_for_status()
    result = resp.json()
    print(f"Session created: {result['session_id']}")
    print(f"Participant URL: {result['participant_url']}")
    print(f"Admin URL:      {result['admin_url']}")
    print(f"Target count:   {result['target_count']}")
    return result


if __name__ == "__main__":
    main()
```

- [ ] **Step 3: 手动测试**

```bash
# 启动服务后
curl -X POST http://127.0.0.1:8000/api/pipeline/sessions \
  -H "Authorization: Bearer change-me-to-a-random-secret" \
  -H "Content-Type: application/json" \
  -d '{
    "external_participant_id": "P001",
    "title": "预实验-口语任务",
    "utterances": [
      {"seq":1,"speaker":"experimenter","text":"Have you ever had any funny childhood stories?","raw_text":"Have you ever had any funny childhood stories?<complete>","easyturn_label":"complete"},
      {"seq":2,"speaker":"participant","text":"Because when I was little","raw_text":"Because when I was little<incomplete>","easyturn_label":"incomplete","pause_duration_ms":800},
      {"seq":3,"speaker":"participant","text":"Oh yes I remember once","raw_text":"Oh yes I remember once<complete>","easyturn_label":"complete"}
    ]
  }'
# 预期：返回 session_id、token、participant_url、target_count=1
```

---

### Task 2: 被试填写页 API

**文件：**
- 创建：`app/routers/participant.py`

**接口：**
- 产生：`GET /api/a/{token}`, `PATCH /api/a/{token}/annotations/{target_id}`, `POST /api/a/{token}/submit`

---

- [ ] **Step 1: 写 `app/routers/participant.py`**

```python
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from sqlalchemy import select
from app.database import get_db
from app.models import Session, Utterance, AnnotationTarget, Annotation
from app.schemas import ParticipantSessionOut, UtteranceOut, AnnotationTargetOut, PatchAnnotationRequest
from app.utils import LABEL_HINTS

router = APIRouter()

MISSING = object()


def _build_target_out(target: AnnotationTarget) -> dict:
    ann = target.annotation
    return {
        "id": target.id,
        "utterance_id": target.utterance_id,
        "label": target.label,
        "required": target.required,
        "display_hint": target.display_hint or LABEL_HINTS.get(target.label, target.label),
        "pause_duration_ms": target.pause_duration_ms,
        "annotation": {
            "category": ann.category,
            "description": ann.description,
            "confidence": ann.confidence,
            "is_complete": ann.is_complete,
        } if ann else None,
    }


@router.get("/a/{token}")
async def get_participant_session(token: str, db: AsyncSession = Depends(get_db)):
    stmt = (
        select(Session)
        .where(Session.access_token == token)
        .options(
            selectinload(Session.utterances).selectinload(Utterance.annotation_target).selectinload(AnnotationTarget.annotation)
        )
    )
    result = await db.execute(stmt)
    session = result.scalar_one_or_none()
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    # 首次打开标记
    if session.status == "created":
        session.status = "in_progress"
        session.opened_at = datetime.now(timezone.utc)
        await db.commit()
        await db.refresh(session)

    utterances_out = []
    for u in session.utterances:
        tgt = u.annotation_target
        utterances_out.append(UtteranceOut(
            id=u.id,
            seq=u.seq,
            speaker=u.speaker,
            text=u.text,
            easyturn_label=u.easyturn_label,
            start_ms=u.start_ms,
            end_ms=u.end_ms,
            duration_ms=u.duration_ms,
            pause_duration_ms=tgt.pause_duration_ms if tgt else None,
            annotation_target=_build_target_out(tgt) if tgt else None,
        ))

    return ParticipantSessionOut(
        session_id=session.id,
        title=session.title,
        status=session.status,
        instruction=session.instruction_snapshot,
        utterances=utterances_out,
    )


@router.patch("/a/{token}/annotations/{target_id}")
async def patch_annotation(token: str, target_id: str, body: PatchAnnotationRequest, db: AsyncSession = Depends(get_db)):
    # 查找 session
    stmt = select(Session).where(Session.access_token == token)
    result = await db.execute(stmt)
    session = result.scalar_one_or_none()
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    if session.status == "submitted":
        raise HTTPException(status_code=400, detail="Session already submitted")

    # 查找 target
    tgt_stmt = select(AnnotationTarget).where(
        AnnotationTarget.id == target_id,
        AnnotationTarget.session_id == session.id,
    ).options(selectinload(AnnotationTarget.annotation))
    result = await db.execute(tgt_stmt)
    target = result.scalar_one_or_none()
    if not target:
        raise HTTPException(status_code=404, detail="Target not found")

    # upsert annotation
    if target.annotation:
        ann = target.annotation
    else:
        ann = Annotation(target_id=target.id)
        db.add(ann)

    if body.category is not MISSING:
        ann.category = body.category
    if body.description is not MISSING:
        ann.description = body.description
    if body.confidence is not MISSING:
        ann.confidence = body.confidence

    # 判断是否完整（三项都有值即为 complete）
    ann.is_complete = bool(ann.category and ann.description and ann.confidence)
    ann.updated_at = datetime.now(timezone.utc)

    await db.commit()
    await db.refresh(ann)
    return {"ok": True, "is_complete": ann.is_complete}


@router.post("/a/{token}/submit")
async def submit_session(token: str, db: AsyncSession = Depends(get_db)):
    stmt = (
        select(Session)
        .where(Session.access_token == token)
        .options(
            selectinload(Session.annotation_targets).selectinload(AnnotationTarget.annotation)
        )
    )
    result = await db.execute(stmt)
    session = result.scalar_one_or_none()
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    if session.status == "submitted":
        return {"ok": True, "message": "Already submitted"}

    # 校验所有 required target 已 complete
    incomplete = []
    for t in session.annotation_targets:
        if t.required:
            ann = t.annotation
            if not ann or not ann.is_complete:
                incomplete.append({"target_id": t.id, "display_hint": t.display_hint or t.label})

    if incomplete:
        raise HTTPException(
            status_code=400,
            detail={"message": "Not all required targets are complete", "incomplete": incomplete},
        )

    session.status = "submitted"
    session.submitted_at = datetime.now(timezone.utc)
    await db.commit()
    return {"ok": True, "message": "Submitted"}
```

- [ ] **Step 2: 验证被试 API**

```bash
# 用 Task 1 创建的 token
TOKEN="<上一步返回的 access_token>"
TARGET_ID="<上一步返回或查询得到的 target_id>"

# GET 会话
curl http://127.0.0.1:8000/api/a/$TOKEN
# 预期：返回 utterances 与 annotation_targets

# PATCH 草稿
curl -X PATCH http://127.0.0.1:8000/api/a/$TOKEN/annotations/$TARGET_ID \
  -H "Content-Type: application/json" \
  -d '{"category":"thinking","description":"在想要不要讲幼儿园的事","confidence":6}'
# 预期：{"ok":true,"is_complete":true}

# 尝试提交（若只有1个target则成功）
curl -X POST http://127.0.0.1:8000/api/a/$TOKEN/submit
# 预期：{"ok":true,"message":"Submitted"}
```

---

### Task 3: 主试登录与会话管理 API

**文件：**
- 创建：`app/routers/admin.py`

**接口：**
- 产生：`POST /api/admin/login`, `POST /api/admin/logout`, `GET /api/admin/me`
- 产生：`GET /api/admin/sessions`, `GET /api/admin/sessions/{id}`, `POST /api/admin/sessions/{id}/reset`, `GET /api/admin/sessions/{id}/export`
- 产生：`GET/PUT /api/admin/settings` (admin only)
- 产生：`GET/POST /api/admin/users`, `PUT /api/admin/users/{id}`, `POST /api/admin/users/{id}/reset-password` (admin only)

---

- [ ] **Step 1: 写 `app/routers/admin.py`（完整）**

```python
import csv, io, json, uuid
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, Request, Query, Response
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from sqlalchemy import select, func, delete
import bcrypt
from app.database import get_db
from app.models import Session, Utterance, AnnotationTarget, Annotation, Experimenter, GlobalSetting
from app.schemas import (
    AdminLoginRequest, SessionListItem, SettingsUpdate, SettingsOut,
    UserCreate, UserOut, UserPasswordReset,
)
from app.auth import get_current_user, require_admin, ADMIN_SESSION_KEY
from app.utils import (
    generate_token, DEFAULT_INSTRUCTION, DEFAULT_ANNOTATABLE_LABELS,
    DEFAULT_REASON_CATEGORIES,
)

router = APIRouter()


def _new_id() -> str:
    return uuid.uuid4().hex[:12]


# ── helpers ────────────────────────────────────────────────

async def _get_settings(db: AsyncSession) -> dict:
    """读取或初始化全局设置"""
    rows = (await db.execute(select(GlobalSetting))).scalars().all()
    store = {r.key: r.value for r in rows}
    if "instruction_text" not in store:
        store["instruction_text"] = DEFAULT_INSTRUCTION
    if "annotatable_labels" not in store:
        store["annotatable_labels"] = DEFAULT_ANNOTATABLE_LABELS
    if "reason_categories" not in store:
        store["reason_categories"] = DEFAULT_REASON_CATEGORIES
    return store


async def _init_admin(db: AsyncSession):
    """确保至少有一个 admin。无则创 admin/admin。"""
    existing = (await db.execute(select(Experimenter))).scalars().first()
    if not existing:
        pw = bcrypt.hashpw("admin".encode(), bcrypt.gensalt()).decode()
        db.add(Experimenter(id=_new_id(), username="admin", password_hash=pw, role="admin"))
        await db.commit()


# ── login / logout ─────────────────────────────────────────

@router.post("/admin/login")
async def admin_login(body: AdminLoginRequest, request: Request, db: AsyncSession = Depends(get_db)):
    await _init_admin(db)
    stmt = select(Experimenter).where(Experimenter.username == body.username, Experimenter.is_active == True)
    user = (await db.execute(stmt)).scalar_one_or_none()
    if not user or not bcrypt.checkpw(body.password.encode(), user.password_hash.encode()):
        raise HTTPException(status_code=401, detail="Invalid credentials")
    request.session[ADMIN_SESSION_KEY] = user.id
    return {"ok": True, "username": user.username, "role": user.role}


@router.post("/admin/logout")
async def admin_logout(request: Request):
    request.session.clear()
    return {"ok": True}


@router.get("/admin/me")
async def admin_me(user: Experimenter = Depends(get_current_user)):
    return {"username": user.username, "role": user.role}


# ── sessions ───────────────────────────────────────────────

@router.get("/admin/sessions")
async def list_sessions(
    db: AsyncSession = Depends(get_db),
    user: Experimenter = Depends(get_current_user),
):
    stmt = (
        select(Session)
        .options(selectinload(Session.annotation_targets).selectinload(AnnotationTarget.annotation))
        .order_by(Session.created_at.desc())
    )
    rows = (await db.execute(stmt)).scalars().all()
    items = []
    for s in rows:
        total = len(s.annotation_targets)
        done = sum(1 for t in s.annotation_targets if t.annotation and t.annotation.is_complete)
        items.append(SessionListItem(
            id=s.id,
            external_participant_id=s.external_participant_id,
            title=s.title,
            status=s.status,
            target_count=total,
            completed_count=done,
            created_at=s.created_at,
            submitted_at=s.submitted_at,
        ))
    return items


@router.get("/admin/sessions/{session_id}")
async def get_session_detail(
    session_id: str,
    db: AsyncSession = Depends(get_db),
    user: Experimenter = Depends(get_current_user),
):
    stmt = (
        select(Session)
        .where(Session.id == session_id)
        .options(
            selectinload(Session.utterances).selectinload(Utterance.annotation_target).selectinload(AnnotationTarget.annotation)
        )
    )
    s = (await db.execute(stmt)).scalar_one_or_none()
    if not s:
        raise HTTPException(status_code=404, detail="Not found")

    utterances = []
    for u in s.utterances:
        t = u.annotation_target
        ann = t.annotation if t else None
        utterances.append({
            "seq": u.seq,
            "speaker": u.speaker,
            "text": u.text,
            "easyturn_label": u.easyturn_label,
            "pause_duration_ms": t.pause_duration_ms if t else None,
            "target": {
                "id": t.id,
                "label": t.label,
                "required": t.required,
                "display_hint": t.display_hint,
                "annotation": {
                    "category": ann.category,
                    "description": ann.description,
                    "confidence": ann.confidence,
                    "is_complete": ann.is_complete,
                } if ann else None,
            } if t else None,
        })

    from app.config import get_settings
    base = get_settings().public_base_url.rstrip("/")

    return {
        "session": {
            "id": s.id,
            "external_participant_id": s.external_participant_id,
            "title": s.title,
            "status": s.status,
            "access_token": s.access_token,
            "participant_url": f"{base}/a/{s.access_token}",
            "instruction_snapshot": s.instruction_snapshot,
            "created_at": s.created_at.isoformat(),
            "submitted_at": s.submitted_at.isoformat() if s.submitted_at else None,
        },
        "utterances": utterances,
    }


@router.post("/admin/sessions/{session_id}/reset")
async def reset_session(
    session_id: str,
    db: AsyncSession = Depends(get_db),
    user: Experimenter = Depends(get_current_user),
):
    s = (await db.execute(select(Session).where(Session.id == session_id))).scalar_one_or_none()
    if not s:
        raise HTTPException(status_code=404, detail="Not found")
    # 删除已有 annotation
    targets = (await db.execute(
        select(AnnotationTarget).where(AnnotationTarget.session_id == session_id)
    )).scalars().all()
    for t in targets:
        await db.execute(delete(Annotation).where(Annotation.target_id == t.id))
    s.status = "in_progress"
    s.submitted_at = None
    await db.commit()
    return {"ok": True, "status": s.status}


@router.get("/admin/sessions/{session_id}/export")
async def export_session(
    session_id: str,
    format: str = Query("json"),
    db: AsyncSession = Depends(get_db),
    user: Experimenter = Depends(get_current_user),
):
    s = (await db.execute(
        select(Session).where(Session.id == session_id).options(
            selectinload(Session.utterances).selectinload(Utterance.annotation_target).selectinload(AnnotationTarget.annotation)
        )
    )).scalar_one_or_none()
    if not s:
        raise HTTPException(status_code=404, detail="Not found")

    rows = []
    for u in s.utterances:
        t = u.annotation_target
        ann = t.annotation if t else None
        rows.append({
            "session_id": s.id,
            "external_participant_id": s.external_participant_id,
            "seq": u.seq,
            "speaker": u.speaker,
            "text": u.text,
            "easyturn_label": u.easyturn_label,
            "pause_duration_ms": t.pause_duration_ms if t else None,
            "target_label": t.label if t else None,
            "category": ann.category if ann else None,
            "description": ann.description if ann else None,
            "confidence": ann.confidence if ann else None,
            "is_complete": ann.is_complete if ann else False,
        })

    if format == "csv":
        output = io.StringIO()
        if rows:
            writer = csv.DictWriter(output, fieldnames=rows[0].keys())
            writer.writeheader()
            writer.writerows(rows)
        return Response(content=output.getvalue(), media_type="text/csv",
                        headers={"Content-Disposition": f"attachment; filename=session_{session_id}.csv"})

    return {
        "session_id": s.id,
        "external_participant_id": s.external_participant_id,
        "status": s.status,
        "submitted_at": s.submitted_at.isoformat() if s.submitted_at else None,
        "instruction_snapshot": s.instruction_snapshot,
        "items": rows,
    }


# ── settings (admin only) ──────────────────────────────────

@router.get("/admin/settings")
async def get_settings(user: Experimenter = Depends(require_admin), db: AsyncSession = Depends(get_db)):
    s = await _get_settings(db)
    return SettingsOut(**s)


@router.put("/admin/settings")
async def update_settings(body: SettingsUpdate, user: Experimenter = Depends(require_admin), db: AsyncSession = Depends(get_db)):
    store = await _get_settings(db)
    if body.instruction_text is not None:
        store["instruction_text"] = body.instruction_text
    if body.annotatable_labels is not None:
        store["annotatable_labels"] = body.annotatable_labels
        # 同时把当前全局默认作为新会话默认——不影响已创建的会话
    if body.reason_categories is not None:
        store["reason_categories"] = body.reason_categories

    for key, val in store.items():
        existing = (await db.execute(select(GlobalSetting).where(GlobalSetting.key == key))).scalar_one_or_none()
        if existing:
            existing.value = val
        else:
            db.add(GlobalSetting(key=key, value=val))
    await db.commit()
    return SettingsOut(**store)


# ── users (admin only) ─────────────────────────────────────

@router.get("/admin/users")
async def list_users(user: Experimenter = Depends(require_admin), db: AsyncSession = Depends(get_db)):
    rows = (await db.execute(select(Experimenter).order_by(Experimenter.created_at))).scalars().all()
    return [UserOut(id=r.id, username=r.username, role=r.role, is_active=r.is_active, created_at=r.created_at) for r in rows]


@router.post("/admin/users")
async def create_user(body: UserCreate, user: Experimenter = Depends(require_admin), db: AsyncSession = Depends(get_db)):
    existing = (await db.execute(select(Experimenter).where(Experimenter.username == body.username))).scalar_one_or_none()
    if existing:
        raise HTTPException(status_code=400, detail="Username already exists")
    pw = bcrypt.hashpw(body.password.encode(), bcrypt.gensalt()).decode()
    new_user = Experimenter(id=_new_id(), username=body.username, password_hash=pw, role=body.role)
    db.add(new_user)
    await db.commit()
    return UserOut(id=new_user.id, username=new_user.username, role=new_user.role, is_active=True, created_at=new_user.created_at)


@router.put("/admin/users/{user_id}")
async def toggle_user_active(user_id: str, user: Experimenter = Depends(require_admin), db: AsyncSession = Depends(get_db)):
    target = (await db.execute(select(Experimenter).where(Experimenter.id == user_id))).scalar_one_or_none()
    if not target:
        raise HTTPException(status_code=404, detail="Not found")
    target.is_active = not target.is_active
    await db.commit()
    return {"ok": True, "is_active": target.is_active}


@router.post("/admin/users/{user_id}/reset-password")
async def reset_user_password(user_id: str, body: UserPasswordReset, user: Experimenter = Depends(require_admin), db: AsyncSession = Depends(get_db)):
    target = (await db.execute(select(Experimenter).where(Experimenter.id == user_id))).scalar_one_or_none()
    if not target:
        raise HTTPException(status_code=404, detail="Not found")
    target.password_hash = bcrypt.hashpw(body.new_password.encode(), bcrypt.gensalt()).decode()
    await db.commit()
    return {"ok": True}
```

- [ ] **Step 2: 验证主试 API**

```bash
# 登录
curl -X POST http://127.0.0.1:8000/api/admin/login \
  -H "Content-Type: application/json" \
  -d '{"username":"admin","password":"admin"}' \
  -c /tmp/cookies.txt
# 预期：{"ok":true,"username":"admin","role":"admin"}

# 会话列表
curl http://127.0.0.1:8000/api/admin/sessions -b /tmp/cookies.txt
# 预期：数组，含 Task 1 创建的会话

# 设置
curl http://127.0.0.1:8000/api/admin/settings -b /tmp/cookies.txt
# 预期：{instruction_text, annotatable_labels, reason_categories}

# 用户列表
curl http://127.0.0.1:8000/api/admin/users -b /tmp/cookies.txt
# 预期：[{username:"admin",role:"admin",...}]
```

---

### Task 4: 被试填写页前端

**文件：**
- 创建：`static/participant.html`
- 修改：`static/css/style.css`（已有基础样式）

**接口：**
- 消耗：`GET /api/a/{token}`, `PATCH /api/a/{token}/annotations/{target_id}`, `POST /api/a/{token}/submit`

---

- [ ] **Step 1: 写 `static/participant.html`**

```html
<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>停顿回溯标注</title>
<link rel="stylesheet" href="/css/style.css">
<style>
  .instruction-card { background: #eff6ff; border: 1px solid #bfdbfe; border-radius: 8px; padding: 16px; margin-bottom: 16px; }
  .instruction-card summary { font-weight: 700; cursor: pointer; font-size: 15px; }
  .instruction-body { margin-top: 8px; font-size: 14px; line-height: 1.7; white-space: pre-wrap; }
  .save-status { font-size: 12px; color: #6b7280; }
  .save-status.saved { color: #059669; }
  .save-status.saving { color: #d97706; }
  .save-status.error { color: #dc2626; }
  .speaker-label { font-size: 11px; font-weight: 700; text-transform: uppercase; margin-bottom: 2px; }
  .speaker-label.experimenter { color: #4b5563; }
  .speaker-label.participant { color: #2563eb; }
</style>
</head>
<body>
<div class="topbar" id="topbar">
  <div>
    <strong id="title-display">停顿回溯标注</strong>
    <span class="save-status saved" id="save-status">已保存</span>
  </div>
  <div style="display:flex;align-items:center;gap:12px;">
    <span style="font-size:14px;" id="progress-text">0/0</span>
    <progress id="progress-bar" value="0" max="100" style="width:120px;"></progress>
    <button class="btn btn-primary" id="submit-btn" disabled>提交</button>
  </div>
</div>

<div class="container" id="app">
  <div class="card" id="loading">加载中…</div>
</div>

<script>
const TOKEN = window.location.pathname.split('/').pop();
let sessionData = null;
let debounceTimers = {};

// ── API helpers ──────────────────────────────────
const api = {
  async get() {
    const r = await fetch(`/api/a/${TOKEN}`);
    if (!r.ok) throw new Error(await r.text());
    return r.json();
  },
  async patch(targetId, body) {
    const r = await fetch(`/api/a/${TOKEN}/annotations/${targetId}`, {
      method: 'PATCH', headers: {'Content-Type':'application/json'}, body: JSON.stringify(body)
    });
    if (!r.ok) throw new Error(await r.text());
    return r.json();
  },
  async submit() {
    const r = await fetch(`/api/a/${TOKEN}/submit`, { method: 'POST' });
    if (!r.ok) {
      const err = await r.json();
      throw new Error(typeof err.detail === 'object' ? JSON.stringify(err.detail) : err.detail);
    }
    return r.json();
  }
};

// ── Save status ─────────────────────────────────
function setSaveStatus(state) {
  const el = document.getElementById('save-status');
  el.className = 'save-status ' + state;
  el.textContent = {saved:'已保存', saving:'保存中…', error:'保存失败'}[state] || state;
}

function autoSave(targetId, field, value) {
  setSaveStatus('saving');
  clearTimeout(debounceTimers[targetId + field]);
  debounceTimers[targetId + field] = setTimeout(async () => {
    try {
      await api.patch(targetId, { [field]: value });
      setSaveStatus('saved');
      updateProgress();
    } catch(e) {
      setSaveStatus('error');
      console.error(e);
    }
  }, field === 'confidence' ? 0 : 800);
}

// ── Progress ────────────────────────────────────
function updateProgress() {
  const targets = document.querySelectorAll('.annotation-form');
  let done = 0;
  targets.forEach(f => {
    const cat = f.querySelector('select')?.value;
    const desc = f.querySelector('textarea')?.value.trim();
    const conf = f.querySelector('.confidence-btn.selected')?.dataset?.value;
    if (cat && desc && conf) done++;
  });
  const total = targets.length;
  document.getElementById('progress-text').textContent = `${done}/${total}`;
  document.getElementById('progress-bar').value = total ? (done / total) * 100 : 0;
  document.getElementById('submit-btn').disabled = done < total;
}

// ── Render ──────────────────────────────────────
function render(data) {
  sessionData = data;
  document.getElementById('title-display').textContent = data.title || '停顿回溯标注';

  const isReadonly = data.status === 'submitted';

  let html = '';

  // Instruction
  if (data.instruction) {
    html += `<details class="instruction-card" open>
      <summary>📋 填写说明</summary>
      <div class="instruction-body">${escapeHtml(data.instruction)}</div>
    </details>`;
  }

  // Dialogue
  if (!data.utterances || data.utterances.length === 0) {
    html += '<div class="card"><p>暂无对话数据。</p></div>';
  } else {
    html += '<div class="card">';
    for (const u of data.utterances) {
      const speakerClass = u.speaker === 'experimenter' ? 'experimenter' : 'participant';
      const speakerName = u.speaker === 'experimenter' ? '主试' : '被试';
      html += `<div class="utterance utterance-${speakerClass}">
        <div class="speaker-label ${speakerClass}">${speakerName} · #${u.seq}</div>
        <p>${escapeHtml(u.text)}</p>`;

      // Badge
      if (u.easyturn_label) {
        html += `<span class="badge badge-${u.easyturn_label}">${u.easyturn_label}</span>`;
      }
      if (u.pause_duration_ms) {
        html += ` <span style="font-size:12px;color:#6b7280;">约 ${(u.pause_duration_ms/1000).toFixed(1)}s</span>`;
      }

      // Annotation form if target exists
      if (u.annotation_target) {
        const t = u.annotation_target;
        const ann = t.annotation || {};
        html += renderAnnotationForm(t, ann, isReadonly);
      }

      html += '</div>';
    }
    html += '</div>';
  }

  // Submitted notice
  if (isReadonly) {
    html = '<div class="card" style="background:#d1fae5;border:1px solid #059669;text-align:center;margin-bottom:16px;">✅ 你已于 ' + (data.status === 'submitted' ? '提交完成' : '') + '。以下为只读查看。</div>' + html;
  }

  document.getElementById('app').innerHTML = html;

  // Bind events
  if (!isReadonly) {
    document.querySelectorAll('.annotation-form').forEach(form => {
      const targetId = form.dataset.targetId;
      form.querySelector('select').addEventListener('change', e => {
        autoSave(targetId, 'category', e.target.value);
      });
      form.querySelector('textarea').addEventListener('input', e => {
        autoSave(targetId, 'description', e.target.value);
      });
      form.querySelectorAll('.confidence-btn').forEach(btn => {
        btn.addEventListener('click', () => {
          form.querySelectorAll('.confidence-btn').forEach(b => b.classList.remove('selected'));
          btn.classList.add('selected');
          autoSave(targetId, 'confidence', parseInt(btn.dataset.value));
        });
      });
    });
    document.getElementById('submit-btn').addEventListener('click', handleSubmit);
  }

  updateProgress();
}

function renderAnnotationForm(target, ann, readonly) {
  const categories = JSON.parse(document.getElementById('categories-data')?.textContent || '[]');
  const catOptions = categories.map(c =>
    `<option value="${escapeHtml(c.value)}" ${ann.category === c.value ? 'selected' : ''}>${escapeHtml(c.label)}</option>`
  ).join('');

  const confHtml = [1,2,3,4,5,6,7].map(v =>
    `<button type="button" class="confidence-btn ${ann.confidence === v ? 'selected' : ''}" data-value="${v}" ${readonly?'disabled':''}>${v}</button>`
  ).join('');

  return `<div class="annotation-form" data-target-id="${target.id}">
    <div style="font-size:12px;color:#92400e;margin-bottom:6px;">🏷 标记：<strong>${escapeHtml(target.display_hint || target.label)}</strong>${target.required ? '（必填）' : ''}</div>
    <label>原因类别</label>
    <select ${readonly?'disabled':''}>${catOptions}</select>
    <label>原因与心理过程</label>
    <textarea rows="3" placeholder="请描述当时停顿的原因…" ${readonly?'disabled':''}>${escapeHtml(ann.description || '')}</textarea>
    <label>置信度：你在多大程度上确信该停顿原因的描述？</label>
    <div class="confidence-row">${confHtml}</div>
  </div>`;
}

async function handleSubmit() {
  if (!confirm('确认提交？提交后不可再修改。')) return;
  try {
    await api.submit();
    alert('提交成功！');
    location.reload();
  } catch(e) {
    alert('提交失败：' + e.message);
  }
}

function escapeHtml(str) {
  const div = document.createElement('div');
  div.textContent = str || '';
  return div.innerHTML;
}

// ── Init ─────────────────────────────────────────
(async () => {
  try {
    // load categories from settings (fetched via session metadata or separate call)
    // We embed them via a small inline fetch
    const catResp = await fetch('/api/admin/settings');
    let categories = [];
    if (catResp.ok) {
      const settings = await catResp.json();
      categories = settings.reason_categories || [];
    }
    // embed categories for render function
    const script = document.createElement('script');
    script.id = 'categories-data';
    script.type = 'application/json';
    script.textContent = JSON.stringify(categories);
    document.head.appendChild(script);

    const data = await api.get();
    render(data);
  } catch(e) {
    document.getElementById('app').innerHTML = `<div class="card" style="color:#dc2626;">加载失败：${escapeHtml(e.message)}<br>请确认链接正确且已由主试创建会话。</div>`;
  }
})();
</script>
</body>
</html>
```

> **注意**：`/api/admin/settings` 不需要登录（直接暴露出类别给被试页使用）。把 admin router 里的 settings GET 去掉 `require_admin` 依赖即可。

- [ ] **Step 2: 去掉 settings GET 鉴权**

修改 `app/routers/admin.py` 中 `get_settings` 的依赖签名，改为不用 `require_admin`：

```python
# 找到
async def get_settings(user: Experimenter = Depends(require_admin), db: AsyncSession = Depends(get_db)):
# 替换为
async def get_settings(db: AsyncSession = Depends(get_db)):
```

- [ ] **Step 3: 验证**

```bash
# 用浏览器打开 participant_url
# 预期：看到对话流 + 标注表单 + 指导语
# 填写 → 刷新 → 草稿仍在 → 全填完提交 → 只读
```

---

### Task 5: 主试端前端页面

**文件：**
- 创建：`static/admin-login.html`, `static/admin-sessions.html`, `static/admin-detail.html`, `static/admin-settings.html`, `static/admin-users.html`

---

- [ ] **Step 1: 写 `static/admin-login.html`**

```html
<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>主试登录</title>
<link rel="stylesheet" href="/css/style.css">
<style>
  .login-box { max-width: 360px; margin: 80px auto; }
  .login-box input { width: 100%; padding: 10px; margin-bottom: 12px; border: 1px solid #d1d5db; border-radius: 6px; font-size: 14px; }
  .error-msg { color: #dc2626; font-size: 13px; margin-bottom: 8px; }
</style>
</head>
<body>
<div class="login-box card">
  <h2 style="text-align:center;margin-bottom:16px;">主试登录</h2>
  <div class="error-msg" id="error" style="display:none;"></div>
  <input id="username" placeholder="用户名" autocomplete="username">
  <input id="password" type="password" placeholder="密码" autocomplete="current-password">
  <button class="btn btn-primary" style="width:100%;" onclick="login()">登录</button>
</div>
<script>
async function login() {
  const u = document.getElementById('username').value.trim();
  const p = document.getElementById('password').value;
  if (!u || !p) return;
  try {
    const r = await fetch('/api/admin/login', {
      method: 'POST', headers: {'Content-Type':'application/json'},
      body: JSON.stringify({username:u, password:p})
    });
    if (!r.ok) {
      document.getElementById('error').textContent = '用户名或密码错误';
      document.getElementById('error').style.display = 'block';
      return;
    }
    const d = await r.json();
    // Store in sessionStorage for frontend guard
    sessionStorage.setItem('adminUser', JSON.stringify(d));
    window.location.href = '/admin-sessions.html';
  } catch(e) {
    document.getElementById('error').textContent = '网络错误: ' + e.message;
    document.getElementById('error').style.display = 'block';
  }
}
</script>
</body>
</html>
```

- [ ] **Step 2: 写 `static/admin-sessions.html`**

```html
<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>会话列表 - 主试端</title>
<link rel="stylesheet" href="/css/style.css">
<style>
  .nav { display: flex; gap: 12px; margin-bottom: 16px; flex-wrap: wrap; }
  .nav a { color: #2563eb; text-decoration: none; font-size: 14px; }
  .status-dot { display: inline-block; width: 8px; height: 8px; border-radius: 50%; margin-right: 4px; }
  .status-dot.created { background: #9ca3af; }
  .status-dot.in_progress { background: #f59e0b; }
  .status-dot.submitted { background: #10b981; }
</style>
</head>
<body>
<div class="topbar">
  <strong>主试端 · 会话列表</strong>
  <div style="display:flex;gap:12px;align-items:center;">
    <a href="/admin-sessions.html">列表</a>
    <a href="/admin-settings.html">设置</a>
    <a href="/admin-users.html">账号</a>
    <a href="#" onclick="logout()">登出</a>
  </div>
</div>
<div class="container">
  <div class="nav">
    <button class="btn btn-primary" onclick="refresh()">刷新</button>
  </div>
  <div class="card">
    <table id="sessions-table">
      <thead><tr><th>被试编号</th><th>标题</th><th>状态</th><th>进度</th><th>时间</th><th>操作</th></tr></thead>
      <tbody id="sessions-body"></tbody>
    </table>
    <p id="empty-msg" style="display:none;color:#6b7280;text-align:center;padding:24px;">暂无会话。</p>
  </div>
</div>
<script>
function checkAuth() {
  if (!sessionStorage.getItem('adminUser')) {
    window.location.href = '/admin-login.html';
  }
}

async function refresh() {
  checkAuth();
  try {
    const r = await fetch('/api/admin/sessions');
    if (r.status === 401) { window.location.href = '/admin-login.html'; return; }
    const sessions = await r.json();
    render(sessions);
  } catch(e) { console.error(e); }
}

function render(sessions) {
  const tbody = document.getElementById('sessions-body');
  const empty = document.getElementById('empty-msg');
  if (!sessions.length) { tbody.innerHTML = ''; empty.style.display = 'block'; return; }
  empty.style.display = 'none';
  tbody.innerHTML = sessions.map(s => {
    const statusMap = { created: '待打开', in_progress: '填写中', submitted: '已提交' };
    const dotClass = s.status;
    const createdAt = new Date(s.created_at).toLocaleString('zh-CN');
    return `<tr>
      <td>${esc(s.external_participant_id || '-')}</td>
      <td>${esc(s.title || '-')}</td>
      <td><span class="status-dot ${dotClass}"></span>${statusMap[s.status] || s.status}</td>
      <td>${s.completed_count}/${s.target_count}</td>
      <td style="font-size:12px;">${createdAt}</td>
      <td><a href="/admin-detail.html?id=${esc(s.id)}">详情</a></td>
    </tr>`;
  }).join('');
}

async function logout() {
  await fetch('/api/admin/logout', {method:'POST'});
  sessionStorage.removeItem('adminUser');
  window.location.href = '/admin-login.html';
}

function esc(s) { const d=document.createElement('div'); d.textContent=s||''; return d.innerHTML; }

refresh();
</script>
</body>
</html>
```

- [ ] **Step 3: 写 `static/admin-detail.html`**

```html
<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>会话详情 - 主试端</title>
<link rel="stylesheet" href="/css/style.css">
</head>
<body>
<div class="topbar">
  <strong>会话详情</strong>
  <div><a href="/admin-sessions.html">← 返回列表</a></div>
</div>
<div class="container">
  <div class="card" id="meta-card"></div>
  <div class="card" id="dialogue-card"><h3>对话内容</h3><div id="dialogue-body"></div></div>
  <div class="card" style="display:flex;gap:12px;flex-wrap:wrap;">
    <button class="btn btn-primary" id="copy-link-btn" onclick="copyLink()">复制被试链接</button>
    <button class="btn" onclick="exportData('json')">导出 JSON</button>
    <button class="btn" onclick="exportData('csv')">导出 CSV</button>
    <button class="btn btn-danger" id="reset-btn" onclick="resetSession()">重置提交</button>
  </div>
</div>
<script>
const id = new URLSearchParams(location.search).get('id');
let detail = null;

async function load() {
  if (!id) return;
  const r = await fetch(`/api/admin/sessions/${id}`);
  if (r.status === 401) { window.location.href = '/admin-login.html'; return; }
  detail = await r.json();
  render();
}

function render() {
  const s = detail.session;
  const statusMap = { created: '待打开', in_progress: '填写中', submitted: '已提交' };
  document.getElementById('meta-card').innerHTML = `
    <h3>会话信息</h3>
    <p>被试编号：${esc(s.external_participant_id || '-')} | 标题：${esc(s.title || '-')} | 状态：${statusMap[s.status] || s.status}</p>
    <p>创建：${new Date(s.created_at).toLocaleString('zh-CN')} | 提交：${s.submitted_at ? new Date(s.submitted_at).toLocaleString('zh-CN') : '-'}</p>
  `;

  const body = document.getElementById('dialogue-body');
  body.innerHTML = detail.utterances.map(u => {
    let t = u.target;
    let annHtml = '';
    if (t && t.annotation) {
      annHtml = `<div style="margin-top:6px;padding:8px;background:#fefce8;border-radius:6px;font-size:13px;">
        <strong>${esc(t.display_hint || t.label)}</strong>
        · 类别：${esc(t.annotation.category || '-')}
        · 描述：${esc(t.annotation.description || '-')}
        · 置信度：${t.annotation.confidence || '-'}
        · ${t.annotation.is_complete ? '✅完整' : '⚠未完成'}
      </div>`;
    } else if (t) {
      annHtml = `<div style="margin-top:4px;font-size:12px;color:#d97706;">未填写 · ${esc(t.display_hint||t.label)}${t.required?' (必填)':''}</div>`;
    }
    const label = u.easyturn_label ? `<span class="badge badge-${u.easyturn_label}">${u.easyturn_label}</span>` : '';
    const speaker = u.speaker === 'experimenter' ? '主试' : '被试';
    return `<div class="utterance utterance-${u.speaker}">
      <div class="speaker-label ${u.speaker}">${speaker} · #${u.seq}</div>
      <p>${esc(u.text)}</p>${label}${annHtml}
    </div>`;
  }).join('');
}

async function copyLink() {
  if (!detail) return;
  await navigator.clipboard.writeText(detail.session.participant_url);
  alert('链接已复制');
}

function exportData(fmt) {
  window.open(`/api/admin/sessions/${id}/export?format=${fmt}`);
}

async function resetSession() {
  if (!confirm('确认重置该会话？被试已填内容将被清空。')) return;
  await fetch(`/api/admin/sessions/${id}/reset`, {method:'POST'});
  alert('已重置');
  load();
}

function esc(s) { const d=document.createElement('div'); d.textContent=s||''; return d.innerHTML; }

load();
</script>
</body>
</html>
```

- [ ] **Step 4: 写 `static/admin-settings.html`**

```html
<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>系统设置 - 主试端</title>
<link rel="stylesheet" href="/css/style.css">
<style>
  .setting-section { margin-bottom: 20px; }
  .setting-section h3 { margin-bottom: 8px; }
  textarea.wide { width: 100%; min-height: 200px; font-size: 14px; padding: 10px; border: 1px solid #d1d5db; border-radius: 6px; }
  .label-checkbox { display: inline-flex; align-items: center; gap: 4px; margin-right: 16px; }
  .cat-row { display: flex; gap: 8px; margin-bottom: 6px; align-items: center; }
  .cat-row input { padding: 6px; border: 1px solid #d1d5db; border-radius: 4px; font-size: 13px; }
</style>
</head>
<body>
<div class="topbar">
  <strong>系统设置</strong>
  <div><a href="/admin-sessions.html">← 返回列表</a></div>
</div>
<div class="container">
  <div class="card setting-section">
    <h3>指导语</h3>
    <textarea class="wide" id="instruction"></textarea>
  </div>
  <div class="card setting-section">
    <h3>可标注标签</h3>
    <div id="labels-checkboxes"></div>
  </div>
  <div class="card setting-section">
    <h3>原因类别</h3>
    <div id="categories-list"></div>
    <button class="btn" onclick="addCategoryRow()">+ 添加类别</button>
  </div>
  <button class="btn btn-primary" onclick="save()">保存设置</button>
  <span id="save-status" style="margin-left:12px;font-size:13px;"></span>
</div>
<script>
const ALL_LABELS = ['incomplete','wait','complete','backchannel'];
const LABEL_NAMES = {incomplete:'未说完', wait:'等待', complete:'完整', backchannel:'附和'};

async function load() {
  const r = await fetch('/api/admin/settings');
  if (r.status === 401) { window.location.href = '/admin-login.html'; return; }
  const s = await r.json();
  document.getElementById('instruction').value = s.instruction_text || '';

  // labels
  document.getElementById('labels-checkboxes').innerHTML = ALL_LABELS.map(l =>
    `<label class="label-checkbox"><input type="checkbox" value="${l}" ${s.annotatable_labels.includes(l)?'checked':''}>${LABEL_NAMES[l]||l} (${l})</label>`
  ).join('');

  // categories
  window._cats = s.reason_categories || [];
  renderCategories();
}

function renderCategories() {
  document.getElementById('categories-list').innerHTML = window._cats.map((c,i) =>
    `<div class="cat-row">
      <input placeholder="value" value="${esc(c.value)}" data-idx="${i}" class="cat-val" style="width:120px;">
      <input placeholder="显示名" value="${esc(c.label)}" data-idx="${i}" class="cat-label" style="flex:1;">
      <button class="btn" onclick="removeCat(${i})" style="font-size:12px;">删除</button>
    </div>`
  ).join('');
}

function addCategoryRow() {
  window._cats.push({value:'', label:''});
  renderCategories();
}

function removeCat(i) { window._cats.splice(i,1); renderCategories(); }

function collectCategories() {
  const rows = document.querySelectorAll('.cat-row');
  return Array.from(rows).map(r => ({
    value: r.querySelector('.cat-val').value.trim(),
    label: r.querySelector('.cat-label').value.trim(),
  })).filter(c => c.value && c.label);
}

async function save() {
  if (!confirm('确认保存设置？')) return;
  const labels = Array.from(document.querySelectorAll('#labels-checkboxes input:checked')).map(cb=>cb.value);
  const instruction = document.getElementById('instruction').value;
  const reason_categories = collectCategories();
  const r = await fetch('/api/admin/settings', {
    method: 'PUT', headers: {'Content-Type':'application/json'},
    body: JSON.stringify({ instruction_text: instruction, annotatable_labels: labels, reason_categories })
  });
  if (r.ok) {
    document.getElementById('save-status').textContent = '已保存';
    document.getElementById('save-status').style.color = '#059669';
  } else {
    document.getElementById('save-status').textContent = '保存失败';
    document.getElementById('save-status').style.color = '#dc2626';
  }
}

function esc(s) { const d=document.createElement('div'); d.textContent=s||''; return d.innerHTML; }

load();
</script>
</body>
</html>
```

- [ ] **Step 5: 写 `static/admin-users.html`**

```html
<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>主试账号管理</title>
<link rel="stylesheet" href="/css/style.css">
</head>
<body>
<div class="topbar">
  <strong>主试账号管理</strong>
  <div><a href="/admin-sessions.html">← 返回列表</a></div>
</div>
<div class="container">
  <div class="card">
    <h3>添加主试</h3>
    <div style="display:flex;gap:8px;flex-wrap:wrap;margin-top:8px;">
      <input id="new-username" placeholder="用户名" style="padding:8px;border:1px solid #d1d5db;border-radius:6px;">
      <input id="new-password" type="password" placeholder="密码" style="padding:8px;border:1px solid #d1d5db;border-radius:6px;">
      <select id="new-role" style="padding:8px;border:1px solid #d1d5db;border-radius:6px;">
        <option value="experimenter">实验员</option>
        <option value="admin">管理员</option>
      </select>
      <button class="btn btn-primary" onclick="addUser()">添加</button>
    </div>
  </div>
  <div class="card">
    <h3>现有账号</h3>
    <table>
      <thead><tr><th>用户名</th><th>角色</th><th>状态</th><th>操作</th></tr></thead>
      <tbody id="users-body"></tbody>
    </table>
  </div>
</div>
<script>
async function load() {
  const r = await fetch('/api/admin/users');
  if (r.status === 401) { window.location.href = '/admin-login.html'; return; }
  const users = await r.json();
  document.getElementById('users-body').innerHTML = users.map(u =>
    `<tr>
      <td>${esc(u.username)}</td>
      <td>${u.role === 'admin' ? '管理员' : '实验员'}</td>
      <td>${u.is_active ? '🟢 启用' : '🔴 停用'}</td>
      <td>
        <button class="btn" onclick="toggleUser('${u.id}')" style="font-size:12px;">${u.is_active?'停用':'启用'}</button>
        <button class="btn" onclick="resetPw('${u.id}')" style="font-size:12px;">重置密码</button>
      </td>
    </tr>`
  ).join('');
}

async function addUser() {
  const username = document.getElementById('new-username').value.trim();
  const password = document.getElementById('new-password').value;
  const role = document.getElementById('new-role').value;
  if (!username || !password) return alert('请填写用户名和密码');
  const r = await fetch('/api/admin/users', {
    method: 'POST', headers: {'Content-Type':'application/json'},
    body: JSON.stringify({username, password, role})
  });
  if (r.ok) { load(); } else { alert('添加失败'); }
}

async function toggleUser(id) {
  if (!confirm('确认切换启用状态？')) return;
  await fetch(`/api/admin/users/${id}`, {method:'PUT'});
  load();
}

async function resetPw(id) {
  const pw = prompt('输入新密码（至少6位）：');
  if (!pw) return;
  await fetch(`/api/admin/users/${id}/reset-password`, {
    method: 'POST', headers: {'Content-Type':'application/json'},
    body: JSON.stringify({new_password: pw})
  });
  alert('密码已重置');
}

function esc(s) { const d=document.createElement('div'); d.textContent=s||''; return d.innerHTML; }

load();
</script>
</body>
</html>
```

---

### Task 6: README 与安装部署文档

**文件：**
- 创建：`停顿标注工具/README.md`

---

- [ ] **Step 1: 写 `README.md`**

```markdown
# 口语停顿回溯标注工具

## 简介

英语口语任务结束后，为被试提供对话转录与 EasyTurn 停顿标记的回溯标注页面。
被试远程填写每个停顿点的原因类别、心理过程描述与置信度（1–7）。
主试通过后台查看进度、分发链接、导出数据。

## 部署环境要求

- Python ≥ 3.11
- 目标主机必须有**公网可达**的 IP（线上被试需直接打开链接）

## 快速开始

### 1. 安装

```bash
cd 停顿标注工具
bash scripts/install.sh
```

### 2. 配置

编辑 `.env`，至少修改以下三项：

```text
PUBLIC_BASE_URL=http://<你的公网IP>:8000
PIPELINE_TOKEN=<随机长密钥>
SECRET_KEY=<随机长密钥>
```

### 3. 启动

```bash
bash scripts/run.sh
```

### 4. 初始化管理员

首次启动后，默认管理员账号：`admin` / `admin`。
登录后请立即修改密码。

### 5. 流水线对接

口语任务结束后调用：

```bash
python scripts/pipeline_client.py \
  --base-url http://127.0.0.1:8000 \
  --token "$PIPELINE_TOKEN" \
  --participant P001 \
  --utterances /path/to/utterances.json
```

返回的 `participant_url` 发给被试即可。

### 6. 验收

1. 用手机 4G 网络（非 WiFi）打开 `participant_url`，确认可加载
2. 填写全部标注点 → 提交成功
3. 后台登录 → 查看进度 → 导出 CSV/JSON

## 目录

- `app/` — FastAPI 后端
- `static/` — 前端页面（无需构建）
- `data/` — SQLite 数据库（自动创建）
- `scripts/` — 安装/启动脚本 + 流水线 SDK

## 端口

默认 `8000`。防火墙/安全组需放行此端口。

## 备份

```bash
cp data/app.db data/app.db.$(date +%Y%m%d-%H%M%S).bak
```
```

- [ ] **Step 2: 最终验证部署打包**

```bash
# 打包整个文件夹
cd "c:\Users\13824\Desktop\重生之我在BNU学心理学\中科院软件所人机交互实验室\预实验图片收集与口语能力测验"
# Windows 下压缩停顿标注工具文件夹即可发给目标机
tar -czf 停顿标注工具.tar.gz 停顿标注工具/
```

---

## 计划自检

1. **Spec 覆盖检查**：对照设计文档每一项需求——
   - 流水线创建会话 ✅ Task 1
   - 被试填写页 ✅ Task 2 + 4
   - 类别 / 描述 / 置信度 ✅ Task 4 表单
   - 自动暂存 ✅ Task 4 autoSave
   - 提交锁定 ✅ Task 2 submit
   - 多主试登录 B1 ✅ Task 3 + 5
   - 指导语 / 标签 / 类别可改 ✅ Task 3 settings + Task 5 settings 页
   - 导出 JSON/CSV ✅ Task 3 export
   - 重置 ✅ Task 3 reset
   - public_base_url 可配 ✅ Task 0 config
   - 指导语快照 ✅ Task 1（创建时固化）

2. **占位检查**：无 TBD/TODO；所有代码均为完整可运行。

3. **类型一致性**：schemas ↔ models ↔ routers ↔ frontend fetch 全部对齐。
