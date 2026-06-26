from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    google_places_api_key: str = ""
    brave_search_api_key: str = ""
    bing_search_api_key: str = ""
    # Search provider for URL harvester: brave | duckduckgo | searxng
    search_provider: str = "brave"
    searxng_url: str = ""
    apollo_api_key: str = ""
    hunter_api_key: str = ""
    database_url: str = "sqlite+aiosqlite:////data/leadgen.db"
    redis_url: str = "redis://redis:6379/0"
    max_concurrent_scrape_requests: int = 5
    request_delay_seconds: float = 1.0
    request_timeout_seconds: int = 10
    respect_robots_txt: bool = True
    max_contact_pages_per_site: int = 3
    # Number of times to retry a transient HTTP error while scraping a page.
    scrape_max_retries: int = 2
    # Recent news / press-release enrichment (uses the configured search provider + LLM).
    enable_news_enrichment: bool = False
    max_news_articles: int = 3
    cors_origins: list[str] = ["http://localhost:3000"]
    log_level: str = "INFO"

    # Entra ID (Azure AD) authentication
    azure_tenant_id: str = ""
    azure_client_id: str = ""  # API app registration client ID (token audience)
    dev_bypass_auth: bool = False

    # Multi-provider LLM (one of: azure_openai, ollama, anthropic, google)
    llm_provider: str = "ollama"

    # Azure OpenAI
    azure_openai_endpoint: str = ""
    azure_openai_api_key: str = ""
    azure_openai_deployment: str = ""
    azure_openai_api_version: str = "2024-08-01-preview"

    # Ollama
    ollama_base_url: str = "http://ollama:11434"
    ollama_model: str = "llama3.1:8b"

    # Anthropic
    anthropic_api_key: str = ""
    anthropic_model: str = "claude-sonnet-4-5"

    # Google Gemini
    google_api_key: str = ""
    google_model: str = "gemini-3.1-flash-lite"

    # Microsoft Graph (delegated, uses caller's bearer token from the SPA)
    graph_base_url: str = "https://graph.microsoft.com/v1.0"

    # Visitor pixel
    pixel_origins: list[str] = ["*"]  # CORS for /api/v1/pixel/track — open by default
    ip2asn_db_path: str = "/data/IP2LOCATION-LITE-ASN.CSV"  # optional; resolver no-ops if missing

    # Sequence sender pacing
    sequence_send_batch: int = 50

    # ---- Lead scoring / buying-signal layer ----
    # Reachability gate: a lead can't exceed this fit_score without at least one
    # deliverable (mx_valid, non-role, non-disposable) email AND a normalized phone.
    fit_unreachable_cap: int = 79
    # priority = fit_weight*fit + intent_weight*intent (then freshness decay).
    priority_fit_weight: float = 0.6
    priority_intent_weight: float = 0.4
    # Freshness decay: priority multiplier reaches ~0.5 after this many days of
    # no activity (based on last_touched_at, falling back to created_at).
    freshness_half_life_days: int = 60
    # A lead is "hot" (fires lead.hot webhook) when priority_score >= this.
    hot_lead_threshold: int = 80
    # Recency half-life (days) for decaying an individual signal's strength.
    signal_half_life_days: int = 45

    # ---- Outcome-based segment-weight tuning ----
    # Minimum number of matched leads before a segment's weight is tuned.
    segment_tuning_min_samples: int = 5
    # Fraction of the way each tuning pass moves a weight toward its target.
    segment_tuning_learning_rate: float = 0.5
    # Bounds the tuned weight (a segment is never auto-dropped to 0).
    segment_tuning_min_weight: int = 10
    segment_tuning_max_weight: int = 100

    # SMTP RCPT TO probe — envelope-from address used in MAIL FROM
    smtp_verify_sender: str = "verify@example.com"

    # ---- LinkedIn headless-browser enrichment (off by default) ----
    # Automated LinkedIn login/scraping violates LinkedIn's Terms of Service and
    # can get accounts restricted. This whole feature is gated behind this flag.
    enable_linkedin_enrichment: bool = False
    # Service-account credentials used to log in. Prefer injecting via env/secret
    # store; never commit real values.
    linkedin_username: str = ""
    linkedin_password: str = ""
    # Where the authenticated browser storage state (cookies) is persisted so
    # subsequent runs can skip the login flow. Keep this path out of version
    # control. Empty disables persistence.
    linkedin_storage_state_path: str = "/data/linkedin_state.json"
    # Run the browser headless. Set false locally to solve a one-time challenge.
    linkedin_headless: bool = True
    # Conservative human-like pacing between LinkedIn page actions (seconds).
    linkedin_action_delay_seconds: float = 3.0
    # Per-operation navigation timeout (milliseconds).
    linkedin_nav_timeout_ms: int = 30000
    # Max decision-maker candidates to keep per company.
    linkedin_max_candidates: int = 5
    # How many profiles to inspect before ranking down to max_candidates.
    linkedin_max_profiles_scanned: int = 15
    # Max recent posts to scan for buying signals.
    linkedin_max_posts: int = 10
    # Title keywords that mark a person as a decision maker (case-insensitive
    # substring match). Override via LINKEDIN_DECISION_MAKER_TITLES.
    linkedin_decision_maker_titles: list[str] = [
        "ceo", "chief", "cfo", "coo", "cto", "cmo", "ciso", "cio",
        "owner", "founder", "co-founder", "president", "partner",
        "principal", "vp", "vice president", "head of", "director",
        "managing director", "general manager",
    ]

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


settings = Settings()
