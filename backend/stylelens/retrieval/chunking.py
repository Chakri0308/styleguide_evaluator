"""Structure-aware parent/child chunking.

* Parents follow the heading hierarchy: a maximal run of elements under the same heading path
  (split only if a section is very long). Parents give the LLM full-section context.
* Children pack consecutive elements of a parent into ~200-400 tokens for precise retrieval. Tables,
  list items and paragraphs are never split mid-element.
* Images become their own chunks: caption + generated description + OCR text + nearby text.
* Every chunk gets a contextual header (document title, heading path, short section summary) that
  is embedded and indexed together with the text.
* Chunk ids are deterministic (hash of version + member elements), so citations are stable per
  index version.
"""

import hashlib
import re
from dataclasses import dataclass, field

from stylelens.extraction.common import El, categorize

CHILD_MIN_TOKENS = 200
CHILD_MAX_TOKENS = 400
PARENT_MAX_TOKENS = 1600


def estimate_tokens(text: str) -> int:
    return max(1, round(len(re.findall(r"\w+|[^\w\s]", text)) * 0.75))


@dataclass
class ChunkDraft:
    id: str
    kind: str  # parent | child | image
    seq: int
    heading_path: list[str]
    text: str
    context_header: str
    element_ids: list[str]
    regions: list[dict]
    page_start: int
    page_end: int
    category: str | None
    parent_id: str | None = None
    image_key: str | None = None
    token_count: int = 0
    meta: dict = field(default_factory=dict)

    @property
    def embed_text(self) -> str:
        return f"{self.context_header}\n\n{self.text}"


def chunk_id(version_id: str, kind: str, element_ids: list[str]) -> str:
    h = hashlib.sha1(f"{version_id}|{kind}|{','.join(element_ids)}".encode()).hexdigest()
    return f"{kind[0]}{h[:31]}"


def element_text(el: El) -> str:
    if el.type == "heading":
        return el.text
    if el.type == "list_item":
        return f"- {el.text}"
    return el.text


def _summary(elements: list[El], words: int = 28) -> str:
    body = " ".join(e.text for e in elements if e.type in ("paragraph", "list_item") and e.text)
    toks = body.split()
    if not toks:
        return ""
    s = " ".join(toks[:words])
    return s + ("…" if len(toks) > words else "")


def _header(title: str | None, path: list[str], summary: str) -> str:
    parts = [f"Document: {title or 'Untitled'}"]
    if path:
        parts.append(f"Section: {' > '.join(path)}")
    if summary:
        parts.append(f"Summary: {summary}")
    return "\n".join(parts)


def _regions(els: list[El]) -> list[dict]:
    return [{"page": e.page, "bbox": e.bbox, "element_id": e.id} for e in els]


def build_chunks(version_id: str, title: str | None, elements: list[El],
                 image_descriptions: dict[str, dict] | None = None) -> list[ChunkDraft]:
    image_descriptions = image_descriptions or {}
    content = [e for e in elements if e.type != "swatch" and (e.text or e.type == "image")]

    # 1) Parent sections: consecutive elements sharing a heading path (heading starts its section)
    sections: list[list[El]] = []
    for el in content:
        new_section = not sections or el.type == "heading" or el.heading_path != sections[-1][-1].heading_path
        if new_section and sections and el.type != "heading" and sections[-1][-1].type == "heading" \
                and el.heading_path == sections[-1][-1].heading_path:
            new_section = False  # body directly following its heading
        if new_section:
            sections.append([el])
        else:
            sections[-1].append(el)
    # split very long sections
    sized: list[list[El]] = []
    for sec in sections:
        cur, toks = [], 0
        for el in sec:
            t = estimate_tokens(el.text)
            if cur and toks + t > PARENT_MAX_TOKENS:
                sized.append(cur)
                cur, toks = [], 0
            cur.append(el)
            toks += t
        if cur:
            sized.append(cur)

    chunks: list[ChunkDraft] = []
    seq = 0
    for sec in sized:
        text_els = [e for e in sec if e.type != "image"]
        path = sec[0].heading_path
        summary = _summary(sec)
        header = _header(title, path, summary)
        section_str = " > ".join(path)
        category = categorize(section_str, " ".join(e.text for e in text_els[:4]))
        if any(e.type != "heading" for e in text_els):
            parent_text = "\n".join(element_text(e) for e in text_els)
            parent = ChunkDraft(
                id=chunk_id(version_id, "parent", [e.id for e in sec]), kind="parent", seq=seq, heading_path=path,
                text=parent_text, context_header=header, element_ids=[e.id for e in sec], regions=_regions(text_els),
                page_start=min(e.page for e in sec), page_end=max(e.page for e in sec), category=category,
                token_count=estimate_tokens(parent_text))
            chunks.append(parent)
            seq += 1
            # 2) Children
            group: list[El] = []
            toks = 0

            def flush():
                nonlocal group, toks, seq
                body = [e for e in group if e.type != "heading"] or group
                if not body:
                    return
                text = "\n".join(element_text(e) for e in group)
                chunks.append(ChunkDraft(
                    id=chunk_id(version_id, "child", [e.id for e in group]), kind="child", seq=seq,
                    heading_path=path, text=text, context_header=header, element_ids=[e.id for e in group],
                    regions=_regions(body), page_start=min(e.page for e in group),
                    page_end=max(e.page for e in group), category=category, parent_id=parent.id,
                    token_count=estimate_tokens(text)))
                seq += 1
                group, toks = [], 0

            for el in text_els:
                t = estimate_tokens(element_text(el)) + 1
                # Keep a heading with the content that follows it; never split an element.
                if group and toks + t > CHILD_MAX_TOKENS and toks >= CHILD_MIN_TOKENS // 2 and group[-1].type != "heading":
                    flush()
                group.append(el)
                toks += t
            flush()
        else:
            parent = None
        # 3) Images
        for el in (e for e in sec if e.type == "image"):
            d = image_descriptions.get(el.id, {})
            caption = d.get("caption") or ""
            lines = [f"[Image{' - ' + d['kind'] if d.get('kind') else ''}"
                     f"{' (' + ('do example' if d.get('example') == 'do' else 'do not example') + ')' if d.get('example') in ('do', 'dont') else ''}]"]
            if caption:
                lines.append(f"Caption: {caption}")
            if d.get("description") and d.get("description") != caption:
                lines.append(f"Description: {d['description']}")
            for r in d.get("rules_depicted", []) or []:
                lines.append(f"Illustrates: {r}")
            if d.get("dominant_colors"):
                lines.append(f"Dominant colors: {', '.join(d['dominant_colors'])}")
            ocr = el.meta.get("ocr_text") or d.get("text_in_image")
            if ocr:
                lines.append(f"Text in image: {ocr[:600]}")
            nearby = [e.text for e in text_els if abs(e.seq - el.seq) <= 2 and e.type != "heading"][:2]
            if nearby:
                lines.append(f"Nearby text: {' '.join(nearby)[:500]}")
            text = "\n".join(lines)
            chunks.append(ChunkDraft(
                id=chunk_id(version_id, "image", [el.id]), kind="image", seq=seq, heading_path=path, text=text,
                context_header=header, element_ids=[el.id], regions=_regions([el]), page_start=el.page,
                page_end=el.page, category=category, parent_id=parent.id if parent else None,
                image_key=el.image_key, token_count=estimate_tokens(text)))
            seq += 1
    return chunks
