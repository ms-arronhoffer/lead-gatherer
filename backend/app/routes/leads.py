import csv
import io
import time

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.orm import selectinload
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_session
from app.models import Lead, LeadEmail, JobLead
from app.schemas.lead import LeadRead, LeadUpdate

router = APIRouter()

VALID_STATUSES = {"new", "contacted", "qualified", "rejected"}
VALID_SORT = {"created_at", "name", "city", "state", "status", "updated_at"}


def _build_query(
    status: str | None,
    city: str | None,
    state: str | None,
    has_email: bool | None,
    job_id: str | None,
    search: str | None,
    sort_by: str,
    sort_dir: str,
):
    q = select(Lead).options(selectinload(Lead.emails), selectinload(Lead.contacts))
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
    col = getattr(Lead, sort_by if sort_by in VALID_SORT else "created_at")
    q = q.order_by(col.desc() if sort_dir == "desc" else col.asc())
    return q


@router.get("/export/csv")
async def export_leads_csv(
    status: str | None = Query(None),
    city: str | None = Query(None),
    state: str | None = Query(None),
    has_email: bool | None = Query(None),
    job_id: str | None = Query(None),
    search: str | None = Query(None),
    session: AsyncSession = Depends(get_session),
):
    q = _build_query(status, city, state, has_email, job_id, search, "created_at", "desc")
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
    sort_by: str = Query("created_at"),
    sort_dir: str = Query("desc"),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    session: AsyncSession = Depends(get_session),
):
    q = _build_query(status, city, state, has_email, job_id, search, sort_by, sort_dir)
    count_q = select(__import__("sqlalchemy").func.count()).select_from(q.subquery())
    total = (await session.execute(count_q)).scalar_one()
    offset = (page - 1) * page_size
    result = await session.execute(q.offset(offset).limit(page_size))
    leads = [LeadRead.model_validate(lead) for lead in result.scalars().all()]
    return {"total": total, "page": page, "page_size": page_size, "items": [l.model_dump() for l in leads]}


@router.get("/{lead_id}", response_model=LeadRead)
async def get_lead(lead_id: str, session: AsyncSession = Depends(get_session)):
    result = await session.execute(
        select(Lead)
        .options(selectinload(Lead.emails), selectinload(Lead.contacts))
        .where(Lead.id == lead_id)
    )
    lead = result.scalar_one_or_none()
    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found")
    return LeadRead.model_validate(lead)


@router.patch("/{lead_id}", response_model=LeadRead)
async def update_lead(lead_id: str, body: LeadUpdate, session: AsyncSession = Depends(get_session)):
    result = await session.execute(
        select(Lead)
        .options(selectinload(Lead.emails), selectinload(Lead.contacts))
        .where(Lead.id == lead_id)
    )
    lead = result.scalar_one_or_none()
    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found")
    if body.status is not None:
        if body.status not in VALID_STATUSES:
            raise HTTPException(status_code=422, detail=f"Invalid status. Must be one of: {VALID_STATUSES}")
        lead.status = body.status
    if body.notes is not None:
        lead.notes = body.notes
    if body.employee_count_min is not None:
        lead.employee_count_min = body.employee_count_min
    if body.employee_count_max is not None:
        lead.employee_count_max = body.employee_count_max
    if body.revenue_range is not None:
        lead.revenue_range = body.revenue_range
    lead.updated_at = int(time.time())
    await session.commit()
    await session.refresh(lead)
    return LeadRead.model_validate(lead)


@router.delete("/{lead_id}", status_code=204)
async def delete_lead(lead_id: str, session: AsyncSession = Depends(get_session)):
    lead = await session.get(Lead, lead_id)
    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found")
    await session.delete(lead)
    await session.commit()
