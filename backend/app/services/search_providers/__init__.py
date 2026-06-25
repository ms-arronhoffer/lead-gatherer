"""Search provider factory. Selects implementation based on
`settings.search_provider` (brave | duckduckgo | searxng)."""
from __future__ import annotations

from app.config import settings
from app.services.search_providers.base import SearchProvider
from app.services.search_providers.brave import BraveSearchProvider
from app.services.search_providers.duckduckgo import DuckDuckGoSearchProvider
from app.services.search_providers.searxng import SearxngSearchProvider

_PROVIDERS: dict[str, type[SearchProvider]] = {
    "brave": BraveSearchProvider,
    "duckduckgo": DuckDuckGoSearchProvider,
    "searxng": SearxngSearchProvider,
}


def get_search_provider() -> SearchProvider:
    name = (settings.search_provider or "brave").lower()
    cls = _PROVIDERS.get(name)
    if cls is None:
        raise RuntimeError(
            f"Unknown SEARCH_PROVIDER '{name}'. Valid: {sorted(_PROVIDERS)}"
        )
    return cls()


__all__ = ["SearchProvider", "get_search_provider"]
