"""Ingestion stage implementations."""

import asyncio
import time

from sqlalchemy import delete

from stylelens.db.models import Element, Guide, GuideVersion, Page
from stylelens.db.session import SessionLocal
from stylelens.ingestion.parsers import get_parser
from stylelens.ingestion.parsers.base import assign_heading_paths
from stylelens.ingestion.pipeline import StageReporter
from stylelens.storage import aget, aput


def thread_progress(reporter: StageReporter, stage: str, loop: asyncio.AbstractEventLoop, every: float = 0.4):
    """Progress callback usable from worker threads; throttled to avoid flooding the DB."""
    last = [0.0]

    def cb(fraction: float, message: str) -> None:
        now = time.monotonic()
        if now - last[0] < every and fraction < 1.0:
            return
        last[0] = now
        asyncio.run_coroutine_threadsafe(reporter.update(stage, progress=fraction, message=message), loop)

    return cb


def element_id(version_id: str, seq: int) -> str:
    return f"{version_id[:24]}e{seq:05d}"


def asset_prefix(guide_id: str, version_id: str) -> str:
    return f"guides/{guide_id}/v/{version_id}"


async def parse(version_id: str, r: StageReporter) -> None:
    async with SessionLocal() as session:
        version = await session.get(GuideVersion, version_id)
        guide = await session.get(Guide, version.guide_id)
        fmt, key, filename, guide_id = guide.format, guide.storage_key, guide.filename, guide.id

    data = await aget(key)
    parser = get_parser(fmt)
    await r.update("parsing", message=f"Reading {filename} with {parser.name}")
    loop = asyncio.get_running_loop()
    doc = await asyncio.to_thread(parser.parse, data, filename, thread_progress(r, "parsing", loop))
    paths = assign_heading_paths(doc.elements)
    prefix = asset_prefix(guide_id, version_id)

    # Upload page renders and element images
    page_rows = []
    for p in doc.pages:
        image_key = None
        if p.render:
            image_key = f"{prefix}/pages/{p.page:04d}.png"
            await aput(image_key, p.render, "image/png")
        page_rows.append(Page(version_id=version_id, page=p.page, width=p.width, height=p.height, image_key=image_key))

    element_rows = []
    for seq, (el, path) in enumerate(zip(doc.elements, paths, strict=True)):
        eid = element_id(version_id, seq)
        image_key = None
        if el.image:
            ext = (el.image_ext or "png").lower().replace("jpeg", "jpg")
            image_key = f"{prefix}/images/{eid}.{ext}"
            await aput(image_key, el.image, f"image/{'jpeg' if ext == 'jpg' else ext}")
        element_rows.append(Element(
            id=eid, version_id=version_id, seq=seq, page=el.page,
            bbox=[float(v) for v in el.bbox] if el.bbox else None,
            type=el.type, heading_path=path, level=el.level, text=el.text, meta=el.meta, image_key=image_key,
        ))

    async with SessionLocal() as session:
        await session.execute(delete(Element).where(Element.version_id == version_id))
        await session.execute(delete(Page).where(Page.version_id == version_id))
        session.add_all(page_rows)
        session.add_all(element_rows)
        version = await session.get(GuideVersion, version_id)
        version.page_count = len(doc.pages)
        version.title = (doc.title or "")[:500] or None
        version.parser = doc.parser
        version.meta = _jsonable(doc.meta)
        await session.commit()
    await r.update("parsing", message=f"{len(element_rows)} elements from {len(doc.pages)} page(s)")


def _jsonable(meta: dict) -> dict:
    out = {}
    for k, v in meta.items():
        if isinstance(v, (str, int, float, bool, list, dict)) or v is None:
            out[k] = v
    return out


async def extract(version_id: str, r: StageReporter) -> None:
    from stylelens.db.models import StyleProfile as ProfileRow
    from stylelens.extraction.profile import build_profile

    async def progress(fraction: float, message: str) -> None:
        await r.update("extracting", progress=fraction, message=message)

    profile = await build_profile(version_id, progress)
    async with SessionLocal() as session:
        row = await session.get(ProfileRow, version_id)
        data = profile.model_dump(mode="json")
        if row is None:
            session.add(ProfileRow(version_id=version_id, data=data))
        else:
            row.data = data
        await session.commit()


async def chunk(version_id: str, r: StageReporter) -> None:
    from sqlalchemy import select

    from stylelens.db.models import Chunk
    from stylelens.db.models import StyleProfile as ProfileRow
    from stylelens.extraction.common import from_row
    from stylelens.retrieval.chunking import build_chunks

    async with SessionLocal() as session:
        version = await session.get(GuideVersion, version_id)
        rows = list(await session.scalars(
            select(Element).where(Element.version_id == version_id).order_by(Element.seq)))
        profile = await session.get(ProfileRow, version_id)
        title = version.title
    images = {i["element_id"]: i for i in (profile.data.get("images", []) if profile else [])}
    drafts = build_chunks(version_id, title, [from_row(x) for x in rows], images)
    async with SessionLocal() as session:
        await session.execute(delete(Chunk).where(Chunk.version_id == version_id))
        session.add_all([
            Chunk(id=d.id, version_id=version_id, kind=d.kind, parent_id=d.parent_id, seq=d.seq,
                  heading_path=d.heading_path, category=d.category, text=d.text, context_header=d.context_header,
                  page_start=d.page_start, page_end=d.page_end, regions=d.regions, element_ids=d.element_ids,
                  token_count=d.token_count, image_key=d.image_key)
            for d in drafts
        ])
        await session.commit()
    kinds = {k: sum(1 for d in drafts if d.kind == k) for k in ("parent", "child", "image")}
    await r.update("chunking", message=f"{kinds['child']} passages, {kinds['parent']} sections, {kinds['image']} images")


EMBED_BATCH = 32


async def embed(version_id: str, r: StageReporter) -> None:
    from sqlalchemy import select, update

    from stylelens.db.models import Chunk
    from stylelens.retrieval.models import aembed, get_embedder

    await r.update("embedding", message="Loading embedding model")
    embedder = await asyncio.to_thread(get_embedder)
    async with SessionLocal() as session:
        rows = (await session.execute(
            select(Chunk.id, Chunk.context_header, Chunk.text)
            .where(Chunk.version_id == version_id, Chunk.kind.in_(("child", "image")))
            .order_by(Chunk.seq))).all()
    for i in range(0, len(rows), EMBED_BATCH):
        batch = rows[i : i + EMBED_BATCH]
        vectors = await aembed([f"{h}\n\n{t}" for _, h, t in batch])
        async with SessionLocal() as session:
            for (cid, _, _), vec in zip(batch, vectors, strict=True):
                await session.execute(update(Chunk).where(Chunk.id == cid).values(embedding=vec.tolist()))
            await session.commit()
        await r.update("embedding", progress=min(1.0, (i + len(batch)) / max(len(rows), 1)),
                       message=f"{i + len(batch)} of {len(rows)} passages")
    async with SessionLocal() as session:
        version = await session.get(GuideVersion, version_id)
        version.embedding_model = embedder.name
        await session.commit()


async def index(version_id: str, r: StageReporter) -> None:
    from sqlalchemy import func, select, text

    from stylelens.db.models import Chunk

    async with SessionLocal() as session:
        n = await session.scalar(select(func.count()).select_from(Chunk).where(
            Chunk.version_id == version_id, Chunk.embedding.is_not(None)))
        await session.execute(text("ANALYZE chunks"))
        await session.commit()
    await r.update("indexing", message=f"{n} passages searchable (hybrid lexical + vector)")
