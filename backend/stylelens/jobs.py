"""Job dispatch. "arq" sends jobs to the Redis-backed worker; "inline" runs them in-process (dev/tests)."""

import asyncio
import logging

from stylelens.config import get_settings

log = logging.getLogger(__name__)
_pool = None
_inline_tasks: set[asyncio.Task] = set()


async def _arq_pool():
    global _pool
    if _pool is None:
        from arq import create_pool
        from arq.connections import RedisSettings

        _pool = await create_pool(RedisSettings.from_dsn(get_settings().redis_url))
    return _pool


async def enqueue(job: str, *args) -> None:
    if get_settings().job_mode == "inline":
        from stylelens.worker import tasks

        fn = getattr(tasks, job)
        task = asyncio.create_task(fn({}, *args))
        _inline_tasks.add(task)
        task.add_done_callback(_inline_tasks.discard)
        return
    pool = await _arq_pool()
    await pool.enqueue_job(job, *args)


async def drain_inline() -> None:
    """Wait for in-process jobs (used by tests)."""
    while _inline_tasks:
        await asyncio.gather(*list(_inline_tasks), return_exceptions=True)
