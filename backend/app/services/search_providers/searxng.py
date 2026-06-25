"""SearXNG meta-search provider. Self-hosted; no key. Configure SEARXNG_URL to
point at your instance's base URL (e.g. http://searxng:8080)."""
from __future__ import annotations

import logging

import httpx

from app.config import settings
from app.services.search_providers.base import is_directory

logger = logging.getLogger(__name__)


class SearxngSearchProvider:
    name = "searxng"

    async def search(self, query: str, count: int) -> list[str]:
        if not settings.searxng_url:
            raise RuntimeError("SEARXNG_URL not set")
        base = settings.searxng_url.rstrip("/")
        params = {"q": query, "format": "json", "safesearch": "0", "language": "en"}
        async with httpx.AsyncClient(timeout=30) as client:
            try:
                resp = await client.get(f"{base}/search", params=params)
                resp.raise_for_status()
            except httpx.HTTPError as exc:
                logger.error("SearXNG fetch failed: %s", exc)
                return []
            data = resp.json()
        out: list[str] = []
        for r in data.get("results", []):
            url = r.get("url") or ""
            if url and not is_directory(url):
                out.append(url)
            if len(out) >= count:
                break
        return out
