"""DuckDuckGo HTML scrape provider. No API key, but fragile to layout changes
and subject to rate-limiting / CAPTCHA if called aggressively."""
from __future__ import annotations

import logging
from urllib.parse import parse_qs, unquote, urlparse

import httpx
from bs4 import BeautifulSoup

from app.services.search_providers.base import is_directory

logger = logging.getLogger(__name__)

_DDG_URL = "https://html.duckduckgo.com/html/"


class DuckDuckGoSearchProvider:
    name = "duckduckgo"

    async def search(self, query: str, count: int) -> list[str]:
        headers = {
            "User-Agent": "Mozilla/5.0 (compatible; LeadGatherer/1.0)",
            "Accept": "text/html,application/xhtml+xml",
        }
        async with httpx.AsyncClient(timeout=30, follow_redirects=True) as client:
            try:
                resp = await client.post(_DDG_URL, data={"q": query}, headers=headers)
                resp.raise_for_status()
            except httpx.HTTPError as exc:
                logger.error("DuckDuckGo HTML fetch failed: %s", exc)
                return []
        soup = BeautifulSoup(resp.text, "lxml")
        out: list[str] = []
        for a in soup.select("a.result__a"):
            href = a.get("href") or ""
            url = _unwrap(href)
            if url and not is_directory(url):
                out.append(url)
            if len(out) >= count:
                break
        return out


def _unwrap(href: str) -> str:
    """DDG wraps result links as /l/?uddg=<encoded>. Unwrap if present."""
    if href.startswith("//"):
        href = "https:" + href
    parsed = urlparse(href)
    if parsed.path == "/l/" and parsed.query:
        qs = parse_qs(parsed.query)
        target = qs.get("uddg", [""])[0]
        if target:
            return unquote(target)
    return href if href.startswith("http") else ""
