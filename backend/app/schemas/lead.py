from pydantic import BaseModel


class LeadEmailRead(BaseModel):
    id: str
    email: str
    source: str
    confidence: float

    model_config = {"from_attributes": True}


class LeadContactRead(BaseModel):
    id: str
    name: str | None
    title: str | None
    phone: str | None
    email: str | None
    source: str

    model_config = {"from_attributes": True}


class LeadRead(BaseModel):
    id: str
    place_id: str | None
    name: str
    address: str | None
    city: str | None
    state: str | None
    phone: str | None
    website: str | None
    place_types: list[str]
    emails: list[LeadEmailRead] = []
    contacts: list[LeadContactRead] = []
    employee_count_min: int | None
    employee_count_max: int | None
    revenue_range: str | None
    location_count: int | None
    status: str
    notes: str | None
    source: str
    scraped_at: int | None
    created_at: int
    updated_at: int

    model_config = {"from_attributes": True}


class LeadUpdate(BaseModel):
    status: str | None = None
    notes: str | None = None
    employee_count_min: int | None = None
    employee_count_max: int | None = None
    revenue_range: str | None = None
