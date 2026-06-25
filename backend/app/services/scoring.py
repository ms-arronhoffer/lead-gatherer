"""ICP scoring: evaluate each lead against active segments and assign
the maximum weight of any segment whose rules all pass."""
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models import Lead, Segment


def _has_mx_valid_email(lead: Lead) -> bool:
    return any(e.mx_valid is True for e in lead.emails)


def _has_non_role_email(lead: Lead) -> bool:
    return any(not e.role_based for e in lead.emails)


def _rule_passes(rule: str, value: Any, lead: Lead) -> bool:
    # Contact quality
    if rule == "has_email":
        return bool(lead.emails) == bool(value)
    if rule == "has_phone":
        return bool(lead.phone) == bool(value)
    if rule == "has_website":
        return bool(lead.website) == bool(value)
    if rule == "mx_valid_email":
        return _has_mx_valid_email(lead) == bool(value)
    if rule == "non_role_email":
        return _has_non_role_email(lead) == bool(value)

    # Firmographics
    if rule == "min_employee_count":
        return (lead.employee_count_min or 0) >= int(value)
    if rule == "max_employee_count":
        return (lead.employee_count_max or 0) <= int(value) if lead.employee_count_max else False
    if rule == "revenue_range_in":
        return lead.revenue_range in (value or [])

    # Workflow state
    if rule == "status_in":
        return lead.status in (value or [])
    if rule == "assigned":
        is_assigned = lead.assigned_to_user_id is not None
        return is_assigned == bool(value)
    if rule == "unassigned":
        is_unassigned = lead.assigned_to_user_id is None
        return is_unassigned == bool(value)

    # Categorical / labels
    if rule == "tags_any":
        lead_tag_ids = {t.id for t in (lead.tags or [])}
        return bool(lead_tag_ids & set(value or []))
    if rule == "tags_all":
        lead_tag_ids = {t.id for t in (lead.tags or [])}
        return set(value or []).issubset(lead_tag_ids)
    if rule == "place_types_any":
        return bool(set(lead.place_types or []) & set(value or []))
    if rule == "place_types_all":
        return set(value or []).issubset(set(lead.place_types or []))

    # Unknown rule key — fail closed
    return False


def segment_matches(segment: Segment, lead: Lead) -> bool:
    rules = segment.rules or {}
    if not rules:
        return False
    return all(_rule_passes(k, v, lead) for k, v in rules.items())


def evaluate(lead: Lead, segments: list[Segment]) -> tuple[int | None, list[str]]:
    """Return (score, matched_segment_ids). Score is the max weight across matches,
    or None if no segments match."""
    matched: list[tuple[Segment, int]] = []
    for seg in segments:
        if not seg.enabled:
            continue
        if segment_matches(seg, lead):
            matched.append((seg, seg.weight))
    if not matched:
        return None, []
    best = max(matched, key=lambda x: x[1])[1]
    ids = [s.id for s, _ in matched]
    return best, ids


async def _load_enabled_segments(session: AsyncSession) -> list[Segment]:
    result = await session.execute(select(Segment).where(Segment.enabled.is_(True)))
    return list(result.scalars().all())


async def score_lead(session: AsyncSession, lead: Lead) -> None:
    segments = await _load_enabled_segments(session)
    score, ids = evaluate(lead, segments)
    lead.score = score
    lead.matched_segment_ids = ids


async def rescore_all(session: AsyncSession) -> int:
    segments = await _load_enabled_segments(session)
    result = await session.execute(
        select(Lead).options(selectinload(Lead.emails), selectinload(Lead.tags))
    )
    leads = list(result.scalars().all())
    for lead in leads:
        score, ids = evaluate(lead, segments)
        lead.score = score
        lead.matched_segment_ids = ids
    await session.commit()
    return len(leads)
