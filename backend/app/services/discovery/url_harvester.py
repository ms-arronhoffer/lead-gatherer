"""URL harvester discovery source.

Takes a free-text query, runs the configured search provider, scrapes each
result, and feeds the page text to the configured LLM with a structured-output
schema to extract a candidate company. Yields `DiscoveredBusiness` entries that
the pipeline writes into `LeadCandidate` (not `Lead`) via a small adapter in
the routes.
"""
from __future__ import annotations

import logging
from typing import AsyncIterator
from urllib.parse import urlparse

import httpx
from bs4 import BeautifulSoup

from app.config import settings
from app.services import llm_client
from app.services.discovery.base import DiscoveredBusiness
from app.services.search_providers import get_search_provider

logger = logging.getLogger(__name__)

_CANDIDATE_SCHEMA = {
    "type": "object",
    "properties": {
        "company_name": {"type": "string"},
        "category": {"type": "string"},
        "summary": {"type": "string"},
        "fit_score": {"type": "integer", "minimum": 0, "maximum": 100},
        "is_company": {"type": "boolean"},
    },
    "required": ["company_name", "summary", "fit_score", "is_company"],
}


class UrlHarvesterSource:
    name = "url_harvester"

    async def search(
        self,
        category: str,
        location: str,
        max_results: int,
        skip_domains: set[str] | None = None,
    ) -> AsyncIterator[DiscoveredBusiness]:
        if not llm_client.is_configured():
            raise RuntimeError("LLM provider not configured (set LLM_PROVIDER + provider creds)")

        provider = get_search_provider()
        query = f"{category} {location}".strip()
        urls = await provider.search(query, max_results * 3)
        seen_domains: set[str] = set()
        skip = {d.lower().removeprefix("www.") for d in (skip_domains or set())}
        yielded = 0

        async with httpx.AsyncClient(
            timeout=settings.request_timeout_seconds,
            follow_redirects=True,
            headers={"User-Agent": "LeadGatherer/1.0 (candidate discovery)"},
        ) as client:
            for url in urls:
                if yielded >= max_results:
                    break
                domain = urlparse(url).netloc.lower().removeprefix("www.")
                if not domain or domain in seen_domains:
                    continue
                seen_domains.add(domain)
                if domain in skip:
                    logger.info("url_harvester skip %s — already known", domain)
                    continue

                page_text = await _fetch_text(client, url)
                if not page_text:
                    continue

                extracted = await _extract_company(query, url, page_text)
                if not extracted or not extracted.get("is_company"):
                    continue

                yield DiscoveredBusiness(
                    name=extracted.get("company_name") or domain,
                    source=self.name,
                    external_id=f"url:{domain}",
                    website=f"https://{domain}",
                    types=[extracted.get("category") or "unknown"],
                    llm_summary=extracted.get("summary"),
                    llm_fit_score=extracted.get("fit_score"),
                )
                yielded += 1


async def _fetch_text(client: httpx.AsyncClient, url: str) -> str:
    try:
        resp = await client.get(url)
        resp.raise_for_status()
    except httpx.HTTPError as exc:
        logger.debug("HTTP error %s: %s", url, exc)
        return ""
    soup = BeautifulSoup(resp.text, "lxml")
    for tag in soup(["script", "style", "noscript"]):
        tag.decompose()
    text = soup.get_text(" ", strip=True)
    return text[:8000]


async def _extract_company(query: str, url: str, page_text: str) -> dict | None:
    system = (
        "You are evaluating whether a web page belongs to a real company that matches "
        "a buyer's lead criteria. Output a single JSON object matching the schema. "
        "fit_score is 0-100; 100 is a perfect match for the buyer's query."
    )
    user = (
        f"Buyer query: {query}\nPage URL: {url}\n\nPage text:\n{page_text}\n\n"
        "Return ONLY the JSON object."
    )
    try:
        result = await llm_client.complete(
            [{"role": "system", "content": system}, {"role": "user", "content": user}],
            schema=_CANDIDATE_SCHEMA,
            max_tokens=400,
        )
    except Exception as exc:
        logger.warning("LLM extract failed for %s: %s", url, exc)
        return None
    if not isinstance(result, dict):
        return None
    return result
