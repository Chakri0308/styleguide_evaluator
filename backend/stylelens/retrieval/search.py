"""Hybrid retrieval: query understanding → BM25-style lexical (Postgres FTS) + dense (pgvector) →
Reciprocal Rank Fusion → cross-encoder rerank → threshold.

Consistency: every ordering breaks ties by chunk id, results are cached per (query, index versions,
model versions, settings), and indexes are immutable per GuideVersion.
"""

import logging
import re
from dataclasses import asdict, dataclass, field

from pydantic import BaseModel
from sqlalchemy import select, text

from stylelens.config import get_settings
from stylelens.db.models import Chunk
from stylelens.db.session import SessionLocal
from stylelens.extraction.common import categorize
from stylelens.llm.base import LLMRefusal, LLMUnavailable
from stylelens.llm.client import cache_get, cache_key, cache_put, generate_json, llm_available, model_spec
from stylelens.retrieval.models import aembed, arerank, get_embedder, get_reranker, tokens

log = logging.getLogger(__name__)
RETRIEVABLE = ("child", "image")
RETRIEVAL_VERSION = 1  # bump when the algorithm changes (cache key)


@dataclass
class Hit:
    chunk_id: str
    version_id: str
    kind: str
    seq: int
    parent_id: str | None
    heading_path: list[str]
    category: str | None
    text: str
    context_header: str
    page_start: int
    page_end: int
    regions: list[dict]
    element_ids: list[str]
    image_key: str | None
    score: float = 0.0
    fused: float = 0.0
    ranks: dict = field(default_factory=dict)


@dataclass
class RetrievalResult:
    query: str
    standalone_query: str
    variants: list[str]
    intent: str | None
    hits: list[Hit]
    candidates: int
    covered: bool  # False when nothing passed the relevance threshold

    def to_json(self) -> dict:
        return {**asdict(self), "hits": [asdict(h) for h in self.hits]}


class QueryPlan(BaseModel):
    standalone: str
    variants: list[str]


INTENT_CATEGORIES = {
    "color_usage", "typography_usage", "logo_rules", "voice_tone", "writing_rules", "imagery_rules",
    "accessibility", "components", "spacing_grid",
}


def classify_intent(q: str) -> str | None:
    cat = categorize("", q)
    return cat if cat in INTENT_CATEGORIES else None


def tsquery_string(q: str) -> str | None:
    toks = []
    for t in tokens(q):
        t = t.lstrip("#")
        if t and re.fullmatch(r"[a-z0-9]+", t):
            toks.append(t)
    toks = list(dict.fromkeys(toks))[:24]
    return " | ".join(toks) if toks else None


async def _lexical(session, q: str, version_ids: list[str], n: int, category: str | None = None) -> list[str]:
    tsq = tsquery_string(q)
    if not tsq:
        return []
    sql = """
        SELECT id FROM chunks, to_tsquery('english', :tsq) query
        WHERE version_id = ANY(:vids) AND kind = ANY(:kinds) AND tsv @@ query
        {cat}
        ORDER BY ts_rank_cd(tsv, query, 32) DESC, id
        LIMIT :n
    """.format(cat="AND category = :cat" if category else "")
    params = {"tsq": tsq, "vids": version_ids, "kinds": list(RETRIEVABLE), "n": n}
    if category:
        params["cat"] = category
    return [r[0] for r in (await session.execute(text(sql), params)).all()]


async def _dense(session, qvec: list[float], version_ids: list[str], n: int) -> list[str]:
    await session.execute(text("SET LOCAL hnsw.ef_search = 200"))
    await session.execute(text("SET LOCAL hnsw.iterative_scan = relaxed_order"))
    rows = (await session.execute(text("""
        SELECT id FROM (
            SELECT id, embedding <=> CAST(:qv AS vector) AS d FROM chunks
            WHERE version_id = ANY(:vids) AND kind = ANY(:kinds) AND embedding IS NOT NULL
            ORDER BY embedding <=> CAST(:qv AS vector)
            LIMIT :n
        ) s ORDER BY d, id
    """), {"qv": str(qvec), "vids": version_ids, "kinds": list(RETRIEVABLE), "n": n})).all()
    return [r[0] for r in rows]


def rrf(ranked_lists: list[list[str]], k: int, weights: list[float] | None = None) -> list[tuple[str, float]]:
    scores: dict[str, float] = {}
    for li, ids in enumerate(ranked_lists):
        w = weights[li] if weights else 1.0
        for rank, cid in enumerate(ids):
            scores[cid] = scores.get(cid, 0.0) + w / (k + rank + 1)
    return sorted(scores.items(), key=lambda kv: (-round(kv[1], 12), kv[0]))


async def plan_query(query: str, history: list[dict] | None) -> tuple[str, list[str]]:
    """Rewrite follow-ups into standalone queries (and optional variants) using chat history."""
    s = get_settings()
    if not history and not s.multi_query:
        return query, []
    if not llm_available("fast"):
        return query, []
    convo = "\n".join(f"{m['role']}: {m['content'][:600]}" for m in (history or [])[-6:])
    try:
        plan = await generate_json("fast", "rewrite_query", QueryPlan, query=query, history=convo or "(none)",
                                   want_variants=s.multi_query, max_tokens=1000)
    except (LLMUnavailable, LLMRefusal, ValueError) as exc:
        log.warning("query rewrite failed: %s", exc)
        return query, []
    standalone = plan.standalone.strip() or query
    variants = [v.strip() for v in plan.variants if v.strip() and v.strip() != standalone][:3] if s.multi_query else []
    return standalone, variants


async def load_hits(ids: list[str]) -> dict[str, Hit]:
    if not ids:
        return {}
    async with SessionLocal() as session:
        rows = await session.scalars(select(Chunk).where(Chunk.id.in_(ids)))
        return {c.id: Hit(
            chunk_id=c.id, version_id=c.version_id, kind=c.kind, seq=c.seq, parent_id=c.parent_id,
            heading_path=list(c.heading_path or []), category=c.category, text=c.text,
            context_header=c.context_header, page_start=c.page_start, page_end=c.page_end,
            regions=c.regions or [], element_ids=list(c.element_ids or []), image_key=c.image_key) for c in rows}


async def retrieve(query: str, version_ids: list[str], *, history: list[dict] | None = None,
                   top_k: int | None = None, threshold: float | None = None,
                   use_cache: bool = True) -> RetrievalResult:
    s = get_settings()
    top_k = top_k or s.rerank_top_k
    if threshold is None:
        threshold = s.rerank_threshold if s.rerank_threshold is not None else get_reranker().default_threshold
    version_ids = sorted(set(version_ids))
    standalone, variants = await plan_query(query, history)
    intent = classify_intent(standalone)

    key = cache_key("retrieval", RETRIEVAL_VERSION, standalone, variants, version_ids, get_embedder().name,
                    get_reranker().name, s.retrieval_candidates, top_k, threshold, s.rrf_k)
    if use_cache and (hit := await cache_get(key)) is not None:
        loaded = await load_hits([h["chunk_id"] for h in hit["hits"]])
        hits = []
        for h in hit["hits"]:
            if h["chunk_id"] in loaded:
                obj = loaded[h["chunk_id"]]
                obj.score, obj.fused, obj.ranks = h["score"], h["fused"], h["ranks"]
                hits.append(obj)
        return RetrievalResult(query, standalone, variants, intent, hits, hit["candidates"], hit["covered"])

    n = s.retrieval_candidates
    queries = [standalone, *variants]
    qvecs = await aembed(queries, query=True)
    lists: list[list[str]] = []
    names: list[str] = []
    async with SessionLocal() as session:
        for qi, q in enumerate(queries):
            lists.append(await _lexical(session, q, version_ids, n))
            names.append(f"lexical{qi}")
            lists.append(await _dense(session, qvecs[qi].tolist(), version_ids, n))
            names.append(f"dense{qi}")
        if intent:
            lists.append(await _lexical(session, standalone, version_ids, n, category=intent))
            names.append("intent")
    weights = [0.5 if nm == "intent" else 1.0 for nm in names]
    fused = rrf(lists, s.rrf_k, weights)[:n]
    rank_of = {nm: {cid: i + 1 for i, cid in enumerate(li)} for nm, li in zip(names, lists, strict=True)}

    loaded = await load_hits([cid for cid, _ in fused])
    candidates = [loaded[cid] for cid, _ in fused if cid in loaded]
    for h, (_, f) in zip(candidates, fused, strict=False):
        h.fused = round(f, 6)
        h.ranks = {nm: r[h.chunk_id] for nm, r in rank_of.items() if h.chunk_id in r}
    passages = [f"{' > '.join(h.heading_path)}\n{h.text}" for h in candidates]
    scores = await arerank(standalone, passages)
    for h, sc in zip(candidates, scores, strict=True):
        h.score = sc
    ranked = sorted(candidates, key=lambda h: (-h.score, -h.fused, h.chunk_id))
    passing = [h for h in ranked if h.score >= threshold][:top_k]
    result = RetrievalResult(query, standalone, variants, intent, passing, len(candidates), bool(passing))
    if use_cache:
        await cache_put(key, "retrieval", {
            "hits": [{"chunk_id": h.chunk_id, "score": h.score, "fused": h.fused, "ranks": h.ranks} for h in passing],
            "candidates": len(candidates), "covered": bool(passing), "generation_model": model_spec("generation"),
        })
    return result
