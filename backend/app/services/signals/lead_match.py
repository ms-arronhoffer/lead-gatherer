"""Fuzzy lead matching.

Used to attach visitor-pixel / signal events to an existing lead, and to catch
the same business discovered under slightly different names across sources.
Pure stdlib (``difflib``) so it adds no dependencies.
"""
from __future__ import annotations

import re
from difflib import SequenceMatcher
from urllib.parse import urlparse

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Lead

# Common company suffixes/noise stripped before comparison.
_SUFFIXES = {
    "inc", "incorporated", "llc", "ltd", "limited", "corp", "corporation",
    "co", "company", "group", "holdings", "plc", "gmbh", "sa", "ag", "the",
    "communications", "technologies", "technology", "networks", "systems",
}

_NON_ALNUM = re.compile(r"[^a-z0-9 ]+")


def normalize_company(name: str) -> str:
    """Lowercase, strip punctuation and common corporate suffix noise."""
    if not name:
        return ""
    base = _NON_ALNUM.sub(" ", name.lower())
    tokens = [t for t in base.split() if t and t not in _SUFFIXES]
    return " ".join(tokens)


def name_similarity(a: str, b: str) -> float:
    """0..1 similarity of two company names after normalization."""
    na, nb = normalize_company(a), normalize_company(b)
    if not na or not nb:
        return 0.0
    if na == nb:
        return 1.0
    return SequenceMatcher(None, na, nb).ratio()


def domain_of(website: str | None) -> str | None:
    if not website:
        return None
    host = urlparse(website if "//" in website else f"http://{website}").netloc.lower()
    return host.removeprefix("www.") or None


def phones_match(a: str | None, b: str | None) -> bool:
    if not a or not b:
        return False
    da = re.sub(r"\D", "", a)[-10:]
    db = re.sub(r"\D", "", b)[-10:]
    return bool(da) and da == db


async def find_matching_lead(
    session: AsyncSession,
    company_name: str,
    *,
    website: str | None = None,
    phone: str | None = None,
    threshold: float = 0.86,
) -> Lead | None:
    """Find the existing lead that best matches the given identity.

    Matching precedence: exact website domain, then phone (last 10 digits),
    then fuzzy normalized-name similarity at or above ``threshold``.
    """
    target_domain = domain_of(website)
    result = await session.execute(select(Lead))
    leads = list(result.scalars().all())

    # 1. Domain match — strongest signal.
    if target_domain:
        for lead in leads:
            if domain_of(lead.website) == target_domain:
                return lead

    # 2. Phone match.
    if phone:
        for lead in leads:
            if phones_match(lead.phone, phone):
                return lead

    # 3. Fuzzy name match — best above threshold.
    best: tuple[float, Lead] | None = None
    for lead in leads:
        score = name_similarity(company_name, lead.name)
        if score >= threshold and (best is None or score > best[0]):
            best = (score, lead)
    return best[1] if best else None
