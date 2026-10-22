"""API response/request models (exported to TypeScript via OpenAPI)."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict


class ORM(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class StageOut(BaseModel):
    status: str
    progress: float = 0.0
    message: str = ""
    started_at: str | None = None
    finished_at: str | None = None


class GuideVersionOut(ORM):
    id: str
    version: int
    status: str
    stages: dict[str, StageOut]
    error: str | None
    page_count: int
    title: str | None
    created_at: datetime
    finished_at: datetime | None


class GuideOut(ORM):
    id: str
    name: str
    role: str
    filename: str
    format: str
    mime_type: str
    size_bytes: int
    status: str
    created_at: datetime
    current_version_id: str | None
    current_version: GuideVersionOut | None = None


class IngestionStatus(BaseModel):
    guide_id: str
    version_id: str
    version: int
    status: str
    stages: dict[str, StageOut]
    error: str | None


class Region(BaseModel):
    page: int
    bbox: list[float] | None = None


class ChunkOut(BaseModel):
    id: str
    guide_id: str
    version_id: str
    kind: str
    text: str
    heading_path: list[str]
    page_start: int
    page_end: int
    regions: list[Region]
    image_url: str | None = None
    parent_id: str | None = None


class PageOut(BaseModel):
    page: int
    width: float
    height: float
    image_url: str | None
