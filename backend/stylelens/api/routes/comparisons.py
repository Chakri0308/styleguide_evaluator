import json
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse, Response
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from sse_starlette.sse import EventSourceResponse

from stylelens import events, jobs
from stylelens.compare.export import report_json, report_pdf
from stylelens.compare.schema import CitationRef
from stylelens.db.models import Comparison, Guide, GuideVersion
from stylelens.db.session import SessionLocal, get_session

router = APIRouter(prefix="/comparisons", tags=["comparisons"])


class CompareIn(BaseModel):
    reference_id: str
    candidate_id: str


class GuideRef(BaseModel):
    id: str
    name: str
    version_id: str
    version: int
    format: str


class FindingOut(BaseModel):
    id: str
    finding_id: str
    category: str
    status: str
    severity: str
    method: str
    summary: str
    reasoning: str
    reference_citations: list[CitationRef]
    candidate_citations: list[CitationRef]
    confidence: float
    data: dict


class ComparisonListItem(BaseModel):
    id: str
    status: str
    score: float | None
    reference_name: str
    candidate_name: str
    created_at: datetime


class ComparisonOut(BaseModel):
    id: str
    status: str
    stages: dict
    score: float | None
    summary: dict
    error: str | None
    created_at: datetime
    finished_at: datetime | None
    reference: GuideRef
    candidate: GuideRef
    findings: list[FindingOut]


async def _guide_ref(session: AsyncSession, version_id: str) -> GuideRef:
    v = await session.get(GuideVersion, version_id)
    g = await session.get(Guide, v.guide_id)
    return GuideRef(id=g.id, name=g.name, version_id=v.id, version=v.version, format=g.format)


async def _out(session: AsyncSession, comp: Comparison) -> ComparisonOut:
    return ComparisonOut(
        id=comp.id, status=comp.status, stages=comp.stages, score=comp.score, summary=comp.summary or {},
        error=comp.error, created_at=comp.created_at, finished_at=comp.finished_at,
        reference=await _guide_ref(session, comp.reference_version_id),
        candidate=await _guide_ref(session, comp.candidate_version_id),
        findings=[FindingOut(
            id=f.id, finding_id=f.finding_id, category=f.category, status=f.status, severity=f.severity,
            method=f.method, summary=f.summary, reasoning=f.reasoning, reference_citations=f.reference_citations,
            candidate_citations=f.candidate_citations, confidence=f.confidence, data=f.data or {})
            for f in comp.findings],
    )


async def _load(session: AsyncSession, comparison_id: str) -> Comparison:
    comp = await session.scalar(
        select(Comparison).where(Comparison.id == comparison_id).options(selectinload(Comparison.findings)))
    if comp is None:
        raise HTTPException(404, "Comparison not found")
    return comp


@router.post("", response_model=ComparisonOut, status_code=201)
async def create_comparison(body: CompareIn, session: AsyncSession = Depends(get_session)):
    if body.reference_id == body.candidate_id:
        raise HTTPException(422, "Pick two different documents.")
    ref = await session.get(Guide, body.reference_id)
    cand = await session.get(Guide, body.candidate_id)
    if ref is None or cand is None:
        raise HTTPException(404, "Guide not found")
    for g in (ref, cand):
        if g.status != "ready" or not g.current_version_id:
            raise HTTPException(409, f"“{g.name}” is still being analyzed.")
    comp = Comparison(reference_version_id=ref.current_version_id, candidate_version_id=cand.current_version_id,
                      status="queued", stages=events.initial_stages(events.COMPARE_STAGES))
    session.add(comp)
    await session.commit()
    await jobs.enqueue("compare_guides", comp.id)
    return await _out(session, await _load(session, comp.id))


@router.get("", response_model=list[ComparisonListItem])
async def list_comparisons(session: AsyncSession = Depends(get_session)):
    comps = list(await session.scalars(select(Comparison).order_by(Comparison.created_at.desc()).limit(100)))
    out = []
    for c in comps:
        ref, cand = await _guide_ref(session, c.reference_version_id), await _guide_ref(session, c.candidate_version_id)
        out.append(ComparisonListItem(id=c.id, status=c.status, score=c.score, reference_name=ref.name,
                                      candidate_name=cand.name, created_at=c.created_at))
    return out


@router.get("/{comparison_id}", response_model=ComparisonOut)
async def get_comparison(comparison_id: str, session: AsyncSession = Depends(get_session)):
    return await _out(session, await _load(session, comparison_id))


@router.delete("/{comparison_id}", status_code=204)
async def delete_comparison(comparison_id: str, session: AsyncSession = Depends(get_session)):
    comp = await _load(session, comparison_id)
    await session.delete(comp)
    await session.commit()
    return Response(status_code=204)


@router.get("/{comparison_id}/events")
async def comparison_events(comparison_id: str, request: Request):
    async with SessionLocal() as session:
        comp = await session.get(Comparison, comparison_id)
        if comp is None:
            raise HTTPException(404, "Comparison not found")
        snapshot = {"status": comp.status, "stages": comp.stages, "error": comp.error}

    async def stream():
        yield {"event": "snapshot", "data": json.dumps(snapshot)}
        if snapshot["status"] in ("ready", "failed"):
            return
        pubsub = events.redis().pubsub()
        await pubsub.subscribe(events.channel("compare", comparison_id))
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


@router.get("/{comparison_id}/export")
async def export_comparison(comparison_id: str, format: str = "json", session: AsyncSession = Depends(get_session)):
    comp = (await _out(session, await _load(session, comparison_id))).model_dump(mode="json")
    if comp["status"] != "ready":
        raise HTTPException(409, "The comparison hasn't finished yet.")
    stem = f"stylelens-{comp['candidate']['name']}-vs-{comp['reference']['name']}".replace(" ", "_")[:120]
    if format == "pdf":
        return Response(report_pdf(comp), media_type="application/pdf",
                        headers={"Content-Disposition": f'attachment; filename="{stem}.pdf"'})
    if format == "json":
        return JSONResponse(report_json(comp), headers={"Content-Disposition": f'attachment; filename="{stem}.json"'})
    raise HTTPException(422, "format must be json or pdf")
