import csv
import io
import uuid
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, Request, Query, Response
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from sqlalchemy import select, delete
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

router = APIRouter(tags=["admin"])


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
    s.opened_at = None
    await db.commit()
    return {"ok": True, "status": s.status}


@router.delete("/admin/sessions/{session_id}")
async def delete_session(
    session_id: str,
    db: AsyncSession = Depends(get_db),
    user: Experimenter = Depends(get_current_user),
):
    """永久删除一场会话及其话语、标注目标与填写内容。"""
    s = (await db.execute(select(Session).where(Session.id == session_id))).scalar_one_or_none()
    if not s:
        raise HTTPException(status_code=404, detail="Not found")

    targets = (await db.execute(
        select(AnnotationTarget).where(AnnotationTarget.session_id == session_id)
    )).scalars().all()
    for t in targets:
        await db.execute(delete(Annotation).where(Annotation.target_id == t.id))
    await db.execute(delete(AnnotationTarget).where(AnnotationTarget.session_id == session_id))
    await db.execute(delete(Utterance).where(Utterance.session_id == session_id))
    await db.execute(delete(Session).where(Session.id == session_id))
    await db.commit()
    return {"ok": True, "deleted": session_id}


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


# ── settings ──────────────────────────────────────────
# GET requires NO auth — the participant page needs to load reason_categories
@router.get("/admin/settings")
async def get_settings(db: AsyncSession = Depends(get_db)):
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
