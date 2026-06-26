"""Arq task wrapper for LinkedIn enrichment.

Kept isolated from the main lead-gen pipeline because browser automation is slow
and must be serialized (LinkedIn punishes concurrency). Failures never crash the
worker — the orchestrator already fails soft — but we log a final activity-style
summary line for observability.
"""
from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


async def task_enrich_linkedin(ctx: dict, lead_id: str) -> None:
    from app.services.linkedin.enricher import enrich_lead

    try:
        stats = await enrich_lead(lead_id)
        logger.info("LinkedIn enrichment for %s: %s", lead_id, stats)
    except Exception as exc:  # noqa: BLE001 - best-effort background task
        logger.exception("LinkedIn enrichment task failed for %s: %s", lead_id, exc)
