"""DEPRECATED — replaced by Arq-backed queue.

The in-memory asyncio.Queue worker that used to live here was replaced
by ``app.workers.arq_settings`` (worker) and ``app.workers.arq_pool``
(enqueue side). Importing from this module will raise.
"""
raise ImportError(
    "app.workers.job_runner has been removed. "
    "Use app.workers.arq_pool.enqueue_pipeline to enqueue jobs."
)
