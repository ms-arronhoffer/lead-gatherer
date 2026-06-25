import time
import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import current_user
from app.db import get_session
from app.models import Job, JobLead, Lead, User
from app.schemas.job import JobCreate, JobRead
from app.schemas.lead import LeadRead

router = APIRouter()


def _job_to_read(job: Job) -> JobRead:
    pct = 0.0
    if job.total_places > 0:
        pct = round(job.processed_places / job.total_places * 100, 1)
    return JobRead(
        id=job.id,
        status=job.status,
        phase=job.phase,
        config=job.config,
        total_places=job.total_places,
        processed_places=job.processed_places,
        leads_found=job.leads_found,
        error_message=job.error_message,
        created_at=job.created_at,
        updated_at=job.updated_at,
        progress_pct=pct,
        attempt=job.attempt,
        checkpoint=job.checkpoint or {},
    )


@router.post("", response_model=JobRead, status_code=201)
async def create_job(
    body: JobCreate,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(current_user),
):
    job = Job(
        id=str(uuid.uuid4()),
        status="pending",
        config=body.config.model_dump(),
        created_at=int(time.time()),
        updated_at=int(time.time()),
    )
    session.add(job)
    await session.commit()
    await session.refresh(job)

    from app.workers.arq_pool import enqueue_pipeline
    await enqueue_pipeline(job.id)

    return _job_to_read(job)


@router.get("", response_model=list[JobRead])
async def list_jobs(
    page: int = 1,
    page_size: int = 20,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(current_user),
):
    offset = (page - 1) * page_size
    result = await session.execute(
        select(Job).order_by(Job.created_at.desc()).offset(offset).limit(page_size)
    )
    return [_job_to_read(j) for j in result.scalars().all()]


@router.get("/{job_id}", response_model=JobRead)
async def get_job(
    job_id: str,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(current_user),
):
    job = await session.get(Job, job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return _job_to_read(job)


@router.delete("/{job_id}", status_code=204)
async def cancel_job(
    job_id: str,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(current_user),
):
    job = await session.get(Job, job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    if job.status in ("completed", "failed", "cancelled"):
        raise HTTPException(status_code=409, detail=f"Job already in terminal state: {job.status}")
    job.status = "cancelled"
    job.updated_at = int(time.time())
    await session.commit()

    # Abort the in-flight Arq task so blocking HTTP calls stop immediately
    from app.workers.arq_pool import abort_pipeline
    await abort_pipeline(job_id)


@router.post("/{job_id}/retry", response_model=JobRead)
async def retry_job(
    job_id: str,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(current_user),
):
    job = await session.get(Job, job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    if job.status not in ("failed", "cancelled"):
        raise HTTPException(
            status_code=409,
            detail=f"Only failed/cancelled jobs can be retried (current: {job.status})",
        )
    job.status = "pending"
    job.error_message = None
    job.updated_at = int(time.time())
    await session.commit()
    await session.refresh(job)

    from app.workers.arq_pool import enqueue_pipeline
    await enqueue_pipeline(job.id)

    return _job_to_read(job)


@router.get("/{job_id}/leads", response_model=list[LeadRead])
async def get_job_leads(
    job_id: str,
    page: int = 1,
    page_size: int = 50,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(current_user),
):
    job = await session.get(Job, job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    offset = (page - 1) * page_size
    result = await session.execute(
        select(Lead)
        .join(JobLead, JobLead.lead_id == Lead.id)
        .where(JobLead.job_id == job_id)
        .order_by(Lead.created_at.desc())
        .offset(offset)
        .limit(page_size)
    )
    from sqlalchemy.orm import selectinload
    result2 = await session.execute(
        select(Lead)
        .options(selectinload(Lead.emails), selectinload(Lead.contacts))
        .join(JobLead, JobLead.lead_id == Lead.id)
        .where(JobLead.job_id == job_id)
        .order_by(Lead.created_at.desc())
        .offset(offset)
        .limit(page_size)
    )
    return [LeadRead.model_validate(lead) for lead in result2.scalars().all()]
