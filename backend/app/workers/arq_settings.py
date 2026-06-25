import logging
import time
from typing import Any

from arq import cron
from arq.connections import RedisSettings

from app.config import settings
from app.db import AsyncSessionLocal
from app.models import Job
from app.workers.reply_poller import task_poll_replies
from app.workers.sequence_sender import task_send_sequence_batch
from app.workers.visitor_resolver import task_resolve_visitors

logger = logging.getLogger(__name__)


def _redis_settings() -> RedisSettings:
    return RedisSettings.from_dsn(settings.redis_url)


async def task_enrich_lead(ctx: dict, lead_id: str) -> None:
    """Ad-hoc re-enrichment for an existing lead. Re-runs scrape + LLM brief +
    contact extraction + email verify + scoring + fit_reasons."""
    from app.models import Lead
    from app.services.scraper_service import scrape_lead
    async with AsyncSessionLocal() as session:
        lead = await session.get(Lead, lead_id)
        website = lead.website if lead else None
    if not website:
        logger.warning("Enrich skipped for %s: no website", lead_id)
        return
    try:
        await scrape_lead(lead_id, website)
    except Exception as exc:
        logger.exception("Enrich failed for %s: %s", lead_id, exc)
        raise


async def task_run_pipeline(ctx: dict, job_id: str) -> None:
    """Arq task wrapper. Pipeline itself reads Job.checkpoint to resume."""
    import asyncio
    from app.workers.pipeline import run_pipeline
    try:
        await run_pipeline(job_id)
    except asyncio.CancelledError:
        logger.info("Job %s aborted via Arq", job_id)
        async with AsyncSessionLocal() as session:
            job = await session.get(Job, job_id)
            if job and job.status not in ("completed", "failed"):
                job.status = "cancelled"
                job.updated_at = int(time.time())
                await session.commit()
        raise
    except Exception as exc:
        logger.exception("Job %s failed: %s", job_id, exc)
        async with AsyncSessionLocal() as session:
            job = await session.get(Job, job_id)
            if job and job.status != "cancelled":
                job.status = "failed"
                job.error_message = str(exc)[:1000]
                job.updated_at = int(time.time())
                await session.commit()
        # Arq will retry per WorkerSettings.max_tries
        raise


class WorkerSettings:
    functions: list[Any] = [
        task_run_pipeline,
        task_enrich_lead,
        task_resolve_visitors,
        task_send_sequence_batch,
        task_poll_replies,
    ]
    cron_jobs = [
        cron(task_resolve_visitors, minute={0, 5, 10, 15, 20, 25, 30, 35, 40, 45, 50, 55}),
        cron(task_send_sequence_batch, minute=set(range(0, 60))),  # every minute
        cron(task_poll_replies, minute={0, 10, 20, 30, 40, 50}),
    ]
    redis_settings = _redis_settings()
    max_tries = 3                     # 1 try + 2 retries on failure
    job_timeout = 60 * 60             # 1h per attempt
    keep_result = 3600                # keep result in redis for 1h for debugging
    max_jobs = 4                      # concurrent pipelines per worker
    health_check_interval = 60
    allow_abort_jobs = True           # required for pool.abort_job(...) to work
