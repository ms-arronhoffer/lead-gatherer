import asyncio
import logging
import time

from sqlalchemy import select

from app.db import AsyncSessionLocal
from app.models import Job

logger = logging.getLogger(__name__)

_job_queue: asyncio.Queue[str] = asyncio.Queue()


async def enqueue(job_id: str) -> None:
    await _job_queue.put(job_id)


async def start_worker() -> None:
    while True:
        job_id = await _job_queue.get()
        try:
            from app.workers.pipeline import run_pipeline
            await run_pipeline(job_id)
        except asyncio.CancelledError:
            await _mark(job_id, "cancelled")
            raise
        except Exception as exc:
            logger.exception("Job %s failed: %s", job_id, exc)
            await _mark(job_id, "failed", str(exc))
        finally:
            _job_queue.task_done()


async def _mark(job_id: str, status: str, error: str | None = None) -> None:
    async with AsyncSessionLocal() as session:
        job = await session.get(Job, job_id)
        if job:
            job.status = status
            job.error_message = error
            job.updated_at = int(time.time())
            await session.commit()
