import asyncio
import hashlib
import json
from pathlib import PurePath

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from sse_starlette.sse import EventSourceResponse

from stylelens import events, jobs
from stylelens.api.schemas import ElementOut, GuideOut, GuideVersionOut, IngestionStatus, PageOut
from stylelens.config import get_settings
from stylelens.db.models import Element, Guide, GuideVersion, Page, StyleProfile
from stylelens.db.session import SessionLocal, get_session
from stylelens.formats import UnsupportedFormat, detect_format, mime_for
from stylelens.storage import aget, aput

router = APIRouter(prefix="/guides", tags=["guides"])


def guide_out(guide: Guide) -> GuideOut:
    out = GuideOut.model_validate(guide)
    current = next((v for v in guide.versions if v.id == guide.current_version_id), None)
    out.current_version = GuideVersionOut.model_validate(current) if current else None
    return out


async def load_guide(session: AsyncSession, guide_id: str) -> Guide:
    guide = await session.scalar(
        select(Guide).where(Guide.id == guide_id).options(selectinload(Guide.versions))
    )
    if guide is None:
        raise HTTPException(404, "Guide not found")
    return guide


async def create_version(session: AsyncSession, guide: Guide, number: int) -> GuideVersion:
    version = GuideVersion(
        guide_id=guide.id,
        version=number,
        status="queued",
        stages=events.initial_stages(events.INGEST_STAGES),
    )
    session.add(version)
    await session.flush()
    guide.current_version_id = version.id
    guide.status = "processing"
    return version


@router.post("", response_model=GuideOut, status_code=201)
async def upload_guide(
    file: UploadFile = File(...),
    role: str = Form("reference"),
    name: str | None = Form(None),
    session: AsyncSession = Depends(get_session),
):
    if role not in ("reference", "candidate"):
        raise HTTPException(422, "role must be 'reference' or 'candidate'")
    data = await file.read()
    limit = get_settings().max_upload_mb * 1024 * 1024
    if not data:
        raise HTTPException(422, "The uploaded file is empty.")
    if len(data) > limit:
        raise HTTPException(413, f"File exceeds the {get_settings().max_upload_mb} MB limit.")
    filename = PurePath(file.filename or "upload").name
    try:
        fmt = detect_format(filename, data[:16])
    except UnsupportedFormat as exc:
        raise HTTPException(415, str(exc)) from exc

    sha = hashlib.sha256(data).hexdigest()
    guide = Guide(
        name=(name or PurePath(filename).stem).strip()[:300],
        role=role,
        filename=filename,
        mime_type=mime_for(fmt, filename),
        format=fmt,
        size_bytes=len(data),
        sha256=sha,
        storage_key="",
        status="uploaded",
    )
    session.add(guide)
    await session.flush()
    guide.storage_key = f"guides/{guide.id}/original/{filename}"
    await aput(guide.storage_key, data, guide.mime_type)
    version = await create_version(session, guide, 1)
    await session.commit()
    await jobs.enqueue("ingest_guide", version.id)
    return guide_out(await load_guide(session, guide.id))


@router.get("", response_model=list[GuideOut])
async def list_guides(role: str | None = None, session: AsyncSession = Depends(get_session)):
    stmt = select(Guide).options(selectinload(Guide.versions)).order_by(Guide.created_at.desc())
    if role:
        stmt = stmt.where(Guide.role == role)
    return [guide_out(g) for g in await session.scalars(stmt)]


@router.get("/{guide_id}", response_model=GuideOut)
async def get_guide(guide_id: str, session: AsyncSession = Depends(get_session)):
    return guide_out(await load_guide(session, guide_id))


@router.delete("/{guide_id}", status_code=204)
async def delete_guide(guide_id: str, session: AsyncSession = Depends(get_session)):
    guide = await load_guide(session, guide_id)
    await session.delete(guide)
    await session.commit()
    return Response(status_code=204)


@router.post("/{guide_id}/reingest", response_model=GuideOut)
async def reingest_guide(guide_id: str, session: AsyncSession = Depends(get_session)):
    """Re-run ingestion as a new index version; the previous version is kept intact."""
    guide = await load_guide(session, guide_id)
    number = max((v.version for v in guide.versions), default=0) + 1
    version = await create_version(session, guide, number)
    await session.commit()
    await jobs.enqueue("ingest_guide", version.id)
    session.expire_all()
    return guide_out(await load_guide(session, guide_id))


@router.get("/{guide_id}/ingestion-status", response_model=IngestionStatus)
async def ingestion_status(guide_id: str, session: AsyncSession = Depends(get_session)):
    guide = await load_guide(session, guide_id)
    version = next((v for v in guide.versions if v.id == guide.current_version_id), None)
    if version is None:
        raise HTTPException(404, "Guide has no ingestion run")
    return IngestionStatus(
        guide_id=guide.id,
        version_id=version.id,
        version=version.version,
        status=version.status,
        stages=version.stages,
        error=version.error,
    )


@router.get("/{guide_id}/events")
async def ingestion_events(guide_id: str, request: Request):
    """Server-sent events with live ingestion progress. Sends a snapshot first, then deltas."""
    async with SessionLocal() as session:
        guide = await load_guide(session, guide_id)
        version = next((v for v in guide.versions if v.id == guide.current_version_id), None)
        if version is None:
            raise HTTPException(404, "Guide has no ingestion run")
        snapshot = {"version_id": version.id, "status": version.status,
                    "stages": version.stages, "error": version.error}

    async def stream():
        yield {"event": "snapshot", "data": json.dumps(snapshot)}
        if snapshot["status"] in ("ready", "failed"):
            return
        pubsub = events.redis().pubsub()
        await pubsub.subscribe(events.channel("ingest", version.id))
        try:
            while not await request.is_disconnected():
                msg = await pubsub.get_message(ignore_subscribe_messages=True, timeout=15)
                if msg is None:
                    yield {"event": "ping", "data": "{}"}
                    continue
                yield {"event": "progress", "data": msg["data"]}
                if json.loads(msg["data"]).get("status") in ("ready", "failed"):
                    break
        finally:
            await pubsub.unsubscribe()
            await pubsub.aclose()

    return EventSourceResponse(stream())


@router.get("/{guide_id}/file")
async def guide_file(guide_id: str, session: AsyncSession = Depends(get_session)):
    guide = await load_guide(session, guide_id)
    data = await aget(guide.storage_key)
    return Response(
        data,
        media_type=guide.mime_type,
        headers={"Content-Disposition": f'inline; filename="{guide.filename}"',
                 "Cache-Control": "private, max-age=3600"},
    )


@router.get("/{guide_id}/pages", response_model=list[PageOut])
async def guide_pages(guide_id: str, session: AsyncSession = Depends(get_session)):
    guide = await load_guide(session, guide_id)
    pages = await session.scalars(
        select(Page).where(Page.version_id == guide.current_version_id).order_by(Page.page)
    )
    return [
        PageOut(page=p.page, width=p.width, height=p.height,
                image_url=f"/assets/{p.image_key}" if p.image_key else None)
        for p in pages
    ]


@router.get("/{guide_id}/elements", response_model=list[ElementOut])
async def guide_elements(guide_id: str, page: int | None = None, session: AsyncSession = Depends(get_session)):
    """Parsed layout elements of the current version (used by the text source viewer)."""
    guide = await load_guide(session, guide_id)
    stmt = select(Element).where(Element.version_id == guide.current_version_id).order_by(Element.seq)
    if page is not None:
        stmt = stmt.where(Element.page == page)
    return list(await session.scalars(stmt))


@router.get("/{guide_id}/profile")
async def guide_profile(guide_id: str, session: AsyncSession = Depends(get_session)):
    guide = await load_guide(session, guide_id)
    profile = await session.get(StyleProfile, guide.current_version_id)
    if profile is None:
        raise HTTPException(404, "Profile not available yet")
    return profile.data


async def wait_for_ingestion(version_id: str, timeout: float = 600) -> str:
    """Poll until a version finishes (used by tests and CLI tools)."""
    loop = asyncio.get_running_loop()
    deadline = loop.time() + timeout
    while loop.time() < deadline:
        async with SessionLocal() as session:
            version = await session.get(GuideVersion, version_id)
            if version and version.status in ("ready", "failed"):
                return version.status
        await asyncio.sleep(0.25)
    raise TimeoutError(version_id)
