"""Classify recent LinkedIn posts into first-class buying signals.

Reuses the canonical signal taxonomy and strengths from the news classifier so
LinkedIn-sourced signals are scored and deduped exactly like news-sourced ones,
then records each via :func:`app.services.signals.signal_service.record_signal`.
"""
from __future__ import annotations

import hashlib
import logging

from app.services import llm_client
from app.services.signals.news_signals import SIGNAL_STRENGTHS, _strength_for
from app.services.signals.signal_service import record_signal

logger = logging.getLogger(__name__)

_SYSTEM = (
    "You are a B2B sales-intelligence analyst. From the provided recent LinkedIn "
    "posts authored by or about a company, extract concrete BUYING-SIGNAL events. "
    "Only report events clearly supported by the text — never invent. Allowed "
    "types: funding_round, m_and_a, expansion, leadership_hire, product_launch, "
    "hiring, layoffs. For each event give a one-sentence evidence quote/paraphrase "
    "grounded in the post text."
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


async def classify_posts(company: str, posts: list[dict]) -> list[dict]:
    """Classify post texts into ``{type, strength, evidence, confidence}`` dicts."""
    texts = [str(p.get("text", "")).strip() for p in posts if p.get("text")]
    combined = "\n\n---\n\n".join(t for t in texts if t)
    if not combined or not company or not llm_client.is_configured():
        return []

    user = (
        f"Company: {company}\n\n"
        f"Recent LinkedIn posts (may concatenate several):\n{combined[:8000]}\n\n"
        "Return ONLY JSON matching the schema."
    )
    try:
        result = await llm_client.complete(
            [{"role": "system", "content": _SYSTEM}, {"role": "user", "content": user}],
            schema=_SCHEMA,
            max_tokens=600,
        )
    except Exception as exc:  # noqa: BLE001 - best-effort
        logger.warning("LinkedIn post signal classification failed for %s: %s", company, exc)
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
        out.append({
            "type": stype,
            "strength": strength,
            "evidence": str(item.get("evidence", "")).strip()[:500],
            "confidence": confidence,
        })
    return out


async def detect_and_record(lead_id: str, company: str, posts: list[dict]) -> int:
    """Classify posts and record each as a LeadSignal. Returns count recorded.

    Dedupe key combines the signal type with a hash of its evidence so distinct
    events of the same type (e.g. two product launches) are both kept, while
    re-scraping the same post is a no-op.
    """
    classified = await classify_posts(company, posts)
    if not classified:
        return 0

    post_urls = [p.get("url", "") for p in posts if p.get("url")]
    recorded = 0
    for sig in classified:
        evidence_hash = hashlib.sha1(sig["evidence"].encode("utf-8")).hexdigest()[:12]
        sid = await record_signal(
            lead_id,
            type=sig["type"],
            strength=sig["strength"],
            source="linkedin",
            payload={
                "evidence": sig["evidence"],
                "confidence": sig["confidence"],
                "post_urls": post_urls,
            },
            dedupe_key=f"{sig['type']}:{evidence_hash}",
        )
        if sid:
            recorded += 1
    return recorded
