"""Orchestrator: enrich a lead's company profile from LinkedIn.

Wires together scraping (:mod:`company_search`), decision-maker ranking
(:mod:`decision_makers`), contact persistence, and post-derived buying signals
(:mod:`post_signals`). Designed to fail soft — any sub-step can degrade without
crashing the worker — and to be unit-testable by injecting a ``scraper``.
"""
from __future__ import annotations

import logging
import time
import uuid

from sqlalchemy import select

from app.config import settings
from app.db import AsyncSessionLocal
from app.models import Lead, LeadActivity, LeadContact
from app.services.enrichment.email_verifier import smtp_verify
from app.utils.email_validator import validate_email

from . import company_search, decision_makers, post_signals
from .browser_session import LinkedInError, is_configured

logger = logging.getLogger(__name__)


async def _persist_contacts(lead_id: str, contacts: list[dict]) -> int:
    """Upsert ranked decision makers as LinkedIn-sourced LeadContact rows.

    Dedupes on linkedin_url first, then (name, title). Any email present is
    syntax/MX/SMTP-verified via the existing verifier before being stored.
    Returns the number of new contacts inserted.
    """
    if not contacts:
        return 0
    now = int(time.time())
    inserted = 0
    async with AsyncSessionLocal() as session:
        existing_rows = (await session.execute(
            select(LeadContact).where(LeadContact.lead_id == lead_id)
        )).scalars().all()
        seen_urls = {c.linkedin_url for c in existing_rows if c.linkedin_url}
        seen_name_title = {(c.name, c.title) for c in existing_rows}

        for c in contacts:
            name = (c.get("name") or "").strip() or None
            title = (c.get("title") or "").strip() or None
            url = (c.get("profile_url") or "").strip() or None
            if not name:
                continue
            if url and url in seen_urls:
                continue
            if (name, title) in seen_name_title:
                continue

            email = (c.get("email") or "").strip().lower() or None
            if email:
                v = await validate_email(email)
                if not v.valid_syntax or not v.mx_valid or v.disposable:
                    email = None
                else:
                    try:
                        await smtp_verify(email)
                    except Exception as exc:  # noqa: BLE001 - verification best-effort
                        logger.debug("SMTP verify error %s: %s", email, exc)

            session.add(LeadContact(
                id=str(uuid.uuid4()),
                lead_id=lead_id,
                name=name,
                title=title,
                email=email,
                linkedin_url=url,
                seniority=(c.get("seniority") or "").strip() or None,
                source="linkedin",
                created_at=now,
            ))
            inserted += 1
            if url:
                seen_urls.add(url)
            seen_name_title.add((name, title))
        await session.commit()
    return inserted


async def _rescore_and_log(lead_id: str, stats: dict) -> None:
    from app.services.scoring import score_lead

    now = int(time.time())
    async with AsyncSessionLocal() as session:
        from sqlalchemy.orm import selectinload

        lead = (await session.execute(
            select(Lead).options(selectinload(Lead.emails)).where(Lead.id == lead_id)
        )).scalar_one_or_none()
        if lead is None:
            return
        lead.updated_at = now
        await score_lead(session, lead)
        session.add(LeadActivity(
            id=str(uuid.uuid4()),
            lead_id=lead_id,
            user_id=None,
            action="linkedin_enriched",
            payload=stats,
            created_at=now,
        ))
        await session.commit()


async def enrich_lead(lead_id: str, *, scraper=None) -> dict:
    """Run LinkedIn enrichment for a single lead.

    ``scraper`` is an awaitable ``(query) -> CompanyScrape`` used to override the
    live Playwright scrape in tests. Returns a stats dict.
    """
    stats = {"contacts_added": 0, "signals_recorded": 0, "profiles_scanned": 0}

    if not is_configured():
        logger.info("LinkedIn enrichment skipped for %s: not configured", lead_id)
        stats["skipped"] = "not_configured"
        return stats

    async with AsyncSessionLocal() as session:
        lead = await session.get(Lead, lead_id)
        if lead is None:
            stats["skipped"] = "lead_not_found"
            return stats
        company = lead.name
        icp_hint = lead.summary or ""

    if not company:
        stats["skipped"] = "no_company_name"
        return stats

    scrape_fn = scraper or company_search.scrape_company
    try:
        scrape = await scrape_fn(company)
    except LinkedInError as exc:
        logger.warning("LinkedIn enrichment aborted for %s: %s", company, exc)
        stats["error"] = str(exc)
        return stats
    except Exception as exc:  # noqa: BLE001 - never crash the worker
        logger.exception("LinkedIn scrape failed for %s: %s", company, exc)
        stats["error"] = "scrape_failed"
        return stats

    profile_dicts = [p.as_dict() for p in scrape.profiles]
    stats["profiles_scanned"] = len(profile_dicts)

    ranked = await decision_makers.normalize_and_rank(
        company,
        profile_dicts,
        max_candidates=settings.linkedin_max_candidates,
        icp_hint=icp_hint,
    )
    stats["contacts_added"] = await _persist_contacts(lead_id, ranked)

    post_dicts = [{"text": p.text, "url": p.url} for p in scrape.posts]
    if post_dicts:
        try:
            stats["signals_recorded"] = await post_signals.detect_and_record(
                lead_id, company, post_dicts
            )
        except Exception as exc:  # noqa: BLE001 - signals are best-effort
            logger.warning("LinkedIn post-signal step failed for %s: %s", company, exc)

    await _rescore_and_log(lead_id, dict(stats))
    return stats
