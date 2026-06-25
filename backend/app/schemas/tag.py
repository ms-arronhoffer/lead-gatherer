from pydantic import BaseModel, Field


class TagCreate(BaseModel):
    name: str = Field(min_length=1, max_length=64)
    color: str | None = Field(default=None, max_length=16)


class TagUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=64)
    color: str | None = Field(default=None, max_length=16)


class TagDetail(BaseModel):
    id: str
    name: str
    color: str | None = None
    created_at: int
    updated_at: int
    lead_count: int = 0

    model_config = {"from_attributes": True}
