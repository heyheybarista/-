import uuid
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.database import get_db
from app.models import Session, Utterance, AnnotationTarget, GlobalSetting
from app.schemas import CreateSessionRequest, CreateSessionResponse
from app.auth import verify_pipeline_token
from app.utils import generate_token, parse_easyturn, DEFAULT_ANNOTATABLE_LABELS, LABEL_HINTS, DEFAULT_INSTRUCTION

router = APIRouter()


def _new_id() -> str:
    return uuid.uuid4().hex[:12]


@router.post("/pipeline/sessions", response_model=CreateSessionResponse, dependencies=[Depends(verify_pipeline_token)])
async def create_session(req: CreateSessionRequest, db: AsyncSession = Depends(get_db)):
    # Request values override the global defaults; an empty list is intentional.
    setting_rows = (await db.execute(
        select(GlobalSetting).where(
            GlobalSetting.key.in_(["instruction_text", "annotatable_labels"])
        )
    )).scalars().all()
    settings = {row.key: row.value for row in setting_rows}
    annotatable = (
        req.annotatable_labels
        if req.annotatable_labels is not None
        else settings.get("annotatable_labels", DEFAULT_ANNOTATABLE_LABELS)
    )
    instruction = settings.get("instruction_text", DEFAULT_INSTRUCTION)

    session = Session(
        id=_new_id(),
        external_participant_id=req.external_participant_id,
        title=req.title,
        status="created",
        access_token=generate_token(),
        annotatable_labels=annotatable,
        pipeline_meta=req.pipeline_meta,
        instruction_snapshot=instruction,
    )
    db.add(session)

    target_count = 0
    for u in req.utterances:
        # 解析 EasyTurn 标签（若 raw_text 中有标签而 easyturn_label 未显式给出）
        label = u.easyturn_label
        text = u.text
        if u.raw_text and not label:
            parsed_text, parsed_label = parse_easyturn(u.raw_text)
            if parsed_label:
                text, label = parsed_text, parsed_label

        extra = dict(u.extra or {})
        pause_items = [
            pause.model_dump(exclude_none=True)
            for pause in (u.pauses or [])
        ]
        if not pause_items:
            legacy_pauses = extra.get("pauses", [])
            if isinstance(legacy_pauses, list):
                pause_items = [
                    item for item in legacy_pauses
                    if isinstance(item, dict)
                ]
        if pause_items:
            # Persist the canonical pause list even when it arrived through the
            # legacy extra.pauses field so exports remain self-contained.
            extra["pauses"] = pause_items

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
            extra=extra or None,
        )
        db.add(utterance)

        # Create one target for every pause. Legacy label-based payloads with
        # no pause list still get one target for backwards compatibility.
        if u.speaker == "participant" and pause_items:
            for idx, pause_info in enumerate(pause_items):
                if not isinstance(pause_info, dict):
                    continue
                try:
                    duration = float(pause_info.get("duration", 0))
                    if duration < 0:
                        continue
                    duration_ms = int(duration * 1000)
                    level = str(pause_info.get("level", "unknown"))
                    target = AnnotationTarget(
                        id=_new_id(),
                        session_id=session.id,
                        utterance_id=utterance.id,
                        target_index=idx,
                        label="pause",
                        required=True,
                        display_hint=f"停顿 {duration:.2f}s ({level})",
                        pause_duration_ms=duration_ms,
                    )
                    db.add(target)
                    target_count += 1
                except (ValueError, TypeError, KeyError):
                    continue  # 跳过格式错误的 pause
        elif (
            u.speaker == "participant"
            and label
            and label in annotatable
        ):
            db.add(AnnotationTarget(
                id=_new_id(),
                session_id=session.id,
                utterance_id=utterance.id,
                target_index=0,
                label=label,
                required=True,
                display_hint=LABEL_HINTS.get(label, label),
                pause_duration_ms=u.pause_duration_ms,
            ))
            target_count += 1

    await db.commit()

    from app.config import get_settings
    app_settings = get_settings()
    base = app_settings.public_base_url.rstrip("/")

    return CreateSessionResponse(
        session_id=session.id,
        access_token=session.access_token,
        participant_url=f"{base}/a/{session.access_token}",
        admin_url=f"{base}/admin-sessions.html",
        target_count=target_count,
        status=session.status,
    )
