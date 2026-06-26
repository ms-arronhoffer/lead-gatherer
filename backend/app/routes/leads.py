import csv
import io
import time
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from sqlalchemy import String, select
from sqlalchemy.orm import selectinload
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import current_user
from app.db import get_session
from app.models import Lead, LeadActivity, LeadEmail, LeadSignal, JobLead, Tag, User
from app.schemas.lead import LeadAssign, LeadRead, LeadSignalRead, LeadUpdate
from app.schemas.user import LeadActivityRead
from app.services.scoring import score_lead
from app.services.webhook_dispatcher import enqueue_event
from app.utils.email_validator import validate_email
from app.utils.phone_normalizer import normalize_phone
from app.workers.arq_pool import enqueue_enrich

router = APIRouter()

VALID_STATUSES = {"new", "contacted", "qualified", "rejected"}
VALID_SORT = {"created_at", "name", "city", "state", "status", "updated_at", "last_touched_at", "score", "fit_score", "intent_score", "priority_score"}


def _build_query(
    status: str | None,
    city: str | None,
    state: str | None,
    has_email: bool | None,
    job_id: str | None,
    search: str | None,
    assigned_to: str | None,
    min_score: int | None,
    max_score: int | None,
    segment_id: str | None,
    sort_by: str,
    sort_dir: str,
):
    q = select(Lead).options(
        selectinload(Lead.emails),
        selectinload(Lead.contacts),
        selectinload(Lead.assignee),
        selectinload(Lead.last_touched_by),
        selectinload(Lead.tags),
    )
    if status:
        q = q.where(Lead.status == status)
    if city:
        q = q.where(Lead.city.ilike(f"%{city}%"))
    if state:
        q = q.where(Lead.state.ilike(f"%{state}%"))
    if job_id:
        q = q.join(JobLead, JobLead.lead_id == Lead.id).where(JobLead.job_id == job_id)
    if has_email is True:
        q = q.where(Lead.emails.any())
    elif has_email is False:
        q = q.where(~Lead.emails.any())
    if search:
        q = q.where(Lead.name.ilike(f"%{search}%"))
    if assigned_to == "unassigned":
        q = q.where(Lead.assigned_to_user_id.is_(None))
    elif assigned_to:
        q = q.where(Lead.assigned_to_user_id == assigned_to)
    if min_score is not None:
        q = q.where(Lead.score >= min_score)
    if max_score is not None:
        q = q.where(Lead.score <= max_score)
    if segment_id:
        # JSON containment varies by dialect; use string LIKE as a portable approximation
        q = q.where(Lead.matched_segment_ids.cast(String).like(f'%"{segment_id}"%'))
    col = getattr(Lead, sort_by if sort_by in VALID_SORT else "created_at")
    q = q.order_by(col.desc() if sort_dir == "desc" else col.asc())
    return q


def _touch(lead: Lead, user: User) -> None:
    now = int(time.time())
    lead.last_touched_at = now
    lead.last_touched_by_user_id = user.id
    lead.updated_at = now


def _log_activity(
    session: AsyncSession,
    *,
    lead_id: str,
    user_id: str | None,
    action: str,
    payload: dict,
) -> None:
    session.add(
        LeadActivity(
            id=str(uuid.uuid4()),
            lead_id=lead_id,
            user_id=user_id,
            action=action,
            payload=payload,
            created_at=int(time.time()),
        )
    )


@router.get("/signals/metrics", response_model=dict)
async def signal_metrics(
    session: AsyncSession = Depends(get_session),
    user: User = Depends(current_user),
):
    """Precision metrics per signal type: how many leads carry each signal type
    and what fraction of those have progressed to contacted/qualified. Lets the
    team see which buying signals actually predict pipeline."""
    rows = (await session.execute(
        select(LeadSignal.type, LeadSignal.lead_id, Lead.status)
        .join(Lead, Lead.id == LeadSignal.lead_id)
    )).all()

    # Count distinct leads per signal type and their statuses.
    by_type: dict[str, dict] = {}
    seen: set[tuple[str, str]] = set()
    for stype, lead_id, status in rows:
        if (stype, lead_id) in seen:
            continue
        seen.add((stype, lead_id))
        bucket = by_type.setdefault(stype, {"leads": 0, "contacted": 0, "qualified": 0})
        bucket["leads"] += 1
        if status in ("contacted", "qualified"):
            bucket["contacted"] += 1
        if status == "qualified":
            bucket["qualified"] += 1

    metrics = []
    for stype, b in sorted(by_type.items()):
        leads = b["leads"]
        metrics.append({
            "type": stype,
            "leads": leads,
            "contacted": b["contacted"],
            "qualified": b["qualified"],
            "qualified_rate": round(b["qualified"] / leads, 3) if leads else 0.0,
        })
    return {"signal_types": metrics}


@router.get("/export/csv")
async def export_leads_csv(
    status: str | None = Query(None),
    city: str | None = Query(None),
    state: str | None = Query(None),
    has_email: bool | None = Query(None),
    job_id: str | None = Query(None),
    search: str | None = Query(None),
    assigned_to: str | None = Query(None),
    min_score: int | None = Query(None),
    max_score: int | None = Query(None),
    segment_id: str | None = Query(None),
    session: AsyncSession = Depends(get_session),
    user: User = Depends(current_user),
):
    q = _build_query(status, city, state, has_email, job_id, search, assigned_to, min_score, max_score, segment_id, "created_at", "desc")
    result = await session.execute(q)
    leads = result.scalars().all()

    def _generate():
        buf = io.StringIO()
        writer = csv.DictWriter(buf, fieldnames=[
            "id", "name", "address", "city", "state", "phone", "website",
            "emails", "place_types", "employee_count_min", "employee_count_max",
            "revenue_range", "location_count", "status", "notes", "source", "created_at",
        ])
        writer.writeheader()
        yield buf.getvalue()
        buf.truncate(0)
        buf.seek(0)
        for lead in leads:
            writer.writerow({
                "id": lead.id,
                "name": lead.name,
                "address": lead.address or "",
                "city": lead.city or "",
                "state": lead.state or "",
                "phone": lead.phone or "",
                "website": lead.website or "",
                "emails": "; ".join(e.email for e in lead.emails),
                "place_types": ", ".join(lead.place_types),
                "employee_count_min": lead.employee_count_min or "",
                "employee_count_max": lead.employee_count_max or "",
                "revenue_range": lead.revenue_range or "",
                "location_count": lead.location_count or "",
                "status": lead.status,
                "notes": lead.notes or "",
                "source": lead.source,
                "created_at": lead.created_at,
            })
            yield buf.getvalue()
            buf.truncate(0)
            buf.seek(0)

    return StreamingResponse(
        _generate(),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=leads.csv"},
    )


@router.get("", response_model=dict)
async def list_leads(
    status: str | None = Query(None),
    city: str | None = Query(None),
    state: str | None = Query(None),
    has_email: bool | None = Query(None),
    job_id: str | None = Query(None),
    search: str | None = Query(None),
    assigned_to: str | None = Query(None),
    min_score: int | None = Query(None),
    max_score: int | None = Query(None),
    segment_id: str | None = Query(None),
    sort_by: str = Query("created_at"),
    sort_dir: str = Query("desc"),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    session: AsyncSession = Depends(get_session),
    user: User = Depends(current_user),
):
    q = _build_query(status, city, state, has_email, job_id, search, assigned_to, min_score, max_score, segment_id, sort_by, sort_dir)
    count_q = select(__import__("sqlalchemy").func.count()).select_from(q.subquery())
    total = (await session.execute(count_q)).scalar_one()
    offset = (page - 1) * page_size
    result = await session.execute(q.offset(offset).limit(page_size))
    leads = [LeadRead.model_validate(lead) for lead in result.scalars().all()]
    return {"total": total, "page": page, "page_size": page_size, "items": [l.model_dump() for l in leads]}


def _lead_query_with_relations(lead_id: str):
    return (
        select(Lead)
        .options(
            selectinload(Lead.emails),
            selectinload(Lead.contacts),
            selectinload(Lead.assignee),
            selectinload(Lead.last_touched_by),
            selectinload(Lead.tags),
        )
        .where(Lead.id == lead_id)
    )


@router.get("/{lead_id}", response_model=LeadRead)
async def get_lead(
    lead_id: str,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(current_user),
):
    result = await session.execute(_lead_query_with_relations(lead_id))
    lead = result.scalar_one_or_none()
    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found")
    return LeadRead.model_validate(lead)


@router.patch("/{lead_id}", response_model=LeadRead)
async def update_lead(
    lead_id: str,
    body: LeadUpdate,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(current_user),
):
    result = await session.execute(_lead_query_with_relations(lead_id))
    lead = result.scalar_one_or_none()
    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found")
    prev_status = lead.status
    prev_notes = lead.notes
    changed = False
    if body.status is not None and body.status != lead.status:
        if body.status not in VALID_STATUSES:
            raise HTTPException(status_code=422, detail=f"Invalid status. Must be one of: {VALID_STATUSES}")
        lead.status = body.status
        _log_activity(
            session,
            lead_id=lead.id,
            user_id=user.id,
            action="status_changed",
            payload={"from": prev_status, "to": body.status},
        )
        changed = True
    if body.notes is not None and body.notes != prev_notes:
        lead.notes = body.notes
        _log_activity(
            session,
            lead_id=lead.id,
            user_id=user.id,
            action="notes_updated",
            payload={"length": len(body.notes or "")},
        )
        changed = True
    firmographic_changes: dict = {}
    if body.employee_count_min is not None and body.employee_count_min != lead.employee_count_min:
        firmographic_changes["employee_count_min"] = body.employee_count_min
        lead.employee_count_min = body.employee_count_min
    if body.employee_count_max is not None and body.employee_count_max != lead.employee_count_max:
        firmographic_changes["employee_count_max"] = body.employee_count_max
        lead.employee_count_max = body.employee_count_max
    if body.revenue_range is not None and body.revenue_range != lead.revenue_range:
        firmographic_changes["revenue_range"] = body.revenue_range
        lead.revenue_range = body.revenue_range
    if firmographic_changes:
        _log_activity(
            session,
            lead_id=lead.id,
            user_id=user.id,
            action="firmographics_updated",
            payload=firmographic_changes,
        )
        changed = True
    profile_changes: dict = {}
    for field in ("name", "website", "phone", "address", "city", "state"):
        new_val = getattr(body, field)
        if new_val is not None and new_val != getattr(lead, field):
            profile_changes[field] = {"from": getattr(lead, field), "to": new_val}
            setattr(lead, field, new_val)
    if body.place_types is not None and list(body.place_types) != list(lead.place_types or []):
        profile_changes["place_types"] = {"from": lead.place_types, "to": body.place_types}
        lead.place_types = list(body.place_types)
    if profile_changes:
        _log_activity(
            session,
            lead_id=lead.id,
            user_id=user.id,
            action="profile_updated",
            payload={"fields": list(profile_changes.keys()), "changes": profile_changes},
        )
        changed = True
    if changed:
        _touch(lead, user)
        await score_lead(session, lead)
    await session.commit()
    await session.refresh(lead)
    out = LeadRead.model_validate(lead)
    payload = out.model_dump(mode="json")
    if body.status is not None and prev_status != lead.status:
        await enqueue_event("lead.status_changed", {
            "lead_id": lead.id,
            "previous_status": prev_status,
            "status": lead.status,
            "lead": payload,
        })
    if changed:
        await enqueue_event("lead.updated", {"lead_id": lead.id, "lead": payload})
    return out


@router.put("/{lead_id}/assign", response_model=LeadRead)
async def assign_lead(
    lead_id: str,
    body: LeadAssign,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(current_user),
):
    result = await session.execute(_lead_query_with_relations(lead_id))
    lead = result.scalar_one_or_none()
    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found")
    prev = lead.assigned_to_user_id
    new_id = body.user_id
    if new_id and new_id != prev:
        assignee = await session.get(User, new_id)
        if not assignee:
            raise HTTPException(status_code=404, detail="Assignee not found")
    if new_id != prev:
        lead.assigned_to_user_id = new_id
        _log_activity(
            session,
            lead_id=lead.id,
            user_id=user.id,
            action="assigned" if new_id else "unassigned",
            payload={"from": prev, "to": new_id},
        )
        _touch(lead, user)
        await score_lead(session, lead)
        await session.commit()
        await session.refresh(lead)
    out = LeadRead.model_validate(lead)
    await enqueue_event("lead.updated", {"lead_id": lead.id, "lead": out.model_dump(mode="json")})
    return out


@router.get("/{lead_id}/activities", response_model=list[LeadActivityRead])
async def list_lead_activities(
    lead_id: str,
    limit: int = Query(50, ge=1, le=200),
    session: AsyncSession = Depends(get_session),
    user: User = Depends(current_user),
):
    lead = await session.get(Lead, lead_id)
    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found")
    result = await session.execute(
        select(LeadActivity)
        .options(selectinload(LeadActivity.user))
        .where(LeadActivity.lead_id == lead_id)
        .order_by(LeadActivity.created_at.desc())
        .limit(limit)
    )
    return [LeadActivityRead.model_validate(a) for a in result.scalars().all()]


@router.get("/{lead_id}/signals", response_model=list[LeadSignalRead])
async def list_lead_signals(
    lead_id: str,
    limit: int = Query(100, ge=1, le=500),
    session: AsyncSession = Depends(get_session),
    user: User = Depends(current_user),
):
    lead = await session.get(Lead, lead_id)
    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found")
    result = await session.execute(
        select(LeadSignal)
        .where(LeadSignal.lead_id == lead_id)
        .order_by(LeadSignal.detected_at.desc())
        .limit(limit)
    )
    return [LeadSignalRead.model_validate(s) for s in result.scalars().all()]


@router.delete("/{lead_id}", status_code=204)
async def delete_lead(
    lead_id: str,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(current_user),
):
    lead = await session.get(Lead, lead_id)
    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found")
    await session.delete(lead)
    await session.commit()


@router.post("/{lead_id}/revalidate", response_model=LeadRead)
async def revalidate_lead(
    lead_id: str,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(current_user),
):
    result = await session.execute(_lead_query_with_relations(lead_id))
    lead = result.scalar_one_or_none()
    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found")

    if lead.phone:
        np = normalize_phone(lead.phone)
        lead.phone_normalized = np.e164
        lead.phone_type = np.type

    for em in lead.emails:
        v = await validate_email(em.email_normalized)
        em.mx_valid = v.mx_valid
        em.role_based = v.role_based
        em.disposable = v.disposable
        em.validated_at = v.validated_at

    _log_activity(
        session,
        lead_id=lead.id,
        user_id=user.id,
        action="revalidated",
        payload={"emails": len(lead.emails)},
    )
    _touch(lead, user)
    await score_lead(session, lead)
    await session.commit()
    await session.refresh(lead)
    return LeadRead.model_validate(lead)


@router.post("/{lead_id}/enrich", status_code=202)
async def enrich_lead(
    lead_id: str,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(current_user),
):
    """Queue an ad-hoc re-enrichment: re-scrape website, regenerate LLM brief,
    re-extract contacts, re-verify emails, rescore + refresh fit reasons."""
    lead = await session.get(Lead, lead_id)
    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found")
    if not lead.website:
        raise HTTPException(status_code=400, detail="Lead has no website to scrape")
    enqueued = await enqueue_enrich(lead_id)
    if not enqueued:
        return {"status": "already_running", "lead_id": lead_id}
    _log_activity(
        session,
        lead_id=lead.id,
        user_id=user.id,
        action="enrich_queued",
        payload={"website": lead.website},
    )
    _touch(lead, user)
    await session.commit()
    return {"status": "queued", "lead_id": lead_id}


@router.put("/{lead_id}/tags", response_model=LeadRead)
async def set_lead_tags(
    lead_id: str,
    body: dict,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(current_user),
):
    """Replace the lead's tag set. Body: {"tag_ids": [...]}"""
    raw_ids = body.get("tag_ids") or []
    if not isinstance(raw_ids, list):
        raise HTTPException(status_code=422, detail="tag_ids must be a list")
    tag_ids = [str(t) for t in raw_ids]

    result = await session.execute(_lead_query_with_relations(lead_id))
    lead = result.scalar_one_or_none()
    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found")

    before_ids = sorted(t.id for t in lead.tags)
    if tag_ids:
        rows = await session.execute(select(Tag).where(Tag.id.in_(tag_ids)))
        tags = list(rows.scalars().all())
        if len(tags) != len(set(tag_ids)):
            raise HTTPException(status_code=400, detail="One or more tag_ids are invalid")
    else:
        tags = []
    lead.tags = tags
    after_ids = sorted(t.id for t in tags)

    if before_ids != after_ids:
        added = sorted(set(after_ids) - set(before_ids))
        removed = sorted(set(before_ids) - set(after_ids))
        _log_activity(
            session,
            lead_id=lead.id,
            user_id=user.id,
            action="tags_updated",
            payload={"added": added, "removed": removed,
                     "tags": [{"id": t.id, "name": t.name} for t in tags]},
        )
        _touch(lead, user)
        await score_lead(session, lead)
        await session.commit()
        await session.refresh(lead)
    return LeadRead.model_validate(lead)
