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

    # SMTP RCPT TO probe — envelope-from address used in MAIL FROM
    smtp_verify_sender: str = "verify@example.com"

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


settings = Settings()
