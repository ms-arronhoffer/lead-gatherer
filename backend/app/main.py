import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import select

from app.config import settings
from app.db import init_db, AsyncSessionLocal
from app.models import Job
from app.routes import health, jobs, leads, ws

logging.basicConfig(level=settings.log_level)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()

    # Re-enqueue any jobs that were interrupted on the previous run
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(Job).where(Job.status.in_(["pending", "running"]))
        )
        stuck_jobs = result.scalars().all()
        for job in stuck_jobs:
            job.status = "pending"
        await session.commit()

    from app.workers.job_runner import enqueue, start_worker
    for job in stuck_jobs:
        await enqueue(job.id)

    worker_task = asyncio.create_task(start_worker())
    logger.info("Background worker started")

    yield

    worker_task.cancel()
    try:
        await worker_task
    except asyncio.CancelledError:
        pass
    logger.info("Background worker stopped")


app = FastAPI(title="Lead Gatherer API", version="1.0.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health.router, prefix="/api/v1", tags=["system"])
app.include_router(jobs.router, prefix="/api/v1/jobs", tags=["jobs"])
app.include_router(leads.router, prefix="/api/v1/leads", tags=["leads"])
app.add_api_websocket_route("/api/v1/ws/jobs/{job_id}", ws.ws_job_progress)
