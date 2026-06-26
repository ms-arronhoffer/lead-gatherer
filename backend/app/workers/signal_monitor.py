"""Periodic buying-signal monitor.

Arq cron that re-checks a bounded batch of active leads for fresh news-based
buying signals. Complements the one-shot detection that runs during scraping:
funding rounds, hires, expansions, etc. happen *after* a lead is first ingested,
so we keep re-checking the accounts the team actually cares about.

No-ops cheaply when news enrichment or the LLM is not configured, so it is safe
to leave scheduled in every environment.
"""
from __future__ import annotations

import logging
from typing import Any

from sqlalchemy import select

from app.config import settings
from app.db import AsyncSessionLocal
from app.models import Lead
from app.services import llm_client
from app.services.enrichment.news_enricher import search_configured

logger = logging.getLogger(__name__)

# Statuses worth monitoring — skip rejected/closed leads.
_ACTIVE_STATUSES = ("new", "contacted", "qualified")
# How many leads to check per run (keeps LLM/search cost bounded).
_BATCH = 25


async def task_monitor_signals(ctx: dict[str, Any]) -> None:
    if not settings.enable_news_enrichment:
        return
    if not search_configured() or not llm_client.is_configured():
        return

    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(Lead.id, Lead.name, Lead.city, Lead.state)
            .where(Lead.status.in_(_ACTIVE_STATUSES))
            .order_by(Lead.priority_score.desc().nullslast(), Lead.updated_at.desc())
            .limit(_BATCH)
        )
        rows = [(r.id, r.name, r.city or r.state or "") for r in result]

    if not rows:
        return

    # Imported lazily so the worker module stays import-light.
    from app.services.signals.news_signals import detect_and_record

    total = 0
    for lead_id, name, location in rows:
        try:
            total += await detect_and_record(lead_id, name, location)
        except Exception as exc:  # noqa: BLE001
            logger.warning("Signal monitor failed for %s: %s", lead_id, exc)
    if total:
        logger.info("Signal monitor recorded %d new signals across %d leads", total, len(rows))
