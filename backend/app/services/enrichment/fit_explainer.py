"""LLM-generated rationale for why a lead matches a segment.

Runs after scoring during the scrape pipeline. For each segment the lead matched,
asks the LLM for a 1-sentence "why this fits" rationale grounded in the lead's
brief + segment description. Output is cached on `Lead.fit_reasons` as a list of
`{segment_id, segment_name, rationale}` dicts so the UI can render it without
re-prompting.

Skipped on assignment-change rescores (no new signal, just cost).
"""
from __future__ import annotations

import logging

from app.models import Lead, Segment
from app.services import llm_client

logger = logging.getLogger(__name__)

_SYSTEM = (
    "You explain to a B2B salesperson why a specific lead matches a specific "
    "buyer segment. Use ONLY facts present in the provided lead context — do "
    "not invent details. One sentence. No hedging, no marketing language. "
    "Return ONLY the rationale as plain text."
)


def _lead_context(lead: Lead) -> str:
    parts = [f"Company: {lead.name}"]
    if lead.summary:
        parts.append(f"Brief: {lead.summary}")
    if lead.place_types:
        parts.append(f"Category: {', '.join(lead.place_types[:3])}")
    loc = ", ".join(p for p in (lead.city, lead.state) if p)
    if loc:
        parts.append(f"Location: {loc}")
    if lead.website:
        parts.append(f"Website: {lead.website}")
    if lead.employee_count_min or lead.employee_count_max:
        parts.append(
            f"Employees: {lead.employee_count_min or '?'}–{lead.employee_count_max or '?'}"
        )
    if lead.revenue_range:
        parts.append(f"Revenue range: {lead.revenue_range}")
    verified = [e.email for e in lead.emails if e.smtp_verified or e.mx_valid]
    if verified:
        parts.append(f"Verified emails: {len(verified)}")
    return "\n".join(parts)


async def _explain_one(lead: Lead, segment: Segment) -> str:
    user = (
        f"{_lead_context(lead)}\n\n"
        f"Segment name: {segment.name}\n"
        f"Segment description: {segment.description or '(none)'}\n"
        f"Segment rules: {segment.rules}\n\n"
        "Return ONLY the one-sentence rationale."
    )
    try:
        result = await llm_client.complete(
            [{"role": "system", "content": _SYSTEM}, {"role": "user", "content": user}],
            schema=None,
            max_tokens=120,
        )
    except Exception as exc:
        logger.warning("Fit explainer LLM failed for segment %s: %s", segment.id, exc)
        return ""
    if isinstance(result, dict):
        text = result.get("text", "")
        return text.strip() if isinstance(text, str) else ""
    if isinstance(result, str):
        return result.strip()
    return ""


async def explain_matches(lead: Lead, matched_segments: list[Segment]) -> list[dict]:
    if not llm_client.is_configured() or not matched_segments:
        return []
    out: list[dict] = []
    for seg in matched_segments:
        rationale = await _explain_one(lead, seg)
        if rationale:
            out.append({"segment_id": seg.id, "segment_name": seg.name, "rationale": rationale})
    return out
