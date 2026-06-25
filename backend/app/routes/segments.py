import time
import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.auth import current_user
from app.db import get_session
from app.models import Lead, Segment, User
from app.schemas.segment import (
    SegmentCreate, SegmentPreview, SegmentRead, SegmentUpdate,
)
from app.services.scoring import rescore_all, segment_matches

router = APIRouter()


@router.get("", response_model=list[SegmentRead])
async def list_segments(
    session: AsyncSession = Depends(get_session),
    user: User = Depends(current_user),
):
    result = await session.execute(select(Segment).order_by(Segment.weight.desc(), Segment.name))
    return [SegmentRead.model_validate(s) for s in result.scalars().all()]


@router.post("", response_model=SegmentRead, status_code=201)
async def create_segment(
    body: SegmentCreate,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(current_user),
):
    now = int(time.time())
    seg = Segment(
        id=str(uuid.uuid4()),
        name=body.name,
        description=body.description,
        weight=body.weight,
        rules=body.rules,
        enabled=body.enabled,
        created_at=now,
        updated_at=now,
    )
    session.add(seg)
    await session.commit()
    await session.refresh(seg)
    await rescore_all(session)
    return SegmentRead.model_validate(seg)


@router.patch("/{segment_id}", response_model=SegmentRead)
async def update_segment(
    segment_id: str,
    body: SegmentUpdate,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(current_user),
):
    seg = await session.get(Segment, segment_id)
    if not seg:
        raise HTTPException(status_code=404, detail="Segment not found")
    data = body.model_dump(exclude_unset=True)
    for k, v in data.items():
        setattr(seg, k, v)
    seg.updated_at = int(time.time())
    await session.commit()
    await session.refresh(seg)
    await rescore_all(session)
    return SegmentRead.model_validate(seg)


@router.delete("/{segment_id}", status_code=204)
async def delete_segment(
    segment_id: str,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(current_user),
):
    seg = await session.get(Segment, segment_id)
    if not seg:
        raise HTTPException(status_code=404, detail="Segment not found")
    await session.delete(seg)
    await session.commit()
    await rescore_all(session)


@router.post("/preview", response_model=SegmentPreview)
async def preview_segment(
    body: SegmentCreate,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(current_user),
):
    """Evaluate the proposed rules against all leads — does not persist."""
    seg = Segment(
        id="preview", name=body.name, description=body.description,
        weight=body.weight, rules=body.rules, enabled=True,
        created_at=0, updated_at=0,
    )
    result = await session.execute(
        select(Lead).options(selectinload(Lead.emails), selectinload(Lead.tags))
    )
    leads = list(result.scalars().all())
    matches = sum(1 for l in leads if segment_matches(seg, l))
    return SegmentPreview(matches=matches, total=len(leads))


@router.post("/rescore", response_model=dict)
async def rescore_endpoint(
    session: AsyncSession = Depends(get_session),
    user: User = Depends(current_user),
):
    count = await rescore_all(session)
    return {"rescored": count}
