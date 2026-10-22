"""Context assembly: expand retrieved passages to their parent sections, deduplicate, order by
document position, and render them for the LLM with numbered, stable source ids.

Each section is shown in full so the model has context, with the retrieved passages wrapped in
<source id="N"> tags — the model cites those numbers and every number maps back to a chunk id,
page and highlight regions.
"""

from dataclasses import dataclass, field

from sqlalchemy import select

from stylelens.db.models import Chunk, Element, Guide, GuideVersion
from stylelens.db.session import SessionLocal
from stylelens.retrieval.search import Hit


@dataclass
class Source:
    n: int
    chunk_id: str
    guide_id: str
    guide_name: str
    version_id: str
    kind: str
    page: int
    regions: list[dict]
    heading_path: list[str]
    text: str
    score: float
    element_ids: list[str] = field(default_factory=list)

    def citation(self) -> dict:
        return {"n": self.n, "chunk_id": self.chunk_id, "guide_id": self.guide_id, "guide_name": self.guide_name,
                "version_id": self.version_id, "kind": self.kind, "page": self.page, "regions": self.regions,
                "heading_path": self.heading_path, "snippet": self.text[:400], "score": self.score,
                "element_ids": self.element_ids}


@dataclass
class Context:
    sources: list[Source]
    rendered: str

    def by_number(self) -> dict[int, Source]:
        return {s.n: s for s in self.sources}


async def assemble(hits: list[Hit], label_by_version: dict[str, str] | None = None) -> Context:
    if not hits:
        return Context([], "")
    async with SessionLocal() as session:
        versions = {v.id: v for v in await session.scalars(
            select(GuideVersion).where(GuideVersion.id.in_({h.version_id for h in hits})))}
        guides = {g.id: g for g in await session.scalars(
            select(Guide).where(Guide.id.in_({v.guide_id for v in versions.values()})))}
        parent_ids = {h.parent_id for h in hits if h.parent_id}
        parents = {c.id: c for c in await session.scalars(select(Chunk).where(Chunk.id.in_(parent_ids)))}
        el_ids = {eid for p in parents.values() for eid in p.element_ids}
        elements = {e.id: e for e in await session.scalars(select(Element).where(Element.id.in_(el_ids)))}

    # Source numbers follow document order (version, then position), so they're stable for a hit set.
    ordered = sorted(hits, key=lambda h: (h.version_id, h.seq, h.chunk_id))
    sources: list[Source] = []
    for i, h in enumerate(ordered):
        v = versions[h.version_id]
        g = guides[v.guide_id]
        first_region = next((r for r in h.regions if r.get("bbox")), h.regions[0] if h.regions else {})
        sources.append(Source(
            n=i + 1, chunk_id=h.chunk_id, guide_id=g.id, guide_name=g.name, version_id=h.version_id, kind=h.kind,
            page=first_region.get("page", h.page_start), regions=h.regions, heading_path=h.heading_path,
            text=h.text, score=h.score, element_ids=h.element_ids))
    by_chunk = {s.chunk_id: s for s in sources}
    hit_by_chunk = {h.chunk_id: h for h in hits}

    # Group by parent section; sections ordered by document position.
    groups: dict[str, list[Hit]] = {}
    orphans: list[Hit] = []
    for h in ordered:
        if h.parent_id and h.parent_id in parents:
            groups.setdefault(h.parent_id, []).append(h)
        else:
            orphans.append(h)
    blocks: list[str] = []
    for pid in sorted(groups, key=lambda p: (parents[p].version_id, parents[p].seq)):
        parent = parents[pid]
        members = groups[pid]
        doc_label = (label_by_version or {}).get(parent.version_id) or guides[versions[parent.version_id].guide_id].name
        el_to_source: dict[str, int] = {}
        image_sources = []
        for h in members:
            if h.kind == "image":
                image_sources.append(by_chunk[h.chunk_id])
                continue
            for eid in h.element_ids:
                el_to_source.setdefault(eid, by_chunk[h.chunk_id].n)
        lines: list[str] = []
        open_n: int | None = None
        for eid in parent.element_ids:
            el = elements.get(eid)
            if el is None or el.type in ("image", "swatch") or not el.text:
                continue
            n = el_to_source.get(eid)
            if n != open_n:
                if open_n is not None:
                    lines.append("</source>")
                if n is not None:
                    src = next(s for s in sources if s.n == n)
                    lines.append(f'<source id="{n}" page="{src.page}">')
                open_n = n
            prefix = "- " if el.type == "list_item" else ""
            lines.append(prefix + el.text)
        if open_n is not None:
            lines.append("</source>")
        for s in image_sources:
            lines.append(f'<source id="{s.n}" page="{s.page}" type="image">\n{hit_by_chunk[s.chunk_id].text}\n</source>')
        path = " > ".join(parent.heading_path)
        blocks.append(f'<section document="{doc_label}" path="{path}" pages="{parent.page_start}-{parent.page_end}">\n'
                      + "\n".join(lines) + "\n</section>")
    for h in orphans:
        s = by_chunk[h.chunk_id]
        doc_label = (label_by_version or {}).get(h.version_id) or s.guide_name
        blocks.append(f'<section document="{doc_label}" path="{" > ".join(h.heading_path)}">\n'
                      f'<source id="{s.n}" page="{s.page}" type="{h.kind}">\n{h.text}\n</source>\n</section>')
    return Context(sources, "\n\n".join(blocks))
