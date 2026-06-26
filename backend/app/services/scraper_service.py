import asyncio
import json
import logging
import re
import time
import uuid
from urllib.parse import urljoin, urlparse

import httpx
from bs4 import BeautifulSoup
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.config import settings
from app.db import AsyncSessionLocal
from app.models import Lead, LeadContact, LeadEmail, Segment
from app.services.enrichment.company_brief import generate_brief
from app.services.enrichment.email_verifier import smtp_verify
from app.services.enrichment.fit_explainer import explain_matches
from app.services.enrichment.llm_contact_extractor import extract_contacts
from app.services.enrichment.news_enricher import find_news
from app.utils.email_extractor import extract_emails
from app.utils.email_validator import validate_email
from app.utils.rate_limiter import RateLimiter
from app.utils.robots import is_allowed

logger = logging.getLogger(__name__)

_CONTACT_KEYWORDS = (
    "/contact", "/about", "/team", "/staff", "/reach", "/people",
    "/leadership", "/management", "/our-team", "/meet", "/board",
    "/founders", "/directors", "/who-we-are", "/company",
)
_rate_limiter = RateLimiter()

_HEADERS = {
    "User-Agent": "LeadGatherer/1.0 (contact discovery bot)",
    "Accept": "text/html,application/xhtml+xml",
}


async def _fetch(client: httpx.AsyncClient, url: str, domain: str) -> str | None:
    """Fetch a single URL, respecting robots/rate limits, with bounded retries.

    Returns the response body, or ``None`` if disallowed or unrecoverable.
    """
    if settings.respect_robots_txt and not await is_allowed(url):
        return None

    attempts = max(1, settings.scrape_max_retries + 1)
    for attempt in range(attempts):
        await _rate_limiter.wait(domain)
        try:
            resp = await client.get(url)
            resp.raise_for_status()
            return resp.text
        except httpx.HTTPStatusError as exc:
            # Retry only transient server-side / rate-limit responses.
            status = exc.response.status_code
            if status in (429, 500, 502, 503, 504) and attempt + 1 < attempts:
                continue
            logger.debug("HTTP %s for %s", status, url)
            return None
        except httpx.HTTPError as exc:
            if attempt + 1 < attempts:
                continue
            logger.debug("HTTP error for %s: %s", url, exc)
            return None
    return None


async def scrape_lead(lead_id: str, website: str, *, enable_news: bool = False) -> None:
    domain = urlparse(website).netloc
    all_emails: set[tuple[str, str, float]] = set()  # (email, source_type, confidence)
    aggregated_text: list[str] = []

    async with httpx.AsyncClient(
        timeout=settings.request_timeout_seconds,
        follow_redirects=True,
        headers=_HEADERS,
    ) as client:
        # Fetch the homepage first so we can discover contact-relevant sub-pages.
        home_html = await _fetch(client, website, domain)
        if home_html is not None:
            for email, confidence in extract_emails(home_html):
                all_emails.add((email, "website", confidence))
            soup = BeautifulSoup(home_html, "lxml")
            for tag in soup(["script", "style", "noscript"]):
                tag.decompose()
            aggregated_text.append(soup.get_text(" ", strip=True))

            sub_urls = _discover_contact_links(soup, website, domain)
            sub_urls = sub_urls[: settings.max_contact_pages_per_site]

            # Fetch contact sub-pages concurrently (each still rate-limited per domain).
            results = await asyncio.gather(
                *(_fetch(client, url, domain) for url in sub_urls)
            )
            for html in results:
                if html is None:
                    continue
                for email, confidence in extract_emails(html):
                    all_emails.add((email, "website", confidence))
                sub_soup = BeautifulSoup(html, "lxml")
                for tag in sub_soup(["script", "style", "noscript"]):
                    tag.decompose()
                aggregated_text.append(sub_soup.get_text(" ", strip=True))

    if all_emails:
        await _save_emails(lead_id, list(all_emails))

    # F2: LLM-driven contact extraction over the aggregated page text.
    page_text = " ".join(aggregated_text) if aggregated_text else ""
    if page_text:
        await _save_llm_contacts(lead_id, page_text)

    # Recent news / press-release enrichment: discover additional names & contacts.
    if enable_news:
        await _enrich_from_news(lead_id)

    # Company brief: short LLM summary of what the company does.
    brief = ""
    if page_text:
        async with AsyncSessionLocal() as session:
            lead_row = await session.get(Lead, lead_id)
            company = lead_row.name if lead_row else ""
        if company:
            brief = await generate_brief(company, page_text)

    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(Lead).options(selectinload(Lead.emails)).where(Lead.id == lead_id)
        )
        lead = result.scalar_one_or_none()
        if lead:
            now = int(time.time())
            lead.scraped_at = now
            lead.updated_at = now
            if brief:
                lead.summary = brief
                lead.summary_generated_at = now
            from app.services.scoring import score_lead
            await score_lead(session, lead)

            # Buyer-fit reasoning: one-sentence rationale per matched segment.
            matched_ids = list(lead.matched_segment_ids or [])
            if matched_ids:
                seg_rows = await session.execute(
                    select(Segment).where(Segment.id.in_(matched_ids))
                )
                matched_segments = list(seg_rows.scalars().all())
                reasons = await explain_matches(lead, matched_segments)
                if reasons:
                    lead.fit_reasons = reasons
                    lead.fit_reasons_generated_at = now
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
            v = await validate_email(normalized)
            smtp_ok: bool | None = None
            if v.mx_valid and v.valid_syntax and not v.disposable:
                try:
                    smtp_ok = await smtp_verify(normalized)
                except Exception as exc:
                    logger.debug("SMTP verify error %s: %s", normalized, exc)
            session.add(LeadEmail(
                id=str(uuid.uuid4()),
                lead_id=lead_id,
                email=email,
                email_normalized=normalized,
                source=source,
                confidence=confidence,
                mx_valid=v.mx_valid,
                role_based=v.role_based,
                disposable=v.disposable,
                smtp_verified=smtp_ok,
                validated_at=v.validated_at,
                created_at=int(time.time()),
            ))
        await session.commit()


async def _save_llm_contacts(lead_id: str, page_text: str, source: str = "llm") -> None:
    """Persist high-confidence LLM-extracted contacts (F2).

    Only contacts with confidence >= 0.7 AND a syntactically valid + MX-passing
    email are persisted. Emails are stored on LeadEmail; person metadata on
    LeadContact. ``source`` tags where the contact came from (e.g. "llm", "news").
    """
    async with AsyncSessionLocal() as session:
        lead_row = await session.get(Lead, lead_id)
        company = lead_row.name if lead_row else ""
    contacts = await extract_contacts(company, page_text)
    if not contacts:
        return

    async with AsyncSessionLocal() as session:
        for c in contacts:
            try:
                confidence = float(c.get("confidence", 0))
            except (TypeError, ValueError):
                continue
            if confidence < 0.7:
                continue
            email = (c.get("email") or "").strip().lower()
            name = (c.get("name") or "").strip() or None
            title = (c.get("title") or "").strip() or None
            if email:
                v = await validate_email(email)
                if not v.valid_syntax or not v.mx_valid or v.disposable:
                    continue
                existing = await session.execute(
                    select(LeadEmail).where(
                        LeadEmail.lead_id == lead_id,
                        LeadEmail.email_normalized == email,
                    )
                )
                if not existing.scalar_one_or_none():
                    smtp_ok: bool | None = None
                    try:
                        smtp_ok = await smtp_verify(email)
                    except Exception as exc:
                        logger.debug("SMTP verify error %s: %s", email, exc)
                    session.add(LeadEmail(
                        id=str(uuid.uuid4()),
                        lead_id=lead_id,
                        email=email,
                        email_normalized=email,
                        source=source,
                        confidence=confidence,
                        mx_valid=v.mx_valid,
                        role_based=v.role_based,
                        disposable=v.disposable,
                        smtp_verified=smtp_ok,
                        validated_at=v.validated_at,
                        created_at=int(time.time()),
                    ))
            if name or title:
                existing_c = await session.execute(
                    select(LeadContact).where(
                        LeadContact.lead_id == lead_id,
                        LeadContact.name == name,
                        LeadContact.title == title,
                    )
                )
                if not existing_c.scalar_one_or_none():
                    session.add(LeadContact(
                        id=str(uuid.uuid4()),
                        lead_id=lead_id,
                        name=name,
                        title=title,
                        email=email or None,
                        source=source,
                        created_at=int(time.time()),
                    ))
        await session.commit()


def _discover_contact_links(soup: BeautifulSoup, website: str, domain: str) -> list[str]:
    """Return on-domain URLs whose path looks like a contact/team/about page."""
    found: list[str] = []
    seen: set[str] = {website}
    for a in soup.find_all("a", href=True):
        href = a["href"].lower()
        if any(kw in href for kw in _CONTACT_KEYWORDS):
            full_url = urljoin(website, a["href"])
            if urlparse(full_url).netloc == domain and full_url not in seen:
                seen.add(full_url)
                found.append(full_url)
    return found


async def _enrich_from_news(lead_id: str) -> None:
    """Discover additional contacts from recent news / press releases."""
    async with AsyncSessionLocal() as session:
        lead_row = await session.get(Lead, lead_id)
        if not lead_row:
            return
        company = lead_row.name
        location = lead_row.city or lead_row.state or ""

    result = await find_news(company, location)
    if not result.articles:
        return

    # Emails surfaced directly in article HTML (e.g. media/PR contacts).
    news_emails: set[tuple[str, str, float]] = set()
    for article in result.articles:
        for email, confidence in extract_emails(article.html):
            news_emails.add((email, "news", confidence))
    if news_emails:
        await _save_emails(lead_id, list(news_emails))

    # Named people mentioned in the coverage, via the LLM extractor.
    combined = result.combined_text
    if combined:
        await _save_llm_contacts(lead_id, combined, source="news")

    # Buying-signal classification over the same coverage (funding, hires,
    # expansion, product launches, M&A, hiring, layoffs).
    if combined:
        from app.services.signals.news_signals import classify_news
        from app.services.signals.signal_service import record_signal
        try:
            for sig in await classify_news(company, combined):
                await record_signal(
                    lead_id,
                    type=sig["type"],
                    strength=sig["strength"],
                    source="news",
                    payload={
                        "evidence": sig["evidence"],
                        "confidence": sig["confidence"],
                        "article_urls": [a.url for a in result.articles],
                    },
                    dedupe_key=sig["type"],
                )
        except Exception as exc:  # noqa: BLE001
            logger.warning("News signal detection failed for %s: %s", company, exc)

