from pydantic import BaseModel, Field


class JobConfig(BaseModel):
    category: str
    location: str
    max_results: int = Field(default=50, ge=1, le=500)
    sources: list[str] = Field(default_factory=lambda: ["google_places"])
    employee_min: int | None = None
    employee_max: int | None = None
    revenue_range: str | None = None
    enable_website_scraping: bool = True
    enable_serp_enrichment: bool = False
    enable_news_enrichment: bool = False
    enable_apollo_enrichment: bool = False


class JobCreate(BaseModel):
    config: JobConfig


class JobRead(BaseModel):
    id: str
    status: str
    phase: str | None
    config: dict
    total_places: int
    processed_places: int
    leads_found: int
    error_message: str | None
    created_at: int
    updated_at: int
    progress_pct: float = 0.0
    attempt: int = 0
    checkpoint: dict = Field(default_factory=dict)

    model_config = {"from_attributes": True}


class JobProgressEvent(BaseModel):
    job_id: str
    status: str
    phase: str | None
    processed_places: int
    total_places: int
    leads_found: int
    progress_pct: float
