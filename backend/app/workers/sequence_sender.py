"""Sequence sender (F3) — Arq cron.

Every minute: pick up to `settings.sequence_send_batch` enrollments whose
`next_send_at` has passed and whose status is `enrolled`. For each, render the
current step, personalize the opener via LLM, and either:
  - send immediately via Graph (using the user's cached Graph token), or
  - create an `OutboundMessage(status='awaiting_approval')` if the step is
    marked `requires_approval=true` — the user approves & sends from the UI.

If no Graph token is cached for the enrolling user, we stage the message as
`awaiting_approval` and rely on the user to send from the SPA. This is the
right failure mode for a $0-budget, team-scale tool.
"""
from __future__ import annotations

import logging
import time
import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.config import settings
from app.db import AsyncSessionLocal
from app.models import Lead, OutboundMessage, Sequence, SequenceEnrollment
from app.services.outreach import graph_mailer
from app.services.outreach.personalizer import personalize_opener, render_template

logger = logging.getLogger(__name__)


def _now() -> int:
    return int(time.time())


def _first_email(lead: Lead) -> str | None:
    if not lead.emails:
        return None
    pool = [e for e in lead.emails if not e.role_based and not e.disposable] or list(lead.emails)
    pool.sort(key=lambda e: ((e.smtp_verified is True) * 2 + (e.mx_valid is True), e.confidence), reverse=True)
    return pool[0].email if pool else None


async def task_send_sequence_batch(ctx: dict[str, Any]) -> None:
    now = _now()
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(SequenceEnrollment)
            .where(SequenceEnrollment.status == "enrolled")
            .where(SequenceEnrollment.next_send_at <= now)
            .order_by(SequenceEnrollment.next_send_at.asc())
            .limit(settings.sequence_send_batch)
        )
        enrollments = list(result.scalars().all())
        if not enrollments:
            return

        for enr in enrollments:
            seq = await session.get(Sequence, enr.sequence_id)
            if not seq or not seq.enabled or enr.step_idx >= len(seq.steps):
                enr.status = "completed"
                enr.completed_at = now
                enr.next_send_at = None
                continue

            lead = (await session.execute(
                select(Lead).options(selectinload(Lead.emails)).where(Lead.id == enr.lead_id)
            )).scalar_one_or_none()
            if not lead:
                enr.status = "failed"
                enr.next_send_at = None
                continue

            to_email = _first_email(lead)
            if not to_email:
                logger.info("Skip enrollment %s — no email on lead", enr.id)
                enr.status = "bounced"
                enr.next_send_at = None
                continue

            step = seq.steps[enr.step_idx]
            opener = await personalize_opener(lead, step.get("body_template", ""))
            subject = render_template(step.get("subject_template", ""), lead, opener)
            body_html = render_template(step.get("body_template", ""), lead, opener)
            requires_approval = bool(step.get("requires_approval", False))

            token = graph_mailer.get_cached_graph_token(enr.enrolled_by_user_id)
            msg = OutboundMessage(
                id=str(uuid.uuid4()),
                enrollment_id=enr.id,
                lead_id=enr.lead_id,
                user_id=enr.enrolled_by_user_id,
                step_idx=enr.step_idx,
                to_email=to_email,
                subject=subject,
                body=body_html,
                requires_approval=requires_approval,
                status="pending",
            )

            if requires_approval or not token:
                msg.status = "awaiting_approval"
                session.add(msg)
                continue

            try:
                graph_id, conv_id = await graph_mailer.send_mail(
                    token, to_email=to_email, subject=subject, body_html=body_html,
                )
                msg.status = "sent"
                msg.sent_at = _now()
                msg.graph_message_id = graph_id
                msg.graph_conversation_id = conv_id
            except graph_mailer.GraphMailError as exc:
                msg.status = "failed"
                msg.error = str(exc)[:1000]
                logger.warning("Graph send failed for enrollment %s: %s", enr.id, exc)
                session.add(msg)
                continue

            session.add(msg)
            next_idx = enr.step_idx + 1
            if next_idx < len(seq.steps):
                next_step = seq.steps[next_idx]
                enr.step_idx = next_idx
                enr.next_send_at = _now() + int(next_step.get("day_offset", 1)) * 86400
            else:
                enr.status = "completed"
                enr.completed_at = _now()
                enr.next_send_at = None

        await session.commit()
