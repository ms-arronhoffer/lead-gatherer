"""Tests for the LinkedIn enrichment layer.

No live LinkedIn / Playwright is used: the scrape step is injected with a
``CompanyScrape`` fixture and the LLM client is monkeypatched. Verifies
decision-maker ranking, contact persistence, and post -> buying-signal mapping.
"""
import time
import uuid

import pytest
import pytest_asyncio
from sqlalchemy import select

from app.config import settings
from app.db import AsyncSessionLocal, init_db
from app.models import Lead, LeadContact, LeadSignal
from app.services.linkedin import company_search, decision_makers, enricher, post_signals
from app.services.linkedin.company_search import CompanyScrape, RawPost, RawProfile


@pytest_asyncio.fixture
async def lead_id():
    await init_db()
    lid = f"lead-{uuid.uuid4().hex[:8]}"
    now = int(time.time())
    async with AsyncSessionLocal() as s:
        s.add(Lead(
            id=lid, name="Acme Robotics", place_types=[], matched_segment_ids=[],
            score_breakdown={}, fit_reasons=[], status="new",
            created_at=now, updated_at=now,
        ))
        await s.commit()
    return lid


@pytest.fixture
def enable_linkedin(monkeypatch):
    monkeypatch.setattr(settings, "enable_linkedin_enrichment", True)
    monkeypatch.setattr(settings, "linkedin_username", "u@example.com")
    monkeypatch.setattr(settings, "linkedin_password", "secret")


# --- decision_makers.is_decision_maker / fallback ranking ---

def test_is_decision_maker_matches_titles():
    assert decision_makers.is_decision_maker("Chief Executive Officer")
    assert decision_makers.is_decision_maker("VP of Sales")
    assert decision_makers.is_decision_maker("Owner & Founder")
    assert not decision_makers.is_decision_maker("Junior Software Engineer")
    assert not decision_makers.is_decision_maker("")


@pytest.mark.asyncio
async def test_normalize_and_rank_fallback_without_llm(monkeypatch):
    # Force the no-LLM heuristic path.
    monkeypatch.setattr(decision_makers.llm_client, "is_configured", lambda: False)
    profiles = [
        {"name": "Ann Boss", "headline": "CEO at Acme", "profile_url": "https://x/in/ann"},
        {"name": "Bob Mid", "headline": "Marketing Manager", "profile_url": "https://x/in/bob"},
        {"name": "Cara VP", "headline": "VP Engineering", "profile_url": "https://x/in/cara"},
    ]
    ranked = await decision_makers.normalize_and_rank("Acme", profiles, max_candidates=5)
    # CEO ranks above VP above Manager; manager is not a decision maker tier 'other'? manager kept.
    names = [c["name"] for c in ranked]
    assert names[0] == "Ann Boss"
    assert "Cara VP" in names
    assert ranked[0]["seniority"] == "c_suite"


@pytest.mark.asyncio
async def test_normalize_and_rank_uses_llm_and_caps(monkeypatch):
    monkeypatch.setattr(decision_makers.llm_client, "is_configured", lambda: True)

    async def fake_complete(messages, *, schema=None, max_tokens=800):
        return {"candidates": [
            {"name": "Ann Boss", "title": "CEO", "seniority": "c_suite",
             "profile_url": "https://x/in/ann", "is_decision_maker": True, "relevance": 0.9},
            {"name": "Cara VP", "title": "VP Eng", "seniority": "vp",
             "profile_url": "https://x/in/cara", "is_decision_maker": True, "relevance": 0.8},
            {"name": "Not Relevant", "title": "Intern", "seniority": "other",
             "profile_url": "https://x/in/n", "is_decision_maker": False, "relevance": 0.1},
        ]}

    monkeypatch.setattr(decision_makers.llm_client, "complete", fake_complete)
    profiles = [{"name": "x", "headline": "CEO", "profile_url": "https://x/in/ann"}]
    ranked = await decision_makers.normalize_and_rank("Acme", profiles, max_candidates=1)
    assert len(ranked) == 1  # capped
    assert ranked[0]["name"] == "Ann Boss"  # c_suite ranked first
    assert ranked[0]["seniority"] == "c_suite"


@pytest.mark.asyncio
async def test_normalize_and_rank_empty():
    assert await decision_makers.normalize_and_rank("Acme", []) == []


# --- post_signals classification + recording ---

@pytest.mark.asyncio
async def test_classify_posts_maps_known_types(monkeypatch):
    monkeypatch.setattr(post_signals.llm_client, "is_configured", lambda: True)

    async def fake_complete(messages, *, schema=None, max_tokens=800):
        return {"signals": [
            {"type": "funding_round", "evidence": "Raised $10M Series A", "confidence": 0.9},
            {"type": "not_a_real_type", "evidence": "noise", "confidence": 0.9},
        ]}

    monkeypatch.setattr(post_signals.llm_client, "complete", fake_complete)
    out = await post_signals.classify_posts("Acme", [{"text": "We raised money"}])
    assert len(out) == 1
    assert out[0]["type"] == "funding_round"
    assert out[0]["strength"] > 0


@pytest.mark.asyncio
async def test_classify_posts_empty_without_text():
    assert await post_signals.classify_posts("Acme", [{"text": ""}]) == []


@pytest.mark.asyncio
async def test_detect_and_record_creates_signals(lead_id, monkeypatch):
    import app.services.webhook_dispatcher as wd

    async def noop(event, payload):
        return None

    monkeypatch.setattr(wd, "enqueue_event", noop)

    async def fake_classify(company, posts):
        return [{"type": "expansion", "strength": 30, "evidence": "Opening a new office", "confidence": 0.8}]

    monkeypatch.setattr(post_signals, "classify_posts", fake_classify)

    n = await post_signals.detect_and_record(
        lead_id, "Acme", [{"text": "New office!", "url": "https://x/post/1"}]
    )
    assert n == 1
    async with AsyncSessionLocal() as s:
        sigs = (await s.execute(
            select(LeadSignal).where(LeadSignal.lead_id == lead_id)
        )).scalars().all()
        assert len(sigs) == 1
        assert sigs[0].type == "expansion"
        assert sigs[0].source == "linkedin"


# --- enricher orchestration with injected scraper ---

@pytest.mark.asyncio
async def test_enrich_lead_persists_contacts_and_signals(lead_id, enable_linkedin, monkeypatch):
    import app.services.webhook_dispatcher as wd

    async def noop(event, payload):
        return None

    monkeypatch.setattr(wd, "enqueue_event", noop)

    # Injected scrape result — no browser involved.
    async def fake_scraper(query):
        return CompanyScrape(
            query=query,
            company_url="https://www.linkedin.com/company/acme",
            profiles=[
                RawProfile(name="Ann Boss", profile_url="https://x/in/ann", headline="CEO"),
                RawProfile(name="Cara VP", profile_url="https://x/in/cara", headline="VP Sales"),
            ],
            posts=[RawPost(text="We raised a $10M Series A", url="https://x/post/1")],
        )

    # Deterministic ranking + classification (skip real LLM).
    async def fake_rank(company, profiles, *, max_candidates=5, icp_hint=""):
        return [
            {"name": "Ann Boss", "title": "CEO", "seniority": "c_suite",
             "profile_url": "https://x/in/ann", "is_decision_maker": True, "relevance": 0.9},
        ]

    async def fake_detect(lead, company, posts):
        from app.services.signals.signal_service import record_signal
        await record_signal(lead, type="funding_round", strength=40, source="linkedin",
                            dedupe_key="funding_round:abc")
        return 1

    monkeypatch.setattr(decision_makers, "normalize_and_rank", fake_rank)
    monkeypatch.setattr(post_signals, "detect_and_record", fake_detect)

    stats = await enricher.enrich_lead(lead_id, scraper=fake_scraper)
    assert stats["contacts_added"] == 1
    assert stats["signals_recorded"] == 1
    assert stats["profiles_scanned"] == 2

    async with AsyncSessionLocal() as s:
        contacts = (await s.execute(
            select(LeadContact).where(LeadContact.lead_id == lead_id)
        )).scalars().all()
        assert len(contacts) == 1
        assert contacts[0].source == "linkedin"
        assert contacts[0].seniority == "c_suite"
        assert contacts[0].linkedin_url == "https://x/in/ann"


@pytest.mark.asyncio
async def test_enrich_lead_dedupes_contacts(lead_id, enable_linkedin, monkeypatch):
    import app.services.webhook_dispatcher as wd
    monkeypatch.setattr(wd, "enqueue_event", lambda *a, **k: None)

    async def fake_scraper(query):
        return CompanyScrape(query=query, profiles=[], posts=[])

    async def fake_rank(company, profiles, *, max_candidates=5, icp_hint=""):
        return [{"name": "Ann Boss", "title": "CEO", "seniority": "c_suite",
                 "profile_url": "https://x/in/ann", "is_decision_maker": True, "relevance": 0.9}]

    monkeypatch.setattr(decision_makers, "normalize_and_rank", fake_rank)

    s1 = await enricher.enrich_lead(lead_id, scraper=fake_scraper)
    s2 = await enricher.enrich_lead(lead_id, scraper=fake_scraper)
    assert s1["contacts_added"] == 1
    assert s2["contacts_added"] == 0  # deduped on linkedin_url

    async with AsyncSessionLocal() as s:
        contacts = (await s.execute(
            select(LeadContact).where(LeadContact.lead_id == lead_id)
        )).scalars().all()
        assert len(contacts) == 1


@pytest.mark.asyncio
async def test_enrich_lead_skips_when_not_configured(lead_id):
    # enable_linkedin fixture NOT applied -> feature disabled.
    stats = await enricher.enrich_lead(lead_id)
    assert stats.get("skipped") == "not_configured"


@pytest.mark.asyncio
async def test_enrich_lead_handles_scrape_failure(lead_id, enable_linkedin):
    async def boom(query):
        raise RuntimeError("selector drift")

    stats = await enricher.enrich_lead(lead_id, scraper=boom)
    assert stats["error"] == "scrape_failed"
    assert stats["contacts_added"] == 0
