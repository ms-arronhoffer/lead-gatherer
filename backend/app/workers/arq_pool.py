"""Singleton Arq Redis pool used by the API process to enqueue jobs."""
from __future__ import annotations

from arq import create_pool
from arq.connections import ArqRedis

from app.workers.arq_settings import _redis_settings

_pool: ArqRedis | None = None


async def get_pool() -> ArqRedis:
    global _pool
    if _pool is None:
        _pool = await create_pool(_redis_settings())
    return _pool


async def close_pool() -> None:
    global _pool
    if _pool is not None:
        await _pool.close()
        _pool = None


async def enqueue_pipeline(job_id: str) -> None:
    pool = await get_pool()
    # Use job_id as the Arq job_id too — guarantees no duplicate enqueue
    # for the same lead-gen job (e.g. on retry after a stuck-job sweep).
    await pool.enqueue_job("task_run_pipeline", job_id, _job_id=f"pipeline:{job_id}")


async def enqueue_enrich(lead_id: str) -> bool:
    """Enqueue ad-hoc re-enrichment for a single lead. Returns False if a job
    for this lead is already enqueued/running (dedupe by lead_id)."""
    pool = await get_pool()
    job = await pool.enqueue_job(
        "task_enrich_lead", lead_id, _job_id=f"enrich:{lead_id}"
    )
    return job is not None


async def enqueue_linkedin_enrich(lead_id: str) -> bool:
    """Enqueue LinkedIn enrichment for a single lead. Returns False if a job for
    this lead is already enqueued/running (dedupe by lead_id)."""
    pool = await get_pool()
    job = await pool.enqueue_job(
        "task_enrich_linkedin", lead_id, _job_id=f"linkedin:{lead_id}"
    )
    return job is not None


async def abort_pipeline(job_id: str) -> bool:
    """Abort an in-flight pipeline task. Returns True if abort signal sent."""
    pool = await get_pool()
    try:
        return bool(await pool.abort_job(f"pipeline:{job_id}", timeout=0))
    except Exception:
        return False
