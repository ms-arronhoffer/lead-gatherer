"""F3 — Sequences, enrollments, and outbound message routes.

Each user sends from their own mailbox via Microsoft Graph. The SPA acquires
a Graph-scoped token alongside the API token (via MSAL) and forwards it on
endpoints that send mail using the `X-Graph-Token` header.
"""
from __future__ import annotations

import logging
import time
import uuid

from fastapi import APIRouter, Depends, Header, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import current_user
from app.db import get_session
from app.models import Lead, LeadEmail, OutboundMessage, Sequence, SequenceEnrollment, User
from app.schemas.sequence import (
    BulkEnrollRequest, BulkEnrollResponse, EnrollmentRead, OutboundMessageRead,
    PreviewRequest, PreviewResponse, SequenceCreate, SequenceRead, SequenceUpdate,
)
from app.services.outreach import graph_mailer
from app.services.outreach.personalizer import personalize_opener, render_template

logger = logging.getLogger(__name__)
router = APIRouter()


def _now() -> int:
    return int(time.time())


@router.get("", response_model=list[SequenceRead])
async def list_sequences(
    session: AsyncSession = Depends(get_session),
    user: User = Depends(current_user),
):
    result = await session.execute(select(Sequence).order_by(Sequence.created_at.desc()))
    return [SequenceRead.model_validate(s) for s in result.scalars().all()]


@router.post("", response_model=SequenceRead, status_code=201)
async def create_sequence(
    body: SequenceCreate,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(current_user),
):
    seq = Sequence(
        id=str(uuid.uuid4()),
        name=body.name,
        description=body.description,
        steps=[s.model_dump() for s in body.steps],
        owner_user_id=user.id,
        enabled=body.enabled,
    )
    session.add(seq)
    await session.commit()
    await session.refresh(seq)
    return SequenceRead.model_validate(seq)


@router.get("/{sequence_id}", response_model=SequenceRead)
async def get_sequence(
    sequence_id: str,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(current_user),
):
    seq = await session.get(Sequence, sequence_id)
    if not seq:
        raise HTTPException(status_code=404, detail="Sequence not found")
    return SequenceRead.model_validate(seq)


@router.patch("/{sequence_id}", response_model=SequenceRead)
async def update_sequence(
    sequence_id: str,
    body: SequenceUpdate,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(current_user),
):
    seq = await session.get(Sequence, sequence_id)
    if not seq:
        raise HTTPException(status_code=404, detail="Sequence not found")
    if body.name is not None:
        seq.name = body.name
    if body.description is not None:
        seq.description = body.description
    if body.steps is not None:
        seq.steps = [s.model_dump() for s in body.steps]
    if body.enabled is not None:
        seq.enabled = body.enabled
    await session.commit()
    await session.refresh(seq)
    return SequenceRead.model_validate(seq)


@router.delete("/{sequence_id}", status_code=204)
async def delete_sequence(
    sequence_id: str,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(current_user),
):
    seq = await session.get(Sequence, sequence_id)
    if not seq:
        raise HTTPException(status_code=404, detail="Sequence not found")
    await session.delete(seq)
    await session.commit()


def _first_email_for(lead: Lead) -> LeadEmail | None:
    if not lead.emails:
        return None
    candidates = [e for e in lead.emails if not e.role_based and not e.disposable]
    if not candidates:
        candidates = list(lead.emails)
    candidates.sort(key=lambda e: ((e.smtp_verified is True) * 2 + (e.mx_valid is True), e.confidence), reverse=True)
    return candidates[0] if candidates else None


@router.post("/{sequence_id}/enroll", response_model=BulkEnrollResponse)
async def bulk_enroll(
    sequence_id: str,
    body: BulkEnrollRequest,
    x_graph_token: str | None = Header(default=None, alias="X-Graph-Token"),
    session: AsyncSession = Depends(get_session),
    user: User = Depends(current_user),
):
    if body.sequence_id != sequence_id:
        raise HTTPException(status_code=400, detail="sequence_id mismatch")
    seq = await session.get(Sequence, sequence_id)
    if not seq:
        raise HTTPException(status_code=404, detail="Sequence not found")
    if not seq.steps:
        raise HTTPException(status_code=400, detail="Sequence has no steps")

    graph_mailer.cache_graph_token(user.id, x_graph_token)

    enrolled = 0
    skipped = 0
    now = _now()
    first_step = seq.steps[0]
    first_offset_secs = int(first_step.get("day_offset", 0)) * 86400
    for lead_id in body.lead_ids:
        existing = await session.execute(
            select(SequenceEnrollment).where(
                SequenceEnrollment.lead_id == lead_id,
                SequenceEnrollment.sequence_id == sequence_id,
            )
        )
        if existing.scalar_one_or_none():
            skipped += 1
            continue
        session.add(SequenceEnrollment(
            id=str(uuid.uuid4()),
            lead_id=lead_id,
            sequence_id=sequence_id,
            enrolled_by_user_id=user.id,
            step_idx=0,
            status="enrolled",
            next_send_at=now + first_offset_secs,
            started_at=now,
        ))
        enrolled += 1
    await session.commit()
    return BulkEnrollResponse(enrolled=enrolled, skipped=skipped)


@router.get("/{sequence_id}/enrollments", response_model=list[EnrollmentRead])
async def list_enrollments(
    sequence_id: str,
    status: str | None = Query(None),
    session: AsyncSession = Depends(get_session),
    user: User = Depends(current_user),
):
    q = select(SequenceEnrollment).where(SequenceEnrollment.sequence_id == sequence_id)
    if status:
        q = q.where(SequenceEnrollment.status == status)
    q = q.order_by(SequenceEnrollment.started_at.desc())
    result = await session.execute(q)
    return [EnrollmentRead.model_validate(e) for e in result.scalars().all()]


@router.post("/preview", response_model=PreviewResponse)
async def preview(
    body: PreviewRequest,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(current_user),
):
    from sqlalchemy.orm import selectinload
    seq = await session.get(Sequence, body.sequence_id)
    if not seq:
        raise HTTPException(status_code=404, detail="Sequence not found")
    if body.step_idx < 0 or body.step_idx >= len(seq.steps):
        raise HTTPException(status_code=400, detail="step_idx out of range")
    lead = (await session.execute(
        select(Lead).options(selectinload(Lead.emails)).where(Lead.id == body.lead_id)
    )).scalar_one_or_none()
    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found")
    step = seq.steps[body.step_idx]
    opener = await personalize_opener(lead, step.get("body_template", ""))
    subject = render_template(step.get("subject_template", ""), lead, opener)
    body_text = render_template(step.get("body_template", ""), lead, opener)
    email = _first_email_for(lead)
    return PreviewResponse(
        subject=subject, body=body_text, opener=opener,
        to_email=email.email if email else None,
    )


@router.get("/outbound", response_model=list[OutboundMessageRead])
async def list_outbound(
    status: str | None = Query(None),
    requires_approval: bool | None = Query(None),
    limit: int = Query(100, ge=1, le=500),
    session: AsyncSession = Depends(get_session),
    user: User = Depends(current_user),
):
    q = select(OutboundMessage)
    if status:
        q = q.where(OutboundMessage.status == status)
    if requires_approval is not None:
        q = q.where(OutboundMessage.requires_approval == requires_approval)
    q = q.order_by(OutboundMessage.created_at.desc()).limit(limit)
    result = await session.execute(q)
    return [OutboundMessageRead.model_validate(m) for m in result.scalars().all()]


@router.post("/outbound/{message_id}/approve-send", response_model=OutboundMessageRead)
async def approve_and_send(
    message_id: str,
    x_graph_token: str | None = Header(default=None, alias="X-Graph-Token"),
    session: AsyncSession = Depends(get_session),
    user: User = Depends(current_user),
):
    msg = await session.get(OutboundMessage, message_id)
    if not msg:
        raise HTTPException(status_code=404, detail="Message not found")
    if msg.status not in ("pending", "awaiting_approval"):
        raise HTTPException(status_code=400, detail=f"Cannot send message in status={msg.status}")
    token = x_graph_token or graph_mailer.get_cached_graph_token(user.id)
    if not token:
        raise HTTPException(status_code=400, detail="X-Graph-Token header required")
    graph_mailer.cache_graph_token(user.id, token)
    try:
        graph_id, conv_id = await graph_mailer.send_mail(
            token,
            to_email=msg.to_email,
            subject=msg.subject,
            body_html=msg.body,
        )
    except graph_mailer.GraphMailError as exc:
        msg.status = "failed"
        msg.error = str(exc)[:1000]
        await session.commit()
        raise HTTPException(status_code=502, detail=str(exc))
    msg.status = "sent"
    msg.sent_at = _now()
    msg.graph_message_id = graph_id
    msg.graph_conversation_id = conv_id
    msg.error = None
    enrollment = await session.get(SequenceEnrollment, msg.enrollment_id)
    if enrollment:
        seq = await session.get(Sequence, enrollment.sequence_id)
        next_idx = enrollment.step_idx + 1
        if seq and next_idx < len(seq.steps):
            next_step = seq.steps[next_idx]
            enrollment.step_idx = next_idx
            enrollment.next_send_at = _now() + int(next_step.get("day_offset", 1)) * 86400
        else:
            enrollment.status = "completed"
            enrollment.completed_at = _now()
            enrollment.next_send_at = None
    await session.commit()
    await session.refresh(msg)
    return OutboundMessageRead.model_validate(msg)


@router.post("/graph-token", status_code=204)
async def cache_token(
    x_graph_token: str | None = Header(default=None, alias="X-Graph-Token"),
    user: User = Depends(current_user),
):
    """SPA hits this on load to make a fresh Graph token available to workers."""
    if x_graph_token:
        graph_mailer.cache_graph_token(user.id, x_graph_token)
