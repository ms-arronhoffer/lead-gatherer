import json
import logging
import re
import time
import uuid
from urllib.parse import urljoin, urlparse

import httpx
from bs4 import BeautifulSoup
from sqlalchemy import select

from app.config import settings
from app.db import AsyncSessionLocal
from app.models import Lead, LeadEmail
from app.utils.email_extractor import extract_emails
from app.utils.rate_limiter import RateLimiter
from app.utils.robots import is_allowed

logger = logging.getLogger(__name__)

_CONTACT_KEYWORDS = ("/contact", "/about", "/team", "/staff", "/reach", "/people")
_rate_limiter = RateLimiter()

_HEADERS = {
    "User-Agent": "LeadGatherer/1.0 (contact discovery bot)",
    "Accept": "text/html,application/xhtml+xml",
}


async def scrape_lead(lead_id: str, website: str) -> None:
    domain = urlparse(website).netloc
    urls_to_visit = [website]
    visited: set[str] = set()
    all_emails: set[tuple[str, str, float]] = set()  # (email, source_type, confidence)

    async with httpx.AsyncClient(
        timeout=settings.request_timeout_seconds,
        follow_redirects=True,
        headers=_HEADERS,
    ) as client:
        for url in urls_to_visit[:1 + settings.max_contact_pages_per_site]:
            if url in visited:
                continue
            visited.add(url)

            await _rate_limiter.wait(domain)

            if settings.respect_robots_txt and not await is_allowed(url):
                continue

            try:
                resp = await client.get(url)
                resp.raise_for_status()
            except httpx.HTTPError as exc:
                logger.debug("HTTP error for %s: %s", url, exc)
                continue

            html = resp.text
            emails = extract_emails(html)
            for email, confidence in emails:
                all_emails.add((email, "website", confidence))

            # Find contact sub-pages from homepage only
            if url == website and len(visited) == 1:
                soup = BeautifulSoup(html, "lxml")
                for a in soup.find_all("a", href=True):
                    href = a["href"].lower()
                    if any(kw in href for kw in _CONTACT_KEYWORDS):
                        full_url = urljoin(website, a["href"])
                        if urlparse(full_url).netloc == domain and full_url not in visited:
                            urls_to_visit.append(full_url)

    if all_emails:
        await _save_emails(lead_id, list(all_emails))

    async with AsyncSessionLocal() as session:
        lead = await session.get(Lead, lead_id)
        if lead:
            lead.scraped_at = int(time.time())
            lead.updated_at = int(time.time())
            await session.commit()


async def _save_emails(lead_id: str, emails: list[tuple[str, str, float]]) -> None:
    async with AsyncSessionLocal() as session:
        for email, source, confidence in emails:
            normalized = email.lower().strip()
            existing = await session.execute(
                select(LeadEmail).where(
                    LeadEmail.lead_id == lead_id,
                    LeadEmail.email_normalized == normalized,
                )
            )
            if existing.scalar_one_or_none():
                continue
            session.add(LeadEmail(
                id=str(uuid.uuid4()),
                lead_id=lead_id,
                email=email,
                email_normalized=normalized,
                source=source,
                confidence=confidence,
                created_at=int(time.time()),
            ))
        await session.commit()
