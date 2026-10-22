"""Ingestion orchestrator: parsing → extracting → chunking → embedding → indexing.

Each stage reports progress to the GuideVersion row and to Redis pub/sub.
"""

import logging
import traceback
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime

from sqlalchemy.orm.attributes import flag_modified

from stylelens import events
from stylelens.db.models import Guide, GuideVersion
from stylelens.db.session import SessionLocal

log = logging.getLogger(__name__)


class StageReporter:
    def __init__(self, version_id: str):
        self.version_id = version_id

    async def update(self, stage: str, *, status: str | None = None, progress: float | None = None,
                     message: str | None = None, version_status: str | None = None,
                     error: str | None = None) -> None:
        async with SessionLocal() as session:
            version = await session.get(GuideVersion, self.version_id)
            if version is None:
                return
            st = dict(version.stages.get(stage, {"status": "pending", "progress": 0.0, "message": ""}))
            if status:
                st["status"] = status
                if status == "running" and "started_at" not in st:
                    st["started_at"] = events.now_iso()
                if status in ("done", "failed", "skipped"):
                    st["finished_at"] = events.now_iso()
                    if status == "done":
                        st["progress"] = 1.0
            if progress is not None:
                st["progress"] = round(max(0.0, min(1.0, progress)), 3)
            if message is not None:
                st["message"] = message
            version.stages = {**version.stages, stage: st}
            flag_modified(version, "stages")
            if version_status:
                version.status = version_status
                if version_status in ("ready", "failed"):
                    version.finished_at = datetime.now(UTC)
                    guide = await session.get(Guide, version.guide_id)
                    if guide and guide.current_version_id == version.id:
                        guide.status = version_status
            if error:
                version.error = error
            await session.commit()
            payload = {"version_id": version.id, "status": version.status,
                       "stage": stage, "stages": version.stages, "error": version.error}
        await events.publish("ingest", self.version_id, payload)


StageFn = Callable[[str, StageReporter], Awaitable[None]]


def stage_functions() -> list[tuple[str, StageFn]]:
    from stylelens.ingestion import stages

    return [
        ("parsing", stages.parse),
        ("extracting", stages.extract),
        ("chunking", stages.chunk),
        ("embedding", stages.embed),
        ("indexing", stages.index),
    ]


async def run_ingestion(version_id: str) -> None:
    reporter = StageReporter(version_id)
    current = "parsing"
    try:
        for name, fn in stage_functions():
            current = name
            await reporter.update(name, status="running", version_status="processing")
            await fn(version_id, reporter)
            await reporter.update(name, status="done")
        await reporter.update("indexing", version_status="ready")
    except Exception as exc:  # noqa: BLE001
        log.exception("ingestion failed for %s", version_id)
        await reporter.update(current, status="failed", message=str(exc)[:500],
                              version_status="failed", error=f"{type(exc).__name__}: {exc}")
        log.debug(traceback.format_exc())
