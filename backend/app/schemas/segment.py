from typing import Any

from pydantic import BaseModel, Field


class SegmentBase(BaseModel):
    name: str
    description: str | None = None
    weight: int = Field(50, ge=0, le=100)
    rules: dict[str, Any] = {}
    enabled: bool = True


class SegmentCreate(SegmentBase):
    pass


class SegmentUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    weight: int | None = Field(None, ge=0, le=100)
    rules: dict[str, Any] | None = None
    enabled: bool | None = None


class SegmentRead(SegmentBase):
    id: str
    created_at: int
    updated_at: int

    model_config = {"from_attributes": True}


class SegmentPreview(BaseModel):
    matches: int
    total: int


class SegmentTuning(BaseModel):
    """Proposed weight adjustment for a single segment based on lead outcomes."""
    segment_id: str
    name: str
    matched: int
    contacted: int
    qualified: int
    conversion_rate: float
    current_weight: int
    proposed_weight: int
    delta: int
    sufficient_data: bool


class SegmentTuningApplied(BaseModel):
    applied: list[SegmentTuning]
    rescored: int
