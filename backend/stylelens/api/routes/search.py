from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from stylelens.api.schemas import ChunkOut, Region
from stylelens.db.models import Chunk, Guide, GuideVersion
from stylelens.db.session import get_session
from stylelens.retrieval.context import assemble
from stylelens.retrieval.search import retrieve

router = APIRouter(tags=["retrieval"])


@router.get("/chunks/{chunk_id}", response_model=ChunkOut)
async def get_chunk(chunk_id: str, session: AsyncSession = Depends(get_session)):
    """Citation preview: text, page, regions and heading path for a chunk."""
    chunk = await session.get(Chunk, chunk_id)
    if chunk is None:
        raise HTTPException(404, "Chunk not found")
    version = await session.get(GuideVersion, chunk.version_id)
    return ChunkOut(
        id=chunk.id, guide_id=version.guide_id, version_id=chunk.version_id, kind=chunk.kind, text=chunk.text,
        heading_path=list(chunk.heading_path or []), page_start=chunk.page_start, page_end=chunk.page_end,
        regions=[Region(page=r["page"], bbox=r.get("bbox")) for r in chunk.regions or []],
        image_url=f"/assets/{chunk.image_key}" if chunk.image_key else None, parent_id=chunk.parent_id,
    )


class SearchRequest(BaseModel):
    query: str
    guide_ids: list[str] | None = None
    top_k: int | None = None


class SearchHit(BaseModel):
    n: int
    chunk_id: str
    guide_id: str
    guide_name: str
    kind: str
    page: int
    heading_path: list[str]
    snippet: str
    score: float
    regions: list[dict]
    element_ids: list[str]


class SearchResponse(BaseModel):
    query: str
    standalone_query: str
    intent: str | None
    covered: bool
    candidates: int
    hits: list[SearchHit]


@router.post("/search", response_model=SearchResponse)
async def search(req: SearchRequest, session: AsyncSession = Depends(get_session)):
    """Hybrid search over ready guides (all of them, or the given ones)."""
    stmt = select(Guide).where(Guide.status == "ready")
    if req.guide_ids:
        stmt = stmt.where(Guide.id.in_(req.guide_ids))
    guides = list(await session.scalars(stmt))
    version_ids = [g.current_version_id for g in guides if g.current_version_id]
    if not version_ids or not req.query.strip():
        return SearchResponse(query=req.query, standalone_query=req.query, intent=None, covered=False, candidates=0, hits=[])
    result = await retrieve(req.query, version_ids, top_k=req.top_k)
    ctx = await assemble(result.hits)
    by_chunk = {s.chunk_id: s for s in ctx.sources}
    hits = [SearchHit(n=by_chunk[h.chunk_id].n, chunk_id=h.chunk_id, guide_id=by_chunk[h.chunk_id].guide_id,
                      guide_name=by_chunk[h.chunk_id].guide_name, kind=h.kind, page=by_chunk[h.chunk_id].page,
                      heading_path=h.heading_path, snippet=h.text[:300], score=h.score, regions=h.regions,
                      element_ids=h.element_ids) for h in result.hits]
    return SearchResponse(query=req.query, standalone_query=result.standalone_query, intent=result.intent,
                          covered=result.covered, candidates=result.candidates, hits=hits)
