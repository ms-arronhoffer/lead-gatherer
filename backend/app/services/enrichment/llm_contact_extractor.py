"""LLM-driven contact extraction (F2).

Feeds scraped HTML/text from a lead's website into the configured LLM with a
structured-output schema. Returns a list of `{name, title, email, confidence}`
items the caller can filter and persist.
"""
from __future__ import annotations

import logging

from app.services import llm_client

logger = logging.getLogger(__name__)

_SCHEMA = {
    "type": "object",
    "properties": {
        "contacts": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                    "title": {"type": "string"},
                    "email": {"type": "string"},
                    "confidence": {"type": "number", "minimum": 0, "maximum": 1},
                },
                "required": ["confidence"],
            },
        }
    },
    "required": ["contacts"],
}

_SYSTEM = (
    "Extract real human contacts (named people, not departments) from the page text. "
    "For each contact, provide name, title, email when present, and confidence (0-1) "
    "that this is a real person at this company in this role. Skip generic role "
    "inboxes like info@/sales@/support@. Return JSON matching the schema."
)


async def extract_contacts(company_name: str, page_text: str) -> list[dict]:
    if not llm_client.is_configured():
        return []
    user = (
        f"Company: {company_name}\n\nPage text (truncated):\n{page_text[:8000]}\n\n"
        "Return ONLY the JSON object."
    )
    try:
        result = await llm_client.complete(
            [{"role": "system", "content": _SYSTEM}, {"role": "user", "content": user}],
            schema=_SCHEMA,
            max_tokens=800,
        )
    except Exception as exc:
        logger.warning("LLM contact extract failed: %s", exc)
        return []
    if not isinstance(result, dict):
        return []
    items = result.get("contacts")
    if not isinstance(items, list):
        return []
    return [c for c in items if isinstance(c, dict)]
