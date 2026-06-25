"""Brave Web Search API provider. Free tier requires an API key."""
from __future__ import annotations

import logging

import httpx

from app.config import settings
from app.services.search_providers.base import is_directory

logger = logging.getLogger(__name__)

_BRAVE_URL = "https://api.search.brave.com/res/v1/web/search"


class BraveSearchProvider:
    name = "brave"

    async def search(self, query: str, count: int) -> list[str]:
        if not settings.brave_search_api_key:
            raise RuntimeError("BRAVE_SEARCH_API_KEY not set")
        headers = {
            "Accept": "application/json",
            "X-Subscription-Token": settings.brave_search_api_key,
        }
        params = {"q": query, "count": min(count, 20), "country": "us", "result_filter": "web"}
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.get(_BRAVE_URL, params=params, headers=headers)
            if resp.status_code >= 400:
                logger.error("Brave API %s: %s", resp.status_code, resp.text[:500])
                return []
            data = resp.json()
        out: list[str] = []
        for r in data.get("web", {}).get("results", []):
            url = r.get("url") or ""
            if url and not is_directory(url):
                out.append(url)
        return out
