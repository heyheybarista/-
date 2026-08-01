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

        # 为每个 <PAUSE> 创建标注目标（仅被试侧）
        if u.speaker == "participant":
            pauses = []
            if u.extra and isinstance(u.extra, dict):
                pauses = u.extra.get("pauses", [])
            for idx, pause_info in enumerate(pauses):
                duration_ms = int(pause_info.get("duration", 0) * 1000)
                level = pause_info.get("level", "unknown")
                target = AnnotationTarget(
                    id=_new_id(),
                    session_id=session.id,
                    utterance_id=utterance.id,
                    label="pause",
                    required=True,
                    display_hint=f"停顿 {pause_info.get('duration', 0):.2f}s ({level})",
                    pause_duration_ms=duration_ms,
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
