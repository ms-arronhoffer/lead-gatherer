from pydantic import BaseModel


class UserRead(BaseModel):
    id: str
    email: str
    display_name: str | None = None

    model_config = {"from_attributes": True}


class LeadActivityRead(BaseModel):
    id: str
    lead_id: str
    user_id: str | None
    user: UserRead | None = None
    action: str
    payload: dict
    created_at: int

    model_config = {"from_attributes": True}
