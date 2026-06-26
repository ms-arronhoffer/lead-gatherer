"""Tests for outcome-based segment-weight tuning."""
import time
import uuid

import pytest

from app.config import settings
from app.db import AsyncSessionLocal, init_db
from app.models import Lead, Segment
from app.services import segment_tuning


# --- pure proposal function -------------------------------------------------

def test_propose_weight_skips_insufficient_samples():
    # Fewer matched leads than min_samples -> weight unchanged.
    assert segment_tuning.propose_weight(50, matched=2, qualified=2, min_samples=5) == 50


def test_propose_weight_high_conversion_raises_toward_max():
    # 100% conversion, learning_rate 1.0 -> jumps straight to max_weight.
    w = segment_tuning.propose_weight(
        40, matched=10, qualified=10,
        min_samples=5, learning_rate=1.0, min_weight=10, max_weight=100,
    )
    assert w == 100


def test_propose_weight_zero_conversion_drops_toward_min():
    w = segment_tuning.propose_weight(
        80, matched=10, qualified=0,
        min_samples=5, learning_rate=1.0, min_weight=10, max_weight=100,
    )
    assert w == 10


def test_propose_weight_learning_rate_damps_swing():
    # target for 50% conversion is 55; halfway from 80 -> 67.5 -> 68 (round).
    w = segment_tuning.propose_weight(
        80, matched=10, qualified=5,
        min_samples=5, learning_rate=0.5, min_weight=10, max_weight=100,
    )
    assert w == 68


def test_propose_weight_clamped_to_bounds():
    w = segment_tuning.propose_weight(
        100, matched=10, qualified=10,
        min_samples=5, learning_rate=1.0, min_weight=10, max_weight=90,
    )
    assert w == 90


# --- integration over the DB ------------------------------------------------

def _seg(weight=50, rules=None):
    now = int(time.time())
    return Segment(
        id=str(uuid.uuid4()), name="ICP", weight=weight,
        rules=rules or {"has_website": True}, enabled=True,
        created_at=now, updated_at=now,
    )


def _lead(status, website="https://x.com"):
    now = int(time.time())
    return Lead(
        id=str(uuid.uuid4()), name="Acme", website=website, place_types=[],
        matched_segment_ids=[], status=status, source="test",
        created_at=now, updated_at=now, score_breakdown={}, fit_reasons=[],
    )


@pytest.mark.asyncio
async def test_compute_and_apply_tuning(client):
    await init_db()
    async with AsyncSessionLocal() as session:
        seg = _seg(weight=50)
        session.add(seg)
        # 6 matched leads (all have a website), 3 qualified -> 50% conversion.
        for st in ["qualified", "qualified", "qualified", "contacted", "new", "rejected"]:
            session.add(_lead(st))
        # A non-matching lead (no website) should be ignored.
        session.add(_lead("qualified", website=None))
        await session.commit()

        proposals = await segment_tuning.compute_tuning(session)
        mine = next(p for p in proposals if p["segment_id"] == seg.id)
        assert mine["matched"] == 6
        assert mine["qualified"] == 3
        assert mine["contacted"] == 4  # contacted + qualified
        assert mine["conversion_rate"] == 0.5
        assert mine["sufficient_data"] is True
        # target 55, halfway from 50 -> 52 or 53 depending on rounding
        assert mine["current_weight"] == 50
        assert mine["proposed_weight"] != 50

        result = await segment_tuning.apply_tuning(session)
        assert result["rescored"] >= 6
        refreshed = await session.get(Segment, seg.id)
        assert refreshed.weight == mine["proposed_weight"]


@pytest.mark.asyncio
async def test_tuning_preview_endpoint(client):
    resp = await client.get("/api/v1/segments/tuning")
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)


@pytest.mark.asyncio
async def test_tuning_apply_endpoint(client):
    resp = await client.post("/api/v1/segments/tuning/apply")
    assert resp.status_code == 200
    body = resp.json()
    assert "applied" in body and "rescored" in body
