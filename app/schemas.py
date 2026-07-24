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
