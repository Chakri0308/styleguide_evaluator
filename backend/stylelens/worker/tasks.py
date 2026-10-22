"""Background job entrypoints. Each takes the arq context dict as first argument."""

from stylelens.ingestion.pipeline import run_ingestion


async def ingest_guide(ctx: dict, version_id: str) -> None:
    await run_ingestion(version_id)
