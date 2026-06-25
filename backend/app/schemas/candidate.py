from pydantic import BaseModel


class LeadCandidateRead(BaseModel):
    id: str
    source: str
    source_ref: str | None
    company_name: str
    website: str | None
    category: str | None
    llm_summary: str | None
    llm_fit_score: int | None
    status: str
    discovered_at: int
    reviewed_at: int | None
    promoted_lead_id: str | None

    model_config = {"from_attributes": True}


class LeadCandidateCreate(BaseModel):
    source: str = "manual"
    source_ref: str | None = None
    company_name: str
    website: str | None = None
    category: str | None = None
    llm_summary: str | None = None
    llm_fit_score: int | None = None


class HarvestRequest(BaseModel):
    query: str
    max_results: int = 25


class HarvestResponse(BaseModel):
    discovered: int
    skipped: int
