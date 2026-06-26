"""Decision-maker filtering + LLM normalization/ranking.

Scraped profiles are noisy (truncated titles, marketing fluff, wrong people).
This module first cheaply filters to likely decision makers by title keyword,
then hands the survivors to the LLM to normalize fields, infer a seniority tier,
and score relevance to the buyer's ICP — keeping only the top N candidates.
"""
from __future__ import annotations

import logging

from app.config import settings
from app.services import llm_client

logger = logging.getLogger(__name__)

# Seniority tiers in descending order; used for the non-LLM fallback ranking.
_SENIORITY_ORDER = ["c_suite", "owner", "vp", "director", "head", "manager", "other"]
_SENIORITY_RANK = {tier: i for i, tier in enumerate(_SENIORITY_ORDER)}

_RANK_SCHEMA = {
    "type": "object",
    "properties": {
        "candidates": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                    "title": {"type": "string"},
                    "seniority": {
                        "type": "string",
                        "enum": _SENIORITY_ORDER,
                    },
                    "profile_url": {"type": "string"},
                    "location": {"type": "string"},
                    "is_decision_maker": {"type": "boolean"},
                    "relevance": {"type": "number", "minimum": 0, "maximum": 1},
                },
                "required": ["name", "title", "seniority", "is_decision_maker", "relevance"],
            },
        }
    },
    "required": ["candidates"],
}

_SYSTEM = (
    "You are a B2B sales-intelligence analyst. Given scraped LinkedIn profiles "
    "for people associated with a target company, identify the DECISION MAKERS "
    "(C-suite, owner/founder, president, partner, VP, director, or 'head of'). "
    "For each, normalize their name and current title, classify seniority into "
    "one of: c_suite, owner, vp, director, head, manager, other; set "
    "is_decision_maker; and score relevance (0-1) to the buyer's ICP. Only use "
    "facts present in the input — never invent people, titles, or contact info. "
    "Preserve each person's profile_url exactly. Return JSON matching the schema."
)


def is_decision_maker(text: str) -> bool:
    """Cheap keyword check against the configured decision-maker title list."""
    if not text:
        return False
    low = text.lower()
    return any(kw in low for kw in settings.linkedin_decision_maker_titles)


def _prefilter(profiles: list[dict]) -> list[dict]:
    """Keep profiles whose headline/title looks like a decision maker.

    Falls back to the full list when the keyword filter removes everything, so a
    sparse-headline scrape still gets a chance at LLM ranking.
    """
    filtered = [
        p for p in profiles
        if is_decision_maker(p.get("headline", "")) or is_decision_maker(p.get("title", ""))
    ]
    return filtered or profiles


def _fallback_rank(profiles: list[dict], max_candidates: int) -> list[dict]:
    """Heuristic ranking used when the LLM is unavailable."""
    def seniority_of(p: dict) -> str:
        text = f"{p.get('headline', '')} {p.get('title', '')}".lower()
        if any(k in text for k in ("ceo", "cfo", "coo", "cto", "cmo", "chief")):
            return "c_suite"
        if any(k in text for k in ("owner", "founder")):
            return "owner"
        if "vp" in text or "vice president" in text:
            return "vp"
        if "director" in text:
            return "director"
        if "head of" in text:
            return "head"
        if "manager" in text:
            return "manager"
        return "other"

    enriched = []
    for p in profiles:
        tier = seniority_of(p)
        enriched.append({
            "name": p.get("name", ""),
            "title": p.get("headline") or p.get("title") or "",
            "seniority": tier,
            "profile_url": p.get("profile_url", ""),
            "location": p.get("location", ""),
            "is_decision_maker": tier != "other",
            "relevance": 1.0 - _SENIORITY_RANK.get(tier, len(_SENIORITY_ORDER)) / len(_SENIORITY_ORDER),
        })
    enriched.sort(key=lambda c: (_SENIORITY_RANK.get(c["seniority"], 99), -c["relevance"]))
    return enriched[:max_candidates]


async def normalize_and_rank(
    company: str,
    profiles: list[dict],
    *,
    max_candidates: int | None = None,
    icp_hint: str = "",
) -> list[dict]:
    """Return the top decision-maker candidates, normalized and ranked.

    Each item: ``{name, title, seniority, profile_url, location,
    is_decision_maker, relevance}``.
    """
    if max_candidates is None:
        max_candidates = settings.linkedin_max_candidates
    if not profiles:
        return []

    candidates = _prefilter(profiles)

    if not llm_client.is_configured():
        return _fallback_rank(candidates, max_candidates)

    payload_lines = []
    for i, p in enumerate(candidates):
        payload_lines.append(
            f"[{i}] name={p.get('name', '')!r} headline={p.get('headline', '')!r} "
            f"title={p.get('title', '')!r} location={p.get('location', '')!r} "
            f"profile_url={p.get('profile_url', '')!r} about={(p.get('about', '') or '')[:300]!r}"
        )
    user = (
        f"Target company: {company}\n"
        + (f"Buyer ICP: {icp_hint}\n" if icp_hint else "")
        + "\nScraped profiles:\n"
        + "\n".join(payload_lines)
        + "\n\nReturn ONLY JSON matching the schema."
    )
    try:
        result = await llm_client.complete(
            [{"role": "system", "content": _SYSTEM}, {"role": "user", "content": user}],
            schema=_RANK_SCHEMA,
            max_tokens=1200,
        )
    except Exception as exc:  # noqa: BLE001 - degrade to heuristic ranking
        logger.warning("LinkedIn candidate ranking failed for %s: %s", company, exc)
        return _fallback_rank(candidates, max_candidates)

    raw = result.get("candidates", []) if isinstance(result, dict) else []
    cleaned: list[dict] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        if not item.get("is_decision_maker"):
            continue
        name = str(item.get("name", "")).strip()
        if not name:
            continue
        seniority = str(item.get("seniority", "other")).strip().lower()
        if seniority not in _SENIORITY_RANK:
            seniority = "other"
        try:
            relevance = float(item.get("relevance", 0))
        except (TypeError, ValueError):
            relevance = 0.0
        cleaned.append({
            "name": name,
            "title": str(item.get("title", "")).strip(),
            "seniority": seniority,
            "profile_url": str(item.get("profile_url", "")).strip(),
            "location": str(item.get("location", "")).strip(),
            "is_decision_maker": True,
            "relevance": max(0.0, min(1.0, relevance)),
        })

    cleaned.sort(key=lambda c: (_SENIORITY_RANK.get(c["seniority"], 99), -c["relevance"]))
    return cleaned[:max_candidates]
