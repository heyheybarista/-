from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from sqlalchemy import select
from app.database import get_db
from app.models import Session, Utterance, AnnotationTarget, Annotation
from app.schemas import ParticipantSessionOut, UtteranceOut, AnnotationTargetOut, PatchAnnotationRequest
from app.utils import LABEL_HINTS

router = APIRouter(tags=["participant"])


def _build_target_out(target: AnnotationTarget) -> dict:
    """Build the annotation target output dict (including the nested annotation if any)."""
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
    """Load a participant session by access token, returning utterances with annotation targets.

    First access transitions session status from "created" to "in_progress".
    """
    stmt = (
        select(Session)
        .where(Session.access_token == token)
        .options(
            selectinload(Session.utterances)
            .selectinload(Utterance.annotation_target)
            .selectinload(AnnotationTarget.annotation)
        )
    )
    result = await db.execute(stmt)
    session = result.scalar_one_or_none()
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    # First access transitions from "created" to "in_progress"
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
async def patch_annotation(
    token: str,
    target_id: str,
    body: PatchAnnotationRequest,
    db: AsyncSession = Depends(get_db),
):
    """Upsert a partial annotation for a target. Only the fields sent in the body are updated.

    Returns the updated completion status (is_complete = True when all three
    of category, description, and confidence have values).
    """
    # Find session by token
    stmt = select(Session).where(Session.access_token == token)
    result = await db.execute(stmt)
    session = result.scalar_one_or_none()
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    if session.status == "submitted":
        raise HTTPException(status_code=400, detail="Session already submitted")

    # Find target belonging to this session
    tgt_stmt = (
        select(AnnotationTarget)
        .where(
            AnnotationTarget.id == target_id,
            AnnotationTarget.session_id == session.id,
        )
        .options(selectinload(AnnotationTarget.annotation))
    )
    result = await db.execute(tgt_stmt)
    target = result.scalar_one_or_none()
    if not target:
        raise HTTPException(status_code=404, detail="Target not found")

    # Upsert annotation row
    if target.annotation:
        ann = target.annotation
    else:
        ann = Annotation(target_id=target.id)
        db.add(ann)

    # Apply only explicitly-provided fields (exclude_unset=True)
    updates = body.model_dump(exclude_unset=True)
    if "category" in updates:
        ann.category = updates["category"]
    if "description" in updates:
        ann.description = updates["description"]
    if "confidence" in updates:
        ann.confidence = updates["confidence"]

    # Recompute completion: True when all three fields have truthy values
    ann.is_complete = bool(ann.category and ann.description and ann.confidence)
    ann.updated_at = datetime.now(timezone.utc)

    await db.commit()
    await db.refresh(ann)
    return {"ok": True, "is_complete": ann.is_complete}


@router.post("/a/{token}/submit")
async def submit_session(token: str, db: AsyncSession = Depends(get_db)):
    """Submit a session after verifying all required targets have complete annotations.

    If any required target is missing a complete annotation, returns 400
    with a list of incomplete target_ids.
    """
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

    # Validate all required targets have complete annotations
    incomplete = []
    for t in session.annotation_targets:
        if t.required:
            ann = t.annotation
            if not ann or not ann.is_complete:
                incomplete.append({
                    "target_id": t.id,
                    "display_hint": t.display_hint or t.label,
                })

    if incomplete:
        raise HTTPException(
            status_code=400,
            detail={
                "message": "Not all required targets are complete",
                "incomplete": incomplete,
            },
        )

    session.status = "submitted"
    session.submitted_at = datetime.now(timezone.utc)
    await db.commit()
    return {"ok": True, "message": "Submitted"}
