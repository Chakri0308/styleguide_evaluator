"""arq worker settings: `arq stylelens.worker.settings.WorkerSettings`."""

from arq.connections import RedisSettings

from stylelens.config import get_settings
from stylelens.worker import tasks


class WorkerSettings:
    functions = [tasks.ingest_guide, tasks.compare_guides]
    redis_settings = RedisSettings.from_dsn(get_settings().redis_url)
    max_jobs = 4
    job_timeout = 60 * 60
    keep_result = 3600
