"""Candidate review and promotion routes (F4)."""
import logging
import time
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.auth import current_user
from app.db import get_session
from app.models import Lead, LeadCandidate, User
from app.schemas.candidate import (
    HarvestRequest, HarvestResponse, LeadCandidateCreate, LeadCandidateRead,
)
from app.schemas.lead import LeadRead

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("", response_model=dict)
async def list_candidates(
    status: str | None = Query(None),
    source: str | None = Query(None),
    min_fit: int | None = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    session: AsyncSession = Depends(get_session),
    user: User = Depends(current_user),
):
    q = select(LeadCandidate)
    if status:
        q = q.where(LeadCandidate.status == status)
    if source:
        q = q.where(LeadCandidate.source == source)
    if min_fit is not None:
        q = q.where(LeadCandidate.llm_fit_score >= min_fit)
    q = q.order_by(LeadCandidate.discovered_at.desc())

    from sqlalchemy import func
    total = (await session.execute(select(func.count()).select_from(q.subquery()))).scalar_one()
    offset = (page - 1) * page_size
    result = await session.execute(q.offset(offset).limit(page_size))
    items = [LeadCandidateRead.model_validate(c).model_dump() for c in result.scalars().all()]
    return {"total": total, "page": page, "page_size": page_size, "items": items}


@router.post("", response_model=LeadCandidateRead, status_code=201)
async def create_candidate(
    body: LeadCandidateCreate,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(current_user),
):
    cand = LeadCandidate(
        id=str(uuid.uuid4()),
        source=body.source,
        source_ref=body.source_ref,
        company_name=body.company_name,
        website=body.website,
        category=body.category,
        llm_summary=body.llm_summary,
        llm_fit_score=body.llm_fit_score,
        status="pending",
        discovered_at=int(time.time()),
    )
    session.add(cand)
    await session.commit()
    await session.refresh(cand)
    return LeadCandidateRead.model_validate(cand)


@router.post("/harvest", response_model=HarvestResponse)
async def harvest_urls(
    body: HarvestRequest,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(current_user),
):
    from urllib.parse import urlparse
    from app.services.discovery.url_harvester import UrlHarvesterSource

    # Pre-load existing Lead + url_harvester candidate domains so the LLM never
    # sees a page we've already ingested.
    lead_websites = (await session.execute(select(Lead.website).where(Lead.website.isnot(None)))).all()
    cand_websites = (await session.execute(
        select(LeadCandidate.website).where(
            LeadCandidate.source == "url_harvester",
            LeadCandidate.website.isnot(None),
        )
    )).all()
    skip_domains: set[str] = set()
    for (w,) in list(lead_websites) + list(cand_websites):
        host = urlparse(w or "").netloc.lower().removeprefix("www.")
        if host:
            skip_domains.add(host)

    src = UrlHarvesterSource()
    discovered = 0
    skipped = 0
    try:
        async for biz in src.search(body.query, "", body.max_results, skip_domains=skip_domains):
            existing = await session.execute(
                select(LeadCandidate).where(
                    LeadCandidate.source == "url_harvester",
                    LeadCandidate.source_ref == biz.external_id,
                )
            )
            if existing.scalar_one_or_none():
                skipped += 1
                continue
            session.add(LeadCandidate(
                id=str(uuid.uuid4()),
                source="url_harvester",
                source_ref=biz.external_id,
                company_name=biz.name,
                website=biz.website,
                category=biz.types[0] if biz.types else None,
                llm_summary=biz.llm_summary,
                llm_fit_score=biz.llm_fit_score,
                raw_payload={"query": body.query, "external_id": biz.external_id},
                status="pending",
                discovered_at=int(time.time()),
            ))
            discovered += 1
        await session.commit()
    except RuntimeError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return HarvestResponse(discovered=discovered, skipped=skipped)


@router.post("/{candidate_id}/promote", response_model=LeadRead)
async def promote_candidate(
    candidate_id: str,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(current_user),
):
    cand = await session.get(LeadCandidate, candidate_id)
    if not cand:
        raise HTTPException(status_code=404, detail="Candidate not found")
    if cand.status == "promoted" and cand.promoted_lead_id:
        result = await session.execute(
            select(Lead)
            .options(selectinload(Lead.emails), selectinload(Lead.contacts))
            .where(Lead.id == cand.promoted_lead_id)
        )
        existing = result.scalar_one_or_none()
        if existing:
            return LeadRead.model_validate(existing)

    now = int(time.time())
    lead = Lead(
        id=str(uuid.uuid4()),
        name=cand.company_name,
        website=cand.website,
        place_types=[cand.category] if cand.category else [],
        source=f"candidate:{cand.source}",
        status="new",
        created_at=now,
        updated_at=now,
    )
    session.add(lead)
    cand.status = "promoted"
    cand.promoted_lead_id = lead.id
    cand.reviewed_by_user_id = user.id
    cand.reviewed_at = now
    await session.commit()

    if lead.website:
        from app.services.scraper_service import scrape_lead
        try:
            await scrape_lead(lead.id, lead.website)
        except Exception as exc:
            logger.warning("Post-promote scrape failed for %s: %s", lead.id, exc)

    result = await session.execute(
        select(Lead)
        .options(selectinload(Lead.emails), selectinload(Lead.contacts),
                 selectinload(Lead.assignee), selectinload(Lead.last_touched_by))
        .where(Lead.id == lead.id)
    )
    return LeadRead.model_validate(result.scalar_one())


@router.post("/{candidate_id}/dismiss", response_model=LeadCandidateRead)
async def dismiss_candidate(
    candidate_id: str,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(current_user),
):
    cand = await session.get(LeadCandidate, candidate_id)
    if not cand:
        raise HTTPException(status_code=404, detail="Candidate not found")
    cand.status = "dismissed"
    cand.reviewed_by_user_id = user.id
    cand.reviewed_at = int(time.time())
    await session.commit()
    await session.refresh(cand)
    return LeadCandidateRead.model_validate(cand)


@router.delete("/{candidate_id}", status_code=204)
async def delete_candidate(
    candidate_id: str,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(current_user),
):
    cand = await session.get(LeadCandidate, candidate_id)
    if not cand:
        raise HTTPException(status_code=404, detail="Candidate not found")
    await session.delete(cand)
    await session.commit()
