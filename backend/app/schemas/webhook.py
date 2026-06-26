from pydantic import BaseModel, Field, HttpUrl

VALID_EVENTS = {"lead.created", "lead.updated", "lead.status_changed", "signal.detected", "lead.hot"}


class WebhookCreate(BaseModel):
    url: HttpUrl
    events: list[str] = Field(default_factory=lambda: list(VALID_EVENTS))
    enabled: bool = True
    description: str | None = None


class WebhookUpdate(BaseModel):
    url: HttpUrl | None = None
    events: list[str] | None = None
    enabled: bool | None = None
    description: str | None = None


class WebhookRead(BaseModel):
    id: str
    url: str
    secret: str
    events: list[str]
    enabled: bool
    description: str | None
    created_at: int
    updated_at: int

    model_config = {"from_attributes": True}


class WebhookDeliveryRead(BaseModel):
    id: str
    webhook_id: str
    event: str
    payload: dict
    status: str
    attempt: int
    status_code: int | None
    error: str | None
    next_retry_at: int | None
    delivered_at: int | None
    created_at: int

    model_config = {"from_attributes": True}
