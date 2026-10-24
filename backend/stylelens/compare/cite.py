"""Resolve elements / source refs to citations backed by real index chunks."""

from dataclasses import dataclass

from sqlalchemy import select

from stylelens.compare.schema import CitationRef
from stylelens.db.models import Chunk, Element
from stylelens.db.session import SessionLocal


@dataclass
class VersionIndex:
    version_id: str
    chunks: dict[str, Chunk]
    elements: dict[str, Element]
    element_to_chunk: dict[str, str]

    def cite_element(self, element_id: str, quote: str = "", bbox: list[float] | None = None) -> CitationRef | None:
        """`bbox` overrides the element's own box (e.g. a figure region that spans several elements)."""
        cid = self.element_to_chunk.get(element_id)
        el = self.elements.get(element_id)
        if cid is None or el is None:
            return None
        return CitationRef(chunk_id=cid, page=el.page, quote=(quote or el.text)[:300], element_id=element_id,
                           bbox=bbox or el.bbox, version_id=self.version_id)

    def cite_region(self, page: int, bbox: list[float] | None, quote: str = "") -> CitationRef | None:
        """Cite an arbitrary page region, anchored to the element it overlaps most (for the chunk link)."""
        from stylelens.visual import overlap

        on_page = [e for e in self.elements.values() if e.page == page and e.id in self.element_to_chunk]
        if not on_page:
            return None
        anchor = max(on_page, key=lambda e: (overlap(bbox, e.bbox), e.type == "image", -e.seq))
        return self.cite_element(anchor.id, quote, bbox=bbox)

    def cite_chunk(self, chunk_id: str, quote: str = "") -> CitationRef | None:
        ch = self.chunks.get(chunk_id)
        if ch is None:
            return None
        region = next((r for r in ch.regions or [] if r.get("bbox")), (ch.regions or [{}])[0] if ch.regions else {})
        eid = region.get("element_id")
        if quote and ch.kind != "image":
            # Point at the element that actually contains the quote when possible
            for e in ch.element_ids or []:
                el = self.elements.get(e)
                if el and quote[:40].lower() in el.text.lower():
                    eid, region = e, {"page": el.page, "bbox": el.bbox}
                    break
        return CitationRef(chunk_id=chunk_id, page=region.get("page", ch.page_start), quote=(quote or ch.text)[:300],
                           element_id=eid, bbox=region.get("bbox"), version_id=self.version_id)

    def cite_refs(self, refs: list[dict], limit: int = 3) -> list[CitationRef]:
        out = []
        for r in refs[:limit]:
            c = self.cite_element(r["element_id"], r.get("quote", ""), bbox=r.get("bbox"))
            if c and all(x.element_id != c.element_id for x in out):
                out.append(c)
        return out


async def load_index(version_id: str) -> VersionIndex:
    async with SessionLocal() as session:
        chunks = {c.id: c for c in await session.scalars(select(Chunk).where(Chunk.version_id == version_id))}
        elements = {e.id: e for e in await session.scalars(select(Element).where(Element.version_id == version_id))}
    e2c: dict[str, str] = {}
    # Prefer child chunks (precise), then images, then parents.
    for kind in ("child", "image", "parent"):
        for c in sorted(chunks.values(), key=lambda c: c.seq):
            if c.kind != kind:
                continue
            for eid in c.element_ids or []:
                e2c.setdefault(eid, c.id)
    # Swatches and other unindexed elements map to the chunk of their nearest indexed neighbour
    ordered = sorted(elements.values(), key=lambda e: e.seq)
    last = None
    for e in ordered:
        if e.id in e2c:
            last = e2c[e.id]
        elif last:
            e2c[e.id] = last
    first = next((e2c[e.id] for e in ordered if e.id in e2c), None)
    for e in ordered:
        if e.id not in e2c and first:
            e2c[e.id] = first
    return VersionIndex(version_id, chunks, elements, e2c)
