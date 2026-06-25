import asyncio
import logging
from contextlib import asynccontextmanager

from arq.worker import create_worker
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import select

from app.config import settings
from app.db import init_db, AsyncSessionLocal
from app.models import Job
from app.routes import candidates, health, jobs, leads, me, pixel, segments, sequences, tags, users, webhooks, ws
from app.workers.arq_pool import close_pool, enqueue_pipeline, get_pool
from app.workers.arq_settings import WorkerSettings

logging.basicConfig(level=settings.log_level)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()

    # Initialize Arq pool used by the API to enqueue work.
    await get_pool()

    # Start the Arq worker in-process so it shares the WebSocket
    # ConnectionManager with the API and can broadcast progress.
    arq_worker = create_worker(WorkerSettings, handle_signals=False)
    worker_task = asyncio.create_task(arq_worker.async_run())
    logger.info("Arq worker started (in-process)")

    # Re-enqueue any jobs that were interrupted on the previous run.
    # The pipeline reads Job.checkpoint and resumes mid-flight.
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(Job).where(Job.status.in_(["pending", "running"]))
        )
        stuck_jobs = result.scalars().all()
        for job in stuck_jobs:
            job.status = "pending"
        await session.commit()

    for job in stuck_jobs:
        await enqueue_pipeline(job.id)
    if stuck_jobs:
        logger.info("Re-enqueued %d interrupted jobs", len(stuck_jobs))

    from app.services.webhook_dispatcher import run_dispatcher_loop
    dispatcher_task = asyncio.create_task(run_dispatcher_loop())
    logger.info("Webhook dispatcher started")

    yield

    await arq_worker.close()
    dispatcher_task.cancel()
    worker_task.cancel()
    for t in (worker_task, dispatcher_task):
        try:
            await t
        except asyncio.CancelledError:
            pass
    await close_pool()
    logger.info("Background tasks stopped")


app = FastAPI(title="Lead Gatherer API", version="1.0.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health.router, prefix="/api/v1", tags=["system"])
app.include_router(me.router, prefix="/api/v1/me", tags=["me"])
app.include_router(users.router, prefix="/api/v1/users", tags=["users"])
app.include_router(jobs.router, prefix="/api/v1/jobs", tags=["jobs"])
app.include_router(leads.router, prefix="/api/v1/leads", tags=["leads"])
app.include_router(candidates.router, prefix="/api/v1/candidates", tags=["candidates"])
app.include_router(segments.router, prefix="/api/v1/segments", tags=["segments"])
app.include_router(tags.router, prefix="/api/v1/tags", tags=["tags"])
app.include_router(webhooks.router, prefix="/api/v1/webhooks", tags=["webhooks"])
app.include_router(pixel.router, prefix="/api/v1/pixel", tags=["pixel"])
app.include_router(sequences.router, prefix="/api/v1/sequences", tags=["sequences"])
app.add_api_websocket_route("/api/v1/ws/jobs/{job_id}", ws.ws_job_progress)
