import asyncio
import logging
import time
import uuid

from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.db import AsyncSessionLocal
from app.models import Job, Lead, LeadEmail, LeadContact, JobLead
from app.schemas.job import JobProgressEvent

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


async def run_pipeline(job_id: str) -> None:
    async with AsyncSessionLocal() as session:
        job = await session.get(Job, job_id)
        if not job or job.status == "cancelled":
            return
        job.status = "running"
        job.updated_at = int(time.time())
        await session.commit()

    config = {}
    async with AsyncSessionLocal() as session:
        job = await session.get(Job, job_id)
        config = job.config

    # Phase 1 — Google Places discovery
    await _phase_places(job_id, config)

    if await _is_cancelled(job_id):
        return

    # Phase 2 — Website scraping (if enabled)
    if config.get("enable_website_scraping", True):
        await _phase_scraping(job_id)

    if await _is_cancelled(job_id):
        return

    # Phase 3 — SERP enrichment (if enabled and key configured)
    from app.config import settings
    if config.get("enable_serp_enrichment") and settings.bing_search_api_key:
        await _phase_serp(job_id)

    async with AsyncSessionLocal() as session:
        job = await session.get(Job, job_id)
        if job and job.status != "cancelled":
            job.status = "completed"
            job.phase = "done"
            job.updated_at = int(time.time())
            await session.commit()
            await _broadcast(job)


async def _phase_places(job_id: str, config: dict) -> None:
    from app.services.places_service import search_places

    category = config.get("category", "")
    location = config.get("location", "")
    max_results = config.get("max_results", 50)

    async with AsyncSessionLocal() as session:
        job = await session.get(Job, job_id)
        job.phase = "places_discovery"
        job.updated_at = int(time.time())
        await session.commit()

    leads_found = 0
    total = 0
    places = []

    async for place in search_places(category, location, max_results):
        places.append(place)

    total = len(places)
    async with AsyncSessionLocal() as session:
        job = await session.get(Job, job_id)
        job.total_places = total
        job.updated_at = int(time.time())
        await session.commit()
        await _broadcast(job)

    for i, place in enumerate(places):
        if await _is_cancelled(job_id):
            return

        async with AsyncSessionLocal() as session:
            lead = await _upsert_lead(session, place)
            # Link job → lead
            existing = await session.execute(
                select(JobLead).where(JobLead.job_id == job_id, JobLead.lead_id == lead.id)
            )
            if not existing.scalar_one_or_none():
                session.add(JobLead(id=str(uuid.uuid4()), job_id=job_id, lead_id=lead.id))
                leads_found += 1
            await session.commit()

        async with AsyncSessionLocal() as session:
            job = await session.get(Job, job_id)
            job.processed_places = i + 1
            job.leads_found = leads_found
            job.updated_at = int(time.time())
            await session.commit()
            if (i + 1) % 5 == 0 or (i + 1) == total:
                await _broadcast(job)


async def _upsert_lead(session, place: dict) -> Lead:
    place_id = place.get("id")
    existing = None
    if place_id:
        result = await session.execute(select(Lead).where(Lead.place_id == place_id))
        existing = result.scalar_one_or_none()

    if existing:
        existing.phone = place.get("phone") or existing.phone
        existing.website = place.get("website") or existing.website
        existing.updated_at = int(time.time())
        return existing

    # Parse city/state from address
    address = place.get("address", "")
    city, state = _parse_city_state(address)

    lead = Lead(
        id=str(uuid.uuid4()),
        place_id=place_id,
        name=place.get("name", "Unknown"),
        address=address,
        city=city,
        state=state,
        phone=place.get("phone"),
        website=place.get("website"),
        place_types=place.get("types", []),
        source="google_places",
        created_at=int(time.time()),
        updated_at=int(time.time()),
    )
    session.add(lead)
    return lead


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
