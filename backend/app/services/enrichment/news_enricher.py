"""Recent news / press-release enrichment.

Uses the configured search provider to surface recent press releases and news
mentioning a company, scrapes the top articles, and returns their text + HTML so
the caller can run the existing email + LLM contact extraction over them. This
discovers additional names and contacts (newly-appointed executives, spokespeople,
PR/media contacts) that are frequently absent from a company's own website.
"""
from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field

import httpx
from bs4 import BeautifulSoup

from app.config import settings
from app.services.search_providers import get_search_provider

logger = logging.getLogger(__name__)

# Signals that a search result is a recent announcement likely to name people.
_NEWS_TERMS = (
    "press release", "news", "announcement", "appoints", "appointed",
    "names", "hires", "promotes", "launches",
)

_HEADERS = {
    "User-Agent": "LeadGatherer/1.0 (news enrichment bot)",
    "Accept": "text/html,application/xhtml+xml",
}


@dataclass
class NewsArticle:
    url: str
    html: str
    text: str


@dataclass
class NewsResult:
    articles: list[NewsArticle] = field(default_factory=list)

    @property
    def combined_text(self) -> str:
        return " ".join(a.text for a in self.articles if a.text)


def build_news_query(company_name: str, location: str = "") -> str:
    """Build a search query biased toward recent announcements that name people."""
    company = (company_name or "").strip()
    query = f'"{company}" (press release OR news OR announcement OR appoints OR hires)'
    location = (location or "").strip()
    if location:
        query += f" {location}"
    return query


def search_configured() -> bool:
    try:
        get_search_provider()
        return True
    except Exception:
        return False


async def find_news(company_name: str, location: str = "", *, limit: int | None = None) -> NewsResult:
    """Search for recent news about a company and scrape the top articles.

    Returns an empty result (never raises) when no search provider is configured
    or every fetch fails, so callers can treat news enrichment as best-effort.
    """
    company = (company_name or "").strip()
    if not company:
        return NewsResult()
    if not search_configured():
        return NewsResult()

    max_articles = limit if limit is not None else settings.max_news_articles
    if max_articles <= 0:
        return NewsResult()

    provider = get_search_provider()
    query = build_news_query(company, location)
    try:
        urls = await provider.search(query, max_articles * 3)
    except Exception as exc:
        logger.warning("News search failed for %s: %s", company, exc)
        return NewsResult()

    # Dedup by host so we don't scrape three pages from the same outlet.
    selected: list[str] = []
    seen_hosts: set[str] = set()
    for url in urls:
        host = httpx.URL(url).host if url else ""
        if not host or host in seen_hosts:
            continue
        seen_hosts.add(host)
        selected.append(url)
        if len(selected) >= max_articles:
            break

    if not selected:
        return NewsResult()

    async with httpx.AsyncClient(
        timeout=settings.request_timeout_seconds,
        follow_redirects=True,
        headers=_HEADERS,
    ) as client:
        fetched = await asyncio.gather(
            *(_fetch_article(client, url) for url in selected)
        )

    articles = [a for a in fetched if a is not None]
    return NewsResult(articles=articles)


async def _fetch_article(client: httpx.AsyncClient, url: str) -> NewsArticle | None:
    try:
        resp = await client.get(url)
        resp.raise_for_status()
    except httpx.HTTPError as exc:
        logger.debug("News fetch error %s: %s", url, exc)
        return None
    html = resp.text
    soup = BeautifulSoup(html, "lxml")
    for tag in soup(["script", "style", "noscript"]):
        tag.decompose()
    text = soup.get_text(" ", strip=True)
    if not text:
        return None
    return NewsArticle(url=url, html=html, text=text[:8000])
