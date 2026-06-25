"""LLM classification of recent news into buying-trigger signals.

Reuses the existing news enricher (which already fetches & scrapes recent
articles) and the multi-provider LLM client. Instead of mining articles only for
*contacts*, this classifies them into classic buying triggers — funding rounds,
leadership hires, expansion, product launches, hiring sprees, M&A, layoffs — and
records each as a :class:`~app.models.LeadSignal`.
"""
from __future__ import annotations

import logging

from app.services import llm_client
from app.services.enrichment.news_enricher import find_news
from app.services.signals.signal_service import record_signal

logger = logging.getLogger(__name__)

# Canonical signal types and their default intent strength (points).
SIGNAL_STRENGTHS: dict[str, int] = {
    "funding_round": 40,
    "m_and_a": 35,
    "expansion": 30,
    "leadership_hire": 25,
    "product_launch": 20,
    "hiring": 18,
    "layoffs": 10,
}

_SYSTEM = (
    "You are a B2B sales-intelligence analyst. From the provided news text about "
    "a company, extract concrete BUYING-SIGNAL events. Only report events clearly "
    "supported by the text — never invent. Allowed types: funding_round, m_and_a, "
    "expansion, leadership_hire, product_launch, hiring, layoffs. For each event "
    "give a one-sentence evidence quote/paraphrase grounded in the text."
)

_SCHEMA = {
    "type": "object",
    "properties": {
        "signals": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "type": {"type": "string"},
                    "evidence": {"type": "string"},
                    "confidence": {"type": "number"},
                },
                "required": ["type", "evidence"],
            },
        }
    },
    "required": ["signals"],
}


def _strength_for(signal_type: str, confidence: float) -> int:
    base = SIGNAL_STRENGTHS.get(signal_type, 0)
    if base <= 0:
        return 0
    conf = max(0.0, min(1.0, confidence))
    # Confidence scales strength but never below half of base.
    return int(round(base * (0.5 + 0.5 * conf)))


async def classify_news(company: str, text: str) -> list[dict]:
    """Return a list of ``{type, strength, evidence, confidence}`` signal dicts."""
    if not text or not company or not llm_client.is_configured():
        return []
    user = (
        f"Company: {company}\n\n"
        f"News text (may concatenate several articles):\n{text[:8000]}\n\n"
        "Return ONLY JSON matching the schema."
    )
    try:
        result = await llm_client.complete(
            [{"role": "system", "content": _SYSTEM}, {"role": "user", "content": user}],
            schema=_SCHEMA,
            max_tokens=600,
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("News signal classification failed for %s: %s", company, exc)
        return []

    raw_signals = result.get("signals", []) if isinstance(result, dict) else []
    out: list[dict] = []
    for item in raw_signals:
        if not isinstance(item, dict):
            continue
        stype = str(item.get("type", "")).strip().lower()
        if stype not in SIGNAL_STRENGTHS:
            continue
        try:
            confidence = float(item.get("confidence", 0.7))
        except (TypeError, ValueError):
            confidence = 0.7
        strength = _strength_for(stype, confidence)
        if strength <= 0:
            continue
        evidence = str(item.get("evidence", "")).strip()[:500]
        out.append({
            "type": stype,
            "strength": strength,
            "evidence": evidence,
            "confidence": confidence,
        })
    return out


async def detect_and_record(lead_id: str, company: str, location: str = "") -> int:
    """Fetch recent news, classify it, and record any buying signals.

    Returns the number of signals recorded. Best-effort: never raises.
    """
    if not company:
        return 0
    try:
        news = await find_news(company, location)
    except Exception as exc:  # noqa: BLE001
        logger.debug("News fetch failed for %s: %s", company, exc)
        return 0
    if not news.articles:
        return 0

    classified = await classify_news(company, news.combined_text)
    if not classified:
        return 0

    recorded = 0
    for sig in classified:
        # Dedupe on type so we don't re-add the same trigger every poll cycle.
        sid = await record_signal(
            lead_id,
            type=sig["type"],
            strength=sig["strength"],
            source="news",
            payload={
                "evidence": sig["evidence"],
                "confidence": sig["confidence"],
                "article_urls": [a.url for a in news.articles],
            },
            dedupe_key=sig["type"],
        )
        if sid:
            recorded += 1
    return recorded
