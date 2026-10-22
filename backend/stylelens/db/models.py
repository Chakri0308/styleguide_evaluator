"""SQLAlchemy ORM models.

Versioning: every (re-)ingestion of a guide creates a new GuideVersion. Elements, chunks and the
style profile hang off the version, never the guide, so re-ingesting never mutates an index silently.
"""

import uuid
from datetime import datetime

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    Computed,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, TSVECTOR
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

from stylelens.config import get_settings

EMBED_DIM = get_settings().embedding_dim


def new_id() -> str:
    return uuid.uuid4().hex


class Base(DeclarativeBase):
    pass


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Guide(TimestampMixin, Base):
    __tablename__ = "guides"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    name: Mapped[str] = mapped_column(String(300))
    # "reference" (source of truth) or "candidate" (document being checked)
    role: Mapped[str] = mapped_column(String(20), index=True)
    filename: Mapped[str] = mapped_column(String(500))
    mime_type: Mapped[str] = mapped_column(String(200))
    format: Mapped[str] = mapped_column(String(20))
    size_bytes: Mapped[int] = mapped_column(Integer)
    sha256: Mapped[str] = mapped_column(String(64), index=True)
    storage_key: Mapped[str] = mapped_column(String(500))
    status: Mapped[str] = mapped_column(String(20), default="uploaded")
    current_version_id: Mapped[str | None] = mapped_column(String(32), nullable=True)

    versions: Mapped[list["GuideVersion"]] = relationship(
        back_populates="guide", cascade="all, delete-orphan", order_by="GuideVersion.version"
    )


class GuideVersion(TimestampMixin, Base):
    __tablename__ = "guide_versions"
    __table_args__ = (UniqueConstraint("guide_id", "version"),)

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    guide_id: Mapped[str] = mapped_column(ForeignKey("guides.id", ondelete="CASCADE"), index=True)
    version: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(20), default="queued")
    # {stage: {status, progress, message, started_at, finished_at}}
    stages: Mapped[dict] = mapped_column(JSONB, default=dict)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    page_count: Mapped[int] = mapped_column(Integer, default=0)
    title: Mapped[str | None] = mapped_column(String(500), nullable=True)
    # Pinned model identifiers used to build this index (part of every cache key)
    embedding_model: Mapped[str | None] = mapped_column(String(200), nullable=True)
    parser: Mapped[str | None] = mapped_column(String(100), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    guide: Mapped[Guide] = relationship(back_populates="versions")


class Page(Base):
    __tablename__ = "pages"
    __table_args__ = (UniqueConstraint("version_id", "page"),)

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    version_id: Mapped[str] = mapped_column(ForeignKey("guide_versions.id", ondelete="CASCADE"))
    page: Mapped[int] = mapped_column(Integer)  # 1-based
    width: Mapped[float] = mapped_column(Float)
    height: Mapped[float] = mapped_column(Float)
    image_key: Mapped[str | None] = mapped_column(String(500), nullable=True)  # rendered preview


class Element(Base):
    """A layout element produced by a parser: heading, paragraph, list item, table, image, ..."""

    __tablename__ = "elements"

    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    version_id: Mapped[str] = mapped_column(
        ForeignKey("guide_versions.id", ondelete="CASCADE"), index=True
    )
    seq: Mapped[int] = mapped_column(Integer)  # document order
    page: Mapped[int] = mapped_column(Integer)
    bbox: Mapped[list[float] | None] = mapped_column(ARRAY(Float), nullable=True)  # x0,y0,x1,y1 pts
    type: Mapped[str] = mapped_column(String(30))
    heading_path: Mapped[list[str]] = mapped_column(ARRAY(Text), default=list)
    level: Mapped[int | None] = mapped_column(Integer, nullable=True)
    text: Mapped[str] = mapped_column(Text, default="")
    meta: Mapped[dict] = mapped_column(JSONB, default=dict)
    image_key: Mapped[str | None] = mapped_column(String(500), nullable=True)


class Chunk(Base):
    __tablename__ = "chunks"
    __table_args__ = (
        Index("ix_chunks_tsv", "tsv", postgresql_using="gin"),
        Index("ix_chunks_version_kind", "version_id", "kind"),
    )

    # Deterministic id: hash(version_id, element ids, kind) so citations are stable per version
    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    version_id: Mapped[str] = mapped_column(ForeignKey("guide_versions.id", ondelete="CASCADE"))
    kind: Mapped[str] = mapped_column(String(10))  # parent | child | image
    parent_id: Mapped[str | None] = mapped_column(String(40), nullable=True, index=True)
    seq: Mapped[int] = mapped_column(Integer)
    heading_path: Mapped[list[str]] = mapped_column(ARRAY(Text), default=list)
    category: Mapped[str | None] = mapped_column(String(40), nullable=True)
    text: Mapped[str] = mapped_column(Text)
    context_header: Mapped[str] = mapped_column(Text, default="")
    page_start: Mapped[int] = mapped_column(Integer)
    page_end: Mapped[int] = mapped_column(Integer)
    # [{page, bbox:[x0,y0,x1,y1]}] for highlight overlays
    regions: Mapped[list] = mapped_column(JSONB, default=list)
    element_ids: Mapped[list[str]] = mapped_column(ARRAY(Text), default=list)
    token_count: Mapped[int] = mapped_column(Integer, default=0)
    image_key: Mapped[str | None] = mapped_column(String(500), nullable=True)
    embedding: Mapped[list[float] | None] = mapped_column(Vector(EMBED_DIM), nullable=True)
    tsv = mapped_column(
        TSVECTOR,
        Computed("to_tsvector('english', coalesce(context_header,'') || ' ' || text)", persisted=True),
    )


class StyleProfile(TimestampMixin, Base):
    __tablename__ = "style_profiles"

    version_id: Mapped[str] = mapped_column(
        ForeignKey("guide_versions.id", ondelete="CASCADE"), primary_key=True
    )
    data: Mapped[dict] = mapped_column(JSONB)


class Comparison(TimestampMixin, Base):
    __tablename__ = "comparisons"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    reference_version_id: Mapped[str] = mapped_column(ForeignKey("guide_versions.id"))
    candidate_version_id: Mapped[str] = mapped_column(ForeignKey("guide_versions.id"))
    status: Mapped[str] = mapped_column(String(20), default="queued")
    stages: Mapped[dict] = mapped_column(JSONB, default=dict)
    score: Mapped[float | None] = mapped_column(Float, nullable=True)
    summary: Mapped[dict] = mapped_column(JSONB, default=dict)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    findings: Mapped[list["Finding"]] = relationship(
        back_populates="comparison", cascade="all, delete-orphan", order_by="Finding.seq"
    )


class Finding(Base):
    __tablename__ = "findings"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    comparison_id: Mapped[str] = mapped_column(
        ForeignKey("comparisons.id", ondelete="CASCADE"), index=True
    )
    seq: Mapped[int] = mapped_column(Integer)
    finding_id: Mapped[str] = mapped_column(String(80))
    category: Mapped[str] = mapped_column(String(40))
    status: Mapped[str] = mapped_column(String(20))
    severity: Mapped[str] = mapped_column(String(20))
    method: Mapped[str] = mapped_column(String(20))  # deterministic | llm | visual
    summary: Mapped[str] = mapped_column(Text)
    reasoning: Mapped[str] = mapped_column(Text, default="")
    reference_citations: Mapped[list] = mapped_column(JSONB, default=list)
    candidate_citations: Mapped[list] = mapped_column(JSONB, default=list)
    confidence: Mapped[float] = mapped_column(Float, default=0.0)
    data: Mapped[dict] = mapped_column(JSONB, default=dict)

    comparison: Mapped[Comparison] = relationship(back_populates="findings")


class Conversation(TimestampMixin, Base):
    __tablename__ = "conversations"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    guide_id: Mapped[str] = mapped_column(ForeignKey("guides.id", ondelete="CASCADE"), index=True)
    comparison_id: Mapped[str | None] = mapped_column(String(32), nullable=True)
    title: Mapped[str | None] = mapped_column(String(300), nullable=True)


class Message(TimestampMixin, Base):
    __tablename__ = "messages"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    conversation_id: Mapped[str] = mapped_column(
        ForeignKey("conversations.id", ondelete="CASCADE"), index=True
    )
    role: Mapped[str] = mapped_column(String(20))
    content: Mapped[str] = mapped_column(Text)
    citations: Mapped[list] = mapped_column(JSONB, default=list)
    meta: Mapped[dict] = mapped_column(JSONB, default=dict)


class Feedback(TimestampMixin, Base):
    __tablename__ = "feedback"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    message_id: Mapped[str] = mapped_column(ForeignKey("messages.id", ondelete="CASCADE"))
    rating: Mapped[int] = mapped_column(Integer)  # +1 / -1
    comment: Mapped[str | None] = mapped_column(Text, nullable=True)


class CacheEntry(TimestampMixin, Base):
    """Content-addressed cache for embeddings-of-queries, retrieval results and LLM responses."""

    __tablename__ = "cache_entries"

    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    namespace: Mapped[str] = mapped_column(String(40), index=True)
    value: Mapped[dict] = mapped_column(JSONB)
