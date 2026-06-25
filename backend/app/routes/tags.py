import time
import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import current_user
from app.db import get_session
from app.models import Lead, Tag, User, lead_tags
from app.schemas.lead import LeadRead, TagRead
from app.schemas.tag import TagCreate, TagDetail, TagUpdate

router = APIRouter()


@router.get("", response_model=list[TagDetail])
async def list_tags(
    session: AsyncSession = Depends(get_session),
    user: User = Depends(current_user),
):
    counts_subq = (
        select(lead_tags.c.tag_id, func.count(lead_tags.c.lead_id).label("n"))
        .group_by(lead_tags.c.tag_id)
        .subquery()
    )
    rows = await session.execute(
        select(Tag, counts_subq.c.n)
        .outerjoin(counts_subq, counts_subq.c.tag_id == Tag.id)
        .order_by(Tag.name)
    )
    out: list[TagDetail] = []
    for tag, n in rows.all():
        out.append(TagDetail(
            id=tag.id, name=tag.name, color=tag.color,
            created_at=tag.created_at, updated_at=tag.updated_at,
            lead_count=int(n or 0),
        ))
    return out


@router.post("", response_model=TagDetail, status_code=201)
async def create_tag(
    body: TagCreate,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(current_user),
):
    name = body.name.strip()
    existing = await session.execute(select(Tag).where(Tag.name == name))
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=409, detail="Tag with that name already exists")
    now = int(time.time())
    tag = Tag(id=str(uuid.uuid4()), name=name, color=body.color, created_at=now, updated_at=now)
    session.add(tag)
    await session.commit()
    await session.refresh(tag)
    return TagDetail(id=tag.id, name=tag.name, color=tag.color,
                     created_at=tag.created_at, updated_at=tag.updated_at, lead_count=0)


@router.patch("/{tag_id}", response_model=TagDetail)
async def update_tag(
    tag_id: str,
    body: TagUpdate,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(current_user),
):
    tag = await session.get(Tag, tag_id)
    if not tag:
        raise HTTPException(status_code=404, detail="Tag not found")
    data = body.model_dump(exclude_unset=True)
    if "name" in data and data["name"]:
        new_name = data["name"].strip()
        if new_name != tag.name:
            dupe = await session.execute(select(Tag).where(Tag.name == new_name, Tag.id != tag_id))
            if dupe.scalar_one_or_none():
                raise HTTPException(status_code=409, detail="Tag with that name already exists")
            tag.name = new_name
    if "color" in data:
        tag.color = data["color"]
    tag.updated_at = int(time.time())
    await session.commit()
    await session.refresh(tag)
    count_row = await session.execute(
        select(func.count()).select_from(lead_tags).where(lead_tags.c.tag_id == tag_id)
    )
    return TagDetail(id=tag.id, name=tag.name, color=tag.color,
                     created_at=tag.created_at, updated_at=tag.updated_at,
                     lead_count=int(count_row.scalar_one()))


@router.delete("/{tag_id}", status_code=204)
async def delete_tag(
    tag_id: str,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(current_user),
):
    tag = await session.get(Tag, tag_id)
    if not tag:
        raise HTTPException(status_code=404, detail="Tag not found")
    await session.delete(tag)
    await session.commit()
