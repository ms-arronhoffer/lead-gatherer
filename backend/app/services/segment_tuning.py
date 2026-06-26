"""Outcome-based segment-weight tuning.

Segments express the ICP — but how well each segment *actually* predicts a
closed/qualified lead is something we only learn from outcomes. This module
looks at the leads each segment matches and the fraction that have progressed
to ``qualified``, then nudges the segment's ``weight`` toward what the outcomes
justify.

The signal-precision metrics endpoint (``/leads/signals/metrics``) measures the
same idea for individual buying signals; this closes the loop for ICP segments.

Tuning is intentionally conservative:

* segments with fewer than ``segment_tuning_min_samples`` matched leads are left
  untouched (not enough evidence),
* each pass only moves the weight a fraction of the way toward the target
  (``segment_tuning_learning_rate``), damping noisy swings,
* proposed weights are clamped to ``[min_weight, max_weight]``.
"""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.config import settings
from app.models import Lead, Segment
from app.services.scoring import rescore_all, segment_matches

# Lead statuses that count as a positive outcome for a matched segment.
_QUALIFIED = "qualified"
_CONTACTED = {"contacted", "qualified"}


def propose_weight(
    current_weight: int,
    matched: int,
    qualified: int,
    *,
    min_samples: int | None = None,
    learning_rate: float | None = None,
    min_weight: int | None = None,
    max_weight: int | None = None,
) -> int:
    """Return the proposed weight for a segment given its outcome counts.

    The target weight maps the qualified conversion rate (0..1) linearly onto
    ``[min_weight, max_weight]``; the returned weight moves ``learning_rate`` of
    the way from ``current_weight`` toward that target. Segments without enough
    matched leads keep their current weight.
    """
    min_samples = settings.segment_tuning_min_samples if min_samples is None else min_samples
    learning_rate = settings.segment_tuning_learning_rate if learning_rate is None else learning_rate
    min_weight = settings.segment_tuning_min_weight if min_weight is None else min_weight
    max_weight = settings.segment_tuning_max_weight if max_weight is None else max_weight

    if matched < max(1, min_samples):
        return current_weight

    conversion = qualified / matched
    target = min_weight + (max_weight - min_weight) * conversion
    blended = current_weight + learning_rate * (target - current_weight)
    new_weight = int(round(blended))
    return max(min_weight, min(max_weight, new_weight))


async def compute_tuning(session: AsyncSession) -> list[dict]:
    """Evaluate every enabled segment against current lead outcomes.

    Returns one entry per enabled segment with its matched/contacted/qualified
    counts, the conversion rate, the current weight and the proposed weight.
    Does not persist anything.
    """
    seg_result = await session.execute(
        select(Segment).where(Segment.enabled.is_(True)).order_by(Segment.name)
    )
    segments = list(seg_result.scalars().all())

    lead_result = await session.execute(
        select(Lead).options(selectinload(Lead.emails), selectinload(Lead.tags))
    )
    leads = list(lead_result.scalars().all())

    out: list[dict] = []
    for seg in segments:
        matched = contacted = qualified = 0
        for lead in leads:
            if not segment_matches(seg, lead):
                continue
            matched += 1
            if lead.status in _CONTACTED:
                contacted += 1
            if lead.status == _QUALIFIED:
                qualified += 1
        proposed = propose_weight(seg.weight, matched, qualified)
        out.append({
            "segment_id": seg.id,
            "name": seg.name,
            "matched": matched,
            "contacted": contacted,
            "qualified": qualified,
            "conversion_rate": round(qualified / matched, 3) if matched else 0.0,
            "current_weight": seg.weight,
            "proposed_weight": proposed,
            "delta": proposed - seg.weight,
            "sufficient_data": matched >= max(1, settings.segment_tuning_min_samples),
        })
    return out


async def apply_tuning(session: AsyncSession) -> dict:
    """Persist proposed weights for segments whose weight would change, then
    rescore all leads so ``fit_score``/``priority_score`` reflect the new weights.

    Returns the list of applied changes plus how many leads were rescored.
    """
    proposals = await compute_tuning(session)
    changes = [p for p in proposals if p["delta"] != 0]
    if not changes:
        return {"applied": [], "rescored": 0}

    by_id = {p["segment_id"]: p for p in changes}
    seg_result = await session.execute(
        select(Segment).where(Segment.id.in_(list(by_id)))
    )
    for seg in seg_result.scalars().all():
        seg.weight = by_id[seg.id]["proposed_weight"]
    await session.commit()

    rescored = await rescore_all(session)
    return {"applied": changes, "rescored": rescored}
