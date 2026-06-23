from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    google_places_api_key: str = ""
    bing_search_api_key: str = ""
    apollo_api_key: str = ""
    hunter_api_key: str = ""
    database_url: str = "sqlite+aiosqlite:////data/leadgen.db"
    max_concurrent_scrape_requests: int = 5
    request_delay_seconds: float = 1.0
    request_timeout_seconds: int = 10
    respect_robots_txt: bool = True
    max_contact_pages_per_site: int = 3
    cors_origins: list[str] = ["http://localhost:3000"]
    log_level: str = "INFO"

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


settings = Settings()
