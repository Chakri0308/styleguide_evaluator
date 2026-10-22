"""Ingestion stage implementations (filled in milestone by milestone)."""

from stylelens.ingestion.pipeline import StageReporter


async def parse(version_id: str, r: StageReporter) -> None:
    await r.update("parsing", message="Parser not implemented yet")


async def extract(version_id: str, r: StageReporter) -> None:
    pass


async def chunk(version_id: str, r: StageReporter) -> None:
    pass


async def embed(version_id: str, r: StageReporter) -> None:
    pass


async def index(version_id: str, r: StageReporter) -> None:
    pass
