"""Lead scoring.

Three numbers are produced for every lead:

* ``fit_score``     — how well the lead matches the active ICP segments
                      (firmographics + contactability). Weighted/partial: a lead
                      no longer scores ``None`` just because one rule failed.
* ``intent_score``  — strength of buying signals (web visits, news triggers, …),
                      with more recent signals weighted more heavily.
* ``priority_score``— a freshness-decayed blend of fit + intent used for ranking
                      and hot-lead alerting.

``segment_matches`` (full boolean match) is preserved for segment previews and
``matched_segment_ids`` semantics.
"""
from __future__ import annotations

import time
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.config import settings
from app.models import Lead, LeadSignal, Segment

_DAY = 86_400


# ---------------------------------------------------------------------------
# Rule evaluation
# ---------------------------------------------------------------------------

def _has_mx_valid_email(lead: Lead) -> bool:
    return any(e.mx_valid is True for e in lead.emails)


def _has_non_role_email(lead: Lead) -> bool:
    return any(not e.role_based for e in lead.emails)


def _has_deliverable_email(lead: Lead) -> bool:
    """At least one email that is MX-valid, not role-based, and not disposable."""
    return any(
        e.mx_valid is True and not e.role_based and not e.disposable
        for e in lead.emails
    )


def is_reachable(lead: Lead) -> bool:
    """A lead is reachable when it has a deliverable email AND a normalized phone."""
    return _has_deliverable_email(lead) and bool(lead.phone_normalized)


def _apply_operator(op: str, actual: Any, expected: Any) -> bool:
    """Generic comparison operators usable on any lead attribute."""
    if actual is None:
        return False
    try:
        if op == "gte":
            return actual >= expected
        if op == "lte":
            return actual <= expected
        if op == "gt":
            return actual > expected
        if op == "lt":
            return actual < expected
        if op == "eq":
            return actual == expected
        if op == "ne":
            return actual != expected
        if op == "in":
            return actual in (expected or [])
        if op == "contains":
            # actual is a collection (e.g. place_types); expected is a member.
            return expected in (actual or [])
    except TypeError:
        return False
    return False


def _operator_rule_passes(rule: str, value: Any, lead: Lead) -> bool:
    """Support operator-style rules of the form ``{"field": {"gte": 10}}``.

    The rule key must name a real ``Lead`` attribute and the value must be a dict
    of ``operator -> operand``. All operators in the dict must pass.
    """
    if not isinstance(value, dict) or not hasattr(lead, rule):
        return False
    actual = getattr(lead, rule)
    return all(_apply_operator(op, actual, operand) for op, operand in value.items())


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
    if rule == "deliverable_email":
        return _has_deliverable_email(lead) == bool(value)
    if rule == "reachable":
        return is_reachable(lead) == bool(value)

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

    # Operator-style rule on an arbitrary lead attribute, e.g.
    # {"employee_count_min": {"gte": 10}} or {"revenue_range": {"in": [...]}}.
    if _operator_rule_passes(rule, value, lead):
        return True

    # Unknown rule key — fail closed
    return False


def segment_matches(segment: Segment, lead: Lead) -> bool:
    """True only when *every* rule passes (preview + matched-id semantics)."""
    rules = segment.rules or {}
    if not rules:
        return False
    return all(_rule_passes(k, v, lead) for k, v in rules.items())


def segment_match_fraction(segment: Segment, lead: Lead) -> float:
    """Fraction (0..1) of a segment's rules that the lead satisfies."""
    rules = segment.rules or {}
    if not rules:
        return 0.0
    passed = sum(1 for k, v in rules.items() if _rule_passes(k, v, lead))
    return passed / len(rules)


# ---------------------------------------------------------------------------
# Fit
# ---------------------------------------------------------------------------

def evaluate_fit(lead: Lead, segments: list[Segment]) -> tuple[int | None, list[str]]:
    """Return ``(fit_score, matched_segment_ids)``.

    ``fit_score`` is the maximum, across enabled segments, of
    ``round(weight * match_fraction)`` — so a partial match still earns partial
    credit instead of falling to ``None``. ``matched_segment_ids`` lists segments
    that match *fully* (all rules), preserving downstream semantics.

    Unreachable leads are capped at ``fit_unreachable_cap`` so "high quality"
    always means actually contactable.
    """
    best = 0.0
    matched_full: list[str] = []
    for seg in segments:
        if not seg.enabled:
            continue
        frac = segment_match_fraction(seg, lead)
        if frac <= 0:
            continue
        best = max(best, seg.weight * frac)
        if frac >= 1.0:
            matched_full.append(seg.id)

    if best <= 0:
        return None, matched_full

    score = int(round(best))
    if not is_reachable(lead) and score > settings.fit_unreachable_cap:
        score = settings.fit_unreachable_cap
    return score, matched_full


def evaluate(lead: Lead, segments: list[Segment]) -> tuple[int | None, list[str]]:
    """Backward-compatible alias returning ``(fit_score, matched_segment_ids)``."""
    return evaluate_fit(lead, segments)


# ---------------------------------------------------------------------------
# Intent
# ---------------------------------------------------------------------------

def _recency_factor(detected_at: int, now: int, half_life_days: int) -> float:
    age_days = max(0.0, (now - detected_at) / _DAY)
    if half_life_days <= 0:
        return 1.0
    return 0.5 ** (age_days / half_life_days)


def compute_intent_score(signals: list[LeadSignal], now: int | None = None) -> int:
    """Sum signal strengths weighted by recency, clamped to 0..100."""
    if not signals:
        return 0
    ref = now if now is not None else int(time.time())
    total = 0.0
    for sig in signals:
        factor = _recency_factor(sig.detected_at, ref, settings.signal_half_life_days)
        total += (sig.strength or 0) * factor
    return max(0, min(100, int(round(total))))


# ---------------------------------------------------------------------------
# Priority (freshness-decayed blend)
# ---------------------------------------------------------------------------

def _freshness_factor(lead: Lead, now: int) -> float:
    reference = lead.last_touched_at or lead.created_at or now
    age_days = max(0.0, (now - reference) / _DAY)
    half_life = settings.freshness_half_life_days
    if half_life <= 0:
        return 1.0
    return 0.5 ** (age_days / half_life)


def compute_priority_score(fit: int | None, intent: int, lead: Lead, now: int | None = None) -> int:
    ref = now if now is not None else int(time.time())
    blended = settings.priority_fit_weight * (fit or 0) + settings.priority_intent_weight * intent
    decayed = blended * _freshness_factor(lead, ref)
    return max(0, min(100, int(round(decayed))))


# ---------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------

async def _load_enabled_segments(session: AsyncSession) -> list[Segment]:
    result = await session.execute(select(Segment).where(Segment.enabled.is_(True)))
    return list(result.scalars().all())


async def _load_signals(session: AsyncSession, lead_id: str) -> list[LeadSignal]:
    result = await session.execute(
        select(LeadSignal).where(LeadSignal.lead_id == lead_id)
    )
    return list(result.scalars().all())


def _assign_scores(lead: Lead, segments: list[Segment], signals: list[LeadSignal], now: int) -> None:
    fit, matched_ids = evaluate_fit(lead, segments)
    intent = compute_intent_score(signals, now)
    priority = compute_priority_score(fit, intent, lead, now)
    lead.fit_score = fit
    lead.intent_score = intent
    lead.priority_score = priority
    lead.matched_segment_ids = matched_ids
    # `score` stays as the primary ranking number for existing API filters/sort.
    lead.score = priority
    lead.score_breakdown = {
        "fit": fit,
        "intent": intent,
        "priority": priority,
        "reachable": is_reachable(lead),
        "signal_count": len(signals),
        "scored_at": now,
    }


async def score_lead(session: AsyncSession, lead: Lead) -> None:
    segments = await _load_enabled_segments(session)
    signals = await _load_signals(session, lead.id)
    _assign_scores(lead, segments, signals, int(time.time()))


async def rescore_all(session: AsyncSession) -> int:
    segments = await _load_enabled_segments(session)
    result = await session.execute(
        select(Lead).options(
            selectinload(Lead.emails),
            selectinload(Lead.tags),
            selectinload(Lead.signals),
        )
    )
    leads = list(result.scalars().all())
    now = int(time.time())
    for lead in leads:
        _assign_scores(lead, segments, list(lead.signals), now)
    await session.commit()
    return len(leads)
