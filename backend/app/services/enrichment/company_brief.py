"""LLM-generated company brief — short summary of what a company does.

Runs once per scrape, alongside contact extraction. Output is cached on
`Lead.summary` and surfaced in the lead detail UI.
"""
from __future__ import annotations

import logging

from app.services import llm_client

logger = logging.getLogger(__name__)

_SYSTEM = (
    "You are a B2B sales researcher. Given a company name and text scraped from "
    "their website, write a tight 2-3 sentence brief covering: (1) what the "
    "company does and who they sell to, (2) signals of size/maturity (years in "
    "business, locations, team size, notable clients) when present, (3) any "
    "explicit value proposition. No filler, no hedging, no marketing language. "
    "Return ONLY the brief as plain text."
)


async def generate_brief(company_name: str, page_text: str) -> str:
    if not llm_client.is_configured():
        return ""
    if not page_text.strip():
        return ""
    user = (
        f"Company: {company_name}\n\nWebsite text (truncated):\n{page_text[:8000]}\n\n"
        "Return ONLY the brief."
    )
    try:
        result = await llm_client.complete(
            [{"role": "system", "content": _SYSTEM}, {"role": "user", "content": user}],
            schema=None,
            max_tokens=250,
        )
    except Exception as exc:
        logger.warning("Company brief LLM failed: %s", exc)
        return ""
    if isinstance(result, dict):
        text = result.get("text", "")
        return text.strip() if isinstance(text, str) else ""
    if isinstance(result, str):
        return result.strip()
    return ""
