"""Progress events: persisted on the job row and broadcast over Redis pub/sub for live SSE streams."""

import json
from datetime import UTC, datetime

from redis.asyncio import Redis

from stylelens.config import get_settings

INGEST_STAGES = ["parsing", "extracting", "chunking", "embedding", "indexing"]
COMPARE_STAGES = ["aligning", "deterministic_checks", "visual_checks", "judging", "scoring"]

_redis: Redis | None = None


def redis() -> Redis:
    global _redis
    if _redis is None:
        _redis = Redis.from_url(get_settings().redis_url, decode_responses=True)
    return _redis


def channel(kind: str, obj_id: str) -> str:
    return f"progress:{kind}:{obj_id}"


def initial_stages(names: list[str]) -> dict:
    return {n: {"status": "pending", "progress": 0.0, "message": ""} for n in names}


def now_iso() -> str:
    return datetime.now(UTC).isoformat()


async def publish(kind: str, obj_id: str, payload: dict) -> None:
    try:
        await redis().publish(channel(kind, obj_id), json.dumps(payload))
    except Exception:  # progress is best-effort; the DB row stays authoritative
        pass
