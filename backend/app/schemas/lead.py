from pydantic import BaseModel

from app.schemas.user import UserRead


class LeadEmailRead(BaseModel):
    id: str
    email: str
    source: str
    confidence: float
    mx_valid: bool | None = None
    role_based: bool = False
    disposable: bool = False
    smtp_verified: bool | None = None
    validated_at: int | None = None

    model_config = {"from_attributes": True}


class LeadContactRead(BaseModel):
    id: str
    name: str | None
    title: str | None
    phone: str | None
    email: str | None
    source: str

    model_config = {"from_attributes": True}


class TagRead(BaseModel):
    id: str
    name: str
    color: str | None = None

    model_config = {"from_attributes": True}


class LeadRead(BaseModel):
    id: str
    place_id: str | None
    name: str
    address: str | None
    city: str | None
    state: str | None
    phone: str | None
    phone_normalized: str | None = None
    phone_type: str | None = None
    website: str | None
    place_types: list[str]
    emails: list[LeadEmailRead] = []
    contacts: list[LeadContactRead] = []
    tags: list[TagRead] = []
    employee_count_min: int | None
    employee_count_max: int | None
    revenue_range: str | None
    location_count: int | None
    status: str
    notes: str | None
    source: str
    scraped_at: int | None
    assigned_to_user_id: str | None = None
    assignee: UserRead | None = None
    last_touched_at: int | None = None
    last_touched_by_user_id: str | None = None
    last_touched_by: UserRead | None = None
    score: int | None = None
    matched_segment_ids: list[str] = []
    summary: str | None = None
    summary_generated_at: int | None = None
    fit_reasons: list[dict] = []
    fit_reasons_generated_at: int | None = None
    created_at: int
    updated_at: int

    model_config = {"from_attributes": True}


class LeadUpdate(BaseModel):
    status: str | None = None
    notes: str | None = None
    employee_count_min: int | None = None
    employee_count_max: int | None = None
    revenue_range: str | None = None
    name: str | None = None
    website: str | None = None
    phone: str | None = None
    address: str | None = None
    city: str | None = None
    state: str | None = None
    place_types: list[str] | None = None


class LeadAssign(BaseModel):
    user_id: str | None = None  # null = unassign
