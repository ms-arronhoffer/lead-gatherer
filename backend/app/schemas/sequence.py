"""F3 — sequences, enrollments, outbound messages."""
from pydantic import BaseModel, Field


class SequenceStep(BaseModel):
    day_offset: int = 0
    subject_template: str
    body_template: str
    requires_approval: bool = False


class SequenceRead(BaseModel):
    id: str
    name: str
    description: str | None
    steps: list[dict]
    owner_user_id: str | None
    enabled: bool
    created_at: int
    updated_at: int

    model_config = {"from_attributes": True}


class SequenceCreate(BaseModel):
    name: str
    description: str | None = None
    steps: list[SequenceStep] = Field(default_factory=list)
    enabled: bool = True


class SequenceUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    steps: list[SequenceStep] | None = None
    enabled: bool | None = None


class EnrollmentRead(BaseModel):
    id: str
    lead_id: str
    sequence_id: str
    enrolled_by_user_id: str
    step_idx: int
    status: str
    next_send_at: int | None
    started_at: int
    completed_at: int | None

    model_config = {"from_attributes": True}


class BulkEnrollRequest(BaseModel):
    sequence_id: str
    lead_ids: list[str]


class BulkEnrollResponse(BaseModel):
    enrolled: int
    skipped: int


class OutboundMessageRead(BaseModel):
    id: str
    enrollment_id: str
    lead_id: str
    user_id: str
    step_idx: int
    to_email: str
    subject: str
    body: str
    requires_approval: bool
    status: str
    sent_at: int | None
    graph_message_id: str | None
    graph_conversation_id: str | None
    reply_at: int | None
    bounce_at: int | None
    error: str | None
    created_at: int

    model_config = {"from_attributes": True}


class PreviewRequest(BaseModel):
    sequence_id: str
    lead_id: str
    step_idx: int = 0


class PreviewResponse(BaseModel):
    subject: str
    body: str
    opener: str
    to_email: str | None
