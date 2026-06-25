"""Unit tests for the scoring engine: operators, partial/weighted fit,
reachability gate, intent from signals, and freshness decay."""
import time

import pytest

from app.config import settings
from app.models import Lead, LeadEmail, LeadSignal, Segment
from app.services import scoring

_DAY = 86_400


def _lead(**kw) -> Lead:
    base = dict(
        id="l1", name="Acme", place_types=[], matched_segment_ids=[],
        emails=[], tags=[], status="new", created_at=int(time.time()),
        updated_at=int(time.time()), score_breakdown={}, fit_reasons=[],
    )
    base.update(kw)
    lead = Lead(**base)
    # SQLAlchemy relationships default to None on detached instances; force lists.
    lead.emails = kw.get("emails", [])
    lead.tags = kw.get("tags", [])
    return lead


def _email(**kw) -> LeadEmail:
    base = dict(mx_valid=True, role_based=False, disposable=False)
    base.update(kw)
    e = LeadEmail(id="e", lead_id="l1", email="a@b.com", email_normalized="a@b.com",
                  source="website", confidence=1.0, **base)
    return e


def _seg(rules, weight=80, enabled=True) -> Segment:
    return Segment(id="s1", name="seg", weight=weight, rules=rules, enabled=enabled,
                   created_at=0, updated_at=0)


# --- operators -------------------------------------------------------------

def test_operator_gte_and_lte():
    lead = _lead(employee_count_min=50, employee_count_max=200)
    assert scoring._rule_passes("employee_count_min", {"gte": 10}, lead)
    assert not scoring._rule_passes("employee_count_min", {"gte": 100}, lead)
    assert scoring._rule_passes("employee_count_max", {"lte": 500}, lead)


def test_operator_in_and_contains():
    lead = _lead(revenue_range="1M-5M", place_types=["saas", "fintech"])
    assert scoring._rule_passes("revenue_range", {"in": ["1M-5M", "5M-10M"]}, lead)
    assert scoring._rule_passes("place_types", {"contains": "fintech"}, lead)
    assert not scoring._rule_passes("place_types", {"contains": "retail"}, lead)


# --- partial / weighted fit ------------------------------------------------

def test_partial_match_earns_partial_credit():
    # Two rules; lead satisfies one. Should earn ~half of weight, not None.
    lead = _lead(website="https://acme.com", phone_normalized="+15125551234",
                 emails=[_email()])
    seg = _seg({"has_website": True, "min_employee_count": 500}, weight=80)
    fit, matched = scoring.evaluate_fit(lead, [seg])
    assert fit == 40  # 80 * 0.5
    assert matched == []  # not a full match


def test_full_match_lists_segment_id():
    lead = _lead(website="https://acme.com", phone_normalized="+15125551234",
                 emails=[_email()])
    seg = _seg({"has_website": True}, weight=70)
    fit, matched = scoring.evaluate_fit(lead, [seg])
    assert fit == 70
    assert matched == ["s1"]


# --- reachability gate -----------------------------------------------------

def test_unreachable_lead_capped():
    # Full match (weight 100) but no deliverable email + no phone → capped.
    lead = _lead()
    seg = _seg({"has_website": False}, weight=100)
    fit, matched = scoring.evaluate_fit(lead, [seg])
    assert fit == settings.fit_unreachable_cap
    assert matched == ["s1"]


def test_reachable_lead_not_capped():
    lead = _lead(website="x", phone_normalized="+15125551234", emails=[_email()])
    seg = _seg({"has_website": True}, weight=100)
    fit, _ = scoring.evaluate_fit(lead, [seg])
    assert fit == 100


def test_role_based_email_is_not_deliverable():
    lead = _lead(phone_normalized="+15125551234",
                 emails=[_email(role_based=True)])
    assert not scoring.is_reachable(lead)


# --- intent ----------------------------------------------------------------

def _signal(strength, age_days=0, stype="web_visit") -> LeadSignal:
    now = int(time.time())
    return LeadSignal(id="sig", lead_id="l1", type=stype, strength=strength,
                      source="test", detected_at=now - age_days * _DAY, payload={})


def test_intent_sums_strengths():
    now = int(time.time())
    sigs = [_signal(20), _signal(15)]
    assert scoring.compute_intent_score(sigs, now) == 35


def test_intent_recency_decay():
    now = int(time.time())
    fresh = scoring.compute_intent_score([_signal(40, age_days=0)], now)
    old = scoring.compute_intent_score(
        [_signal(40, age_days=settings.signal_half_life_days)], now)
    assert fresh == 40
    assert old == 20  # one half-life → half strength


def test_intent_clamped_to_100():
    now = int(time.time())
    sigs = [_signal(60), _signal(60), _signal(60)]
    assert scoring.compute_intent_score(sigs, now) == 100


# --- priority + freshness --------------------------------------------------

def test_priority_blends_fit_and_intent():
    now = int(time.time())
    lead = _lead(created_at=now, last_touched_at=now)
    # 0.6*80 + 0.4*50 = 68, fresh → no decay
    assert scoring.compute_priority_score(80, 50, lead, now) == 68


def test_priority_decays_when_stale():
    now = int(time.time())
    stale = _lead(created_at=now - settings.freshness_half_life_days * _DAY,
                  last_touched_at=now - settings.freshness_half_life_days * _DAY)
    # 0.6*80 + 0.4*50 = 68, one half-life → ~34
    assert scoring.compute_priority_score(80, 50, stale, now) == 34
