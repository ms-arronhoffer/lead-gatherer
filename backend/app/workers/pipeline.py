import asyncio
import logging
import time
import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.db import AsyncSessionLocal
from app.models import Job, Lead, LeadEmail, LeadContact, JobLead
from app.schemas.job import JobProgressEvent
from app.utils.phone_normalizer import normalize_phone

logger = logging.getLogger(__name__)


async def _broadcast(job: Job) -> None:
    from app.routes.ws import manager
    pct = 0.0
    if job.total_places > 0:
        pct = round(job.processed_places / job.total_places * 100, 1)
    event = JobProgressEvent(
        job_id=job.id,
        status=job.status,
        phase=job.phase,
        processed_places=job.processed_places,
        total_places=job.total_places,
        leads_found=job.leads_found,
        progress_pct=pct,
    )
    await manager.broadcast(job.id, event.model_dump())


async def _is_cancelled(job_id: str) -> bool:
    async with AsyncSessionLocal() as session:
        job = await session.get(Job, job_id)
        return job is None or job.status == "cancelled"


async def _set_checkpoint(job_id: str, key: str, value: Any) -> None:
    async with AsyncSessionLocal() as session:
        job = await session.get(Job, job_id)
        if not job:
            return
        cp = dict(job.checkpoint or {})
        cp[key] = value
        job.checkpoint = cp
        job.updated_at = int(time.time())
        await session.commit()


async def _get_checkpoint(job_id: str) -> dict:
    async with AsyncSessionLocal() as session:
        job = await session.get(Job, job_id)
        return dict(job.checkpoint or {}) if job else {}


async def run_pipeline(job_id: str) -> None:
    async with AsyncSessionLocal() as session:
        job = await session.get(Job, job_id)
        if not job or job.status == "cancelled":
            return
        job.status = "running"
        job.attempt = (job.attempt or 0) + 1
        job.error_message = None
        job.updated_at = int(time.time())
        await session.commit()

    config = {}
    async with AsyncSessionLocal() as session:
        job = await session.get(Job, job_id)
        config = job.config

    checkpoint = await _get_checkpoint(job_id)

    # Phase 1 — Business discovery (one or more sources)
    if not checkpoint.get("discovery_done"):
        await _phase_discovery(job_id, config)
        await _set_checkpoint(job_id, "discovery_done", True)

    if await _is_cancelled(job_id):
        return

    # Phase 2 — Website scraping (if enabled)
    if config.get("enable_website_scraping", True) and not checkpoint.get("scraping_done"):
        await _phase_scraping(job_id)
        await _set_checkpoint(job_id, "scraping_done", True)

    if await _is_cancelled(job_id):
        return

    # Phase 3 — SERP enrichment (if enabled and key configured)
    from app.config import settings
    if (
        config.get("enable_serp_enrichment")
        and settings.bing_search_api_key
        and not checkpoint.get("serp_done")
    ):
        await _phase_serp(job_id)
        await _set_checkpoint(job_id, "serp_done", True)

    async with AsyncSessionLocal() as session:
        job = await session.get(Job, job_id)
        if job and job.status != "cancelled":
            job.status = "completed"
            job.phase = "done"
            job.updated_at = int(time.time())
            await session.commit()
            await _broadcast(job)


async def _phase_discovery(job_id: str, config: dict) -> None:
    from app.services.discovery import get_source

    category = config.get("category", "")
    location = config.get("location", "")
    max_results = config.get("max_results", 50)
    sources = config.get("sources") or ["google_places"]

    async with AsyncSessionLocal() as session:
        job = await session.get(Job, job_id)
        job.phase = "discovery"
        job.updated_at = int(time.time())
        await session.commit()

    # Collect across all sources, dedup by external_id then website domain
    collected: list[dict] = []
    seen_external: set[str] = set()
    seen_domain: set[str] = set()
    errors: list[str] = []

    for src_name in sources:
        if await _is_cancelled(job_id):
            return
        try:
            src = get_source(src_name)
        except ValueError as exc:
            errors.append(str(exc))
            continue

        async with AsyncSessionLocal() as session:
            job = await session.get(Job, job_id)
            job.phase = f"discovery:{src_name}"
            job.updated_at = int(time.time())
            await session.commit()
            await _broadcast(job)

        try:
            async for biz in src.search(category, location, max_results):
                key_ext = biz.external_id
                key_dom = _domain_of(biz.website)
                if key_ext and key_ext in seen_external:
                    continue
                if key_dom and key_dom in seen_domain:
                    continue
                if key_ext:
                    seen_external.add(key_ext)
                if key_dom:
                    seen_domain.add(key_dom)
                collected.append({
                    "id": biz.external_id,
                    "name": biz.name,
                    "address": biz.address or "",
                    "phone": biz.phone,
                    "website": biz.website,
                    "types": biz.types,
                    "source": biz.source,
                })
        except Exception as exc:
            logger.exception("Source %s failed: %s", src_name, exc)
            errors.append(f"{src_name}: {exc}")

    if not collected and errors:
        raise RuntimeError("; ".join(errors))

    total = len(collected)
    async with AsyncSessionLocal() as session:
        job = await session.get(Job, job_id)
        job.total_places = total
        job.updated_at = int(time.time())
        await session.commit()
        await _broadcast(job)

    leads_found = 0
    for i, place in enumerate(collected):
        if await _is_cancelled(job_id):
            return

        async with AsyncSessionLocal() as session:
            lead, created = await _upsert_lead(session, place)
            await session.flush()
            existing = await session.execute(
                select(JobLead).where(JobLead.job_id == job_id, JobLead.lead_id == lead.id)
            )
            if not existing.scalar_one_or_none():
                session.add(JobLead(id=str(uuid.uuid4()), job_id=job_id, lead_id=lead.id))
                leads_found += 1
            from app.services.scoring import score_lead
            # ensure relationships loaded for scoring
            await session.refresh(lead, attribute_names=["emails"])
            await score_lead(session, lead)
            lead_id = lead.id
            lead_name = lead.name
            await session.commit()

        if created:
            from app.services.webhook_dispatcher import enqueue_event
            await enqueue_event("lead.created", {"lead_id": lead_id, "name": lead_name})

        async with AsyncSessionLocal() as session:
            job = await session.get(Job, job_id)
            job.processed_places = i + 1
            job.leads_found = leads_found
            job.updated_at = int(time.time())
            await session.commit()
            if (i + 1) % 5 == 0 or (i + 1) == total:
                await _broadcast(job)


def _domain_of(website: str | None) -> str | None:
    if not website:
        return None
    from urllib.parse import urlparse
    host = urlparse(website).netloc.lower()
    if host.startswith("www."):
        host = host[4:]
    return host or None


async def _upsert_lead(session, place: dict) -> tuple[Lead, bool]:
    place_id = place.get("id")
    source = place.get("source", "google_places")
    existing = None
    if place_id:
        result = await session.execute(select(Lead).where(Lead.place_id == place_id))
        existing = result.scalar_one_or_none()

    if not existing:
        domain = _domain_of(place.get("website"))
        if domain:
            result = await session.execute(
                select(Lead).where(Lead.place_id == f"web:{domain}")
            )
            existing = result.scalar_one_or_none()
            if not existing and not place_id:
                place_id = f"web:{domain}"

    if existing:
        existing.phone = place.get("phone") or existing.phone
        if existing.phone and not existing.phone_normalized:
            np = normalize_phone(existing.phone)
            existing.phone_normalized = np.e164
            existing.phone_type = np.type
        existing.website = place.get("website") or existing.website
        existing.updated_at = int(time.time())
        return existing, False

    address = place.get("address", "")
    city, state = _parse_city_state(address)
    raw_phone = place.get("phone")
    np = normalize_phone(raw_phone)

    lead = Lead(
        id=str(uuid.uuid4()),
        place_id=place_id,
        name=place.get("name", "Unknown"),
        address=address,
        city=city,
        state=state,
        phone=raw_phone,
        phone_normalized=np.e164,
        phone_type=np.type,
        website=place.get("website"),
        place_types=place.get("types", []),
        source=source,
        created_at=int(time.time()),
        updated_at=int(time.time()),
    )
    session.add(lead)
    return lead, True


def _parse_city_state(address: str) -> tuple[str | None, str | None]:
    if not address:
        return None, None
    parts = [p.strip() for p in address.split(",")]
    # Typical US format: "Street, City, ST ZIP, Country"
    city = parts[1] if len(parts) > 1 else None
    state = None
    if len(parts) > 2:
        # "TX 78701" or "TX"
        state_part = parts[2].strip().split()[0]
        if len(state_part) == 2 and state_part.isalpha():
            state = state_part
    return city, state


async def _phase_scraping(job_id: str) -> None:
    from app.services.scraper_service import scrape_lead

    async with AsyncSessionLocal() as session:
        job = await session.get(Job, job_id)
        job.phase = "website_scraping"
        job.updated_at = int(time.time())
        await session.commit()
        await _broadcast(job)

    # Collect lead IDs that have websites
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(Lead.id, Lead.website)
            .join(JobLead, JobLead.lead_id == Lead.id)
            .where(JobLead.job_id == job_id, Lead.website.isnot(None))
        )
        leads_to_scrape = [(row.id, row.website) for row in result]

    from app.config import settings
    sem = asyncio.Semaphore(settings.max_concurrent_scrape_requests)

    async def scrape_one(lead_id: str, website: str) -> None:
        async with sem:
            if await _is_cancelled(job_id):
                return
            try:
                await scrape_lead(lead_id, website)
            except Exception as exc:
                logger.warning("Scraping failed for %s: %s", website, exc)

    await asyncio.gather(*[scrape_one(lid, url) for lid, url in leads_to_scrape])


async def _phase_serp(job_id: str) -> None:
    from app.services.serp_service import enrich_with_serp

    async with AsyncSessionLocal() as session:
        job = await session.get(Job, job_id)
        job.phase = "serp_enrichment"
        job.updated_at = int(time.time())
        await session.commit()
        await _broadcast(job)

    # Only enrich leads still missing emails
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(Lead)
            .options(selectinload(Lead.emails))
            .join(JobLead, JobLead.lead_id == Lead.id)
            .where(JobLead.job_id == job_id)
        )
        leads = [l for l in result.scalars().all() if not l.emails]

    calls = 0
    for lead in leads:
        if await _is_cancelled(job_id) or calls >= 1000:
            break
        try:
            await enrich_with_serp(lead.id, lead.name, lead.city or "")
            calls += 1
            await asyncio.sleep(1.0)
        except Exception as exc:
            logger.warning("SERP enrichment failed for %s: %s", lead.name, exc)
