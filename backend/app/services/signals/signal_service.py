"""Buying-signal layer.

A single reusable entry point — :func:`record_signal` — that any producer
(visitor pixel, news classifier, future web-monitoring jobs, manual entry) calls
to attach a first-class :class:`~app.models.LeadSignal` to a lead. Recording a
signal:

* dedupes on ``(lead_id, type, dedupe_key)`` so repeat detections are no-ops,
* re-runs scoring so the lead's ``intent_score`` / ``priority_score`` update,
* writes a ``signal_detected`` activity for the lead timeline,
* fires a ``signal.detected`` webhook, and a ``lead.hot`` webhook when the
  lead's ``priority_score`` first crosses ``settings.hot_lead_threshold``.
"""
from __future__ import annotations

import logging
import time
import uuid

from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.config import settings
from app.db import AsyncSessionLocal
from app.models import Lead, LeadActivity, LeadSignal

logger = logging.getLogger(__name__)


async def record_signal(
    lead_id: str,
    *,
    type: str,
    strength: int,
    source: str,
    payload: dict | None = None,
    dedupe_key: str | None = None,
    detected_at: int | None = None,
) -> str | None:
    """Attach a buying signal to a lead. Returns the new signal id, or ``None``
    if the lead is missing or the signal was deduped away."""
    now = detected_at if detected_at is not None else int(time.time())
    payload = payload or {}

    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(Lead)
            .options(
                selectinload(Lead.emails),
                selectinload(Lead.tags),
                selectinload(Lead.signals),
            )
            .where(Lead.id == lead_id)
        )
        lead = result.scalar_one_or_none()
        if lead is None:
            logger.debug("record_signal: lead %s not found", lead_id)
            return None

        # Dedupe repeat detections of the same underlying event.
        if dedupe_key is not None:
            for existing in lead.signals:
                if existing.type == type and existing.dedupe_key == dedupe_key:
                    return None

        prev_priority = lead.priority_score or 0

        signal = LeadSignal(
            id=str(uuid.uuid4()),
            lead_id=lead_id,
            type=type,
            strength=int(strength),
            source=source,
            dedupe_key=dedupe_key,
            payload=payload,
            detected_at=now,
        )
        session.add(signal)
        lead.signals.append(signal)

        # Rescore now that a new signal exists.
        from app.services.scoring import _assign_scores, _load_enabled_segments
        segments = await _load_enabled_segments(session)
        _assign_scores(lead, segments, list(lead.signals), now)
        new_priority = lead.priority_score or 0

        session.add(LeadActivity(
            id=str(uuid.uuid4()),
            lead_id=lead_id,
            user_id=None,
            action="signal_detected",
            payload={
                "type": type,
                "strength": int(strength),
                "source": source,
                "priority_score": new_priority,
            },
            created_at=now,
        ))

        await session.commit()

        signal_id = signal.id
        lead_name = lead.name

    became_hot = (
        prev_priority < settings.hot_lead_threshold
        and new_priority >= settings.hot_lead_threshold
    )

    # Fire webhooks after the transaction commits.
    from app.services.webhook_dispatcher import enqueue_event
    await enqueue_event("signal.detected", {
        "lead_id": lead_id,
        "name": lead_name,
        "signal": {
            "id": signal_id,
            "type": type,
            "strength": int(strength),
            "source": source,
            "detected_at": now,
            "payload": payload,
        },
        "priority_score": new_priority,
    })
    if became_hot:
        await enqueue_event("lead.hot", {
            "lead_id": lead_id,
            "name": lead_name,
            "priority_score": new_priority,
            "trigger": {"type": type, "source": source},
        })
        logger.info("Lead %s went hot (priority=%s) on %s signal", lead_id, new_priority, type)

    return signal_id
