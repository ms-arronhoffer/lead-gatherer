"""LLM-driven sequence personalization (F3).

Takes a template body and a lead, and asks the LLM to rewrite the first
1-2 sentences into a tailored opener referencing the lead's company,
category, and website summary. The rest of the template is preserved.
"""
from __future__ import annotations

import logging

from app.models import Lead
from app.services import llm_client

logger = logging.getLogger(__name__)

_SYSTEM = (
    "You write 1-2 sentence personalized openers for B2B outreach emails. "
    "Reference the recipient's company, category, or distinctive detail "
    "naturally. Do NOT mention you used AI. Do NOT use exclamation marks. "
    "Return ONLY the opener as plain text — no preamble, no quotes."
)


async def personalize_opener(lead: Lead, template_body: str) -> str:
    """Return a tailored opener line. Falls back to template if LLM unavailable."""
    if not llm_client.is_configured():
        return ""
    parts = [f"Company: {lead.name}"]
    if lead.place_types:
        parts.append(f"Category: {', '.join(lead.place_types[:3])}")
    if lead.city or lead.state:
        loc = ", ".join(p for p in (lead.city, lead.state) if p)
        parts.append(f"Location: {loc}")
    if lead.website:
        parts.append(f"Website: {lead.website}")
    if lead.notes:
        parts.append(f"Notes: {lead.notes[:400]}")
    parts.append(f"\nOriginal template (for tone reference):\n{template_body[:600]}")
    user = "\n".join(parts)
    try:
        opener = await llm_client.complete(
            [{"role": "system", "content": _SYSTEM}, {"role": "user", "content": user}],
            schema=None,
            max_tokens=200,
        )
    except Exception as exc:
        logger.warning("Personalizer LLM failed: %s", exc)
        return ""
    if isinstance(opener, str):
        return opener.strip()
    return ""


def render_template(template: str, lead: Lead, opener: str = "") -> str:
    """Naive Mustache-ish renderer: {{lead.name}}, {{lead.city}}, {{opener}}."""
    out = template
    replacements = {
        "{{opener}}": opener,
        "{{lead.name}}": lead.name or "",
        "{{lead.website}}": lead.website or "",
        "{{lead.city}}": lead.city or "",
        "{{lead.state}}": lead.state or "",
        "{{lead.category}}": (lead.place_types[0] if lead.place_types else ""),
    }
    for token, value in replacements.items():
        out = out.replace(token, value)
    return out
