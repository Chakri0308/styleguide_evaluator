"""Visual rules: read the guide's diagrams (clear space, lockups, grids, misuse examples, imagery style)
with a vision model and turn them into atomic rules that keep a pointer to the illustrating figure.

Pages are chosen by what they are about (logo / layout / imagery cues) and by having something to look
at (images or little text), so text-only chapters don't cost vision calls.
"""

import logging
import re
from typing import Literal

from pydantic import BaseModel
from sqlalchemy import select

from stylelens.config import get_settings
from stylelens.db.models import Page
from stylelens.db.session import SessionLocal
from stylelens.extraction.common import El
from stylelens.llm.base import LLMRefusal, LLMUnavailable
from stylelens.llm.client import generate_json
from stylelens.schema.profile import RuleItem, SourceRef
from stylelens.storage import aget
from stylelens.visual import box_to_bbox, overlap, shrink

log = logging.getLogger(__name__)
VISUAL_CUE_RE = re.compile(
    r"logo|lock-?up|wordmark|symbol|monogram|clear\s*space|exclusion|safe\s*zone|minimum\s*size|placement|"
    r"position|grid|layout|margin|spacing|tagline|imagery|photo|illustrat|icon|misuse|incorrect|don'?t|"
    r"co-?brand|partner|signage|livery|application|templat|composition", re.I)
TEXT_HEAVY_CHARS = 2500


class VisualRuleOut(BaseModel):
    statement: str
    category: Literal["logo_rules", "spacing_grid", "imagery_rules", "color_usage", "typography_usage", "components"]
    polarity: Literal["do", "dont"]
    normative_level: Literal["must", "should", "may"]
    value: str | None
    check: str
    evidence: str
    box_2d: list[float]
    element_ids: list[str]


class VisualRulesOut(BaseModel):
    rules: list[VisualRuleOut]


def select_pages(elements: list[El], pages: list[Page], limit: int) -> list[Page]:
    by_page: dict[int, list[El]] = {}
    for e in elements:
        by_page.setdefault(e.page, []).append(e)
    scored = []
    for p in pages:
        if not p.image_key:
            continue
        els = by_page.get(p.page, [])
        text = " ".join(e.text for e in els if e.type != "image")
        cues = " ".join([text[:4000], *(" ".join(e.heading_path) for e in els[:3])])
        hits = len(VISUAL_CUE_RE.findall(cues))
        has_visual = any(e.type in ("image", "swatch") for e in els) or len(text) < TEXT_HEAVY_CHARS
        if hits and has_visual:
            scored.append((hits + 3 * sum(e.type == "image" for e in els), p))
    top = sorted(scored, key=lambda t: (-t[0], t[1].page))[:limit]
    return sorted((p for _, p in top), key=lambda p: p.page)


def _tokens(s: str) -> set[str]:
    return set(re.findall(r"[a-z0-9/½⅔]+", s.lower()))


def similar(a: str, b: str, threshold: float = 0.6) -> bool:
    ta, tb = _tokens(a), _tokens(b)
    return bool(ta and tb) and len(ta & tb) / len(ta | tb) >= threshold


def page_text(els: list[El]) -> str:
    lines = [f"[{e.id}] {e.text[:300]}" for e in els if e.type != "image" and e.text.strip()]
    return "\n".join(lines)[:6000] or "(no text)"


def to_rule(out: VisualRuleOut, page: Page, els: list[El]) -> RuleItem | None:
    frame = [0.0, 0.0, float(page.width), float(page.height)]
    fig = box_to_bbox(out.box_2d, frame)
    if not out.statement.strip():
        return None
    on_page = {e.id: e for e in els}
    anchor = max(els, key=lambda e: overlap(fig, e.bbox), default=None) if fig else None
    if anchor is None or (fig and overlap(fig, anchor.bbox) == 0):
        anchor = next((e for e in els if e.type == "image"), els[0] if els else None)
    if anchor is None:
        return None
    figure = SourceRef(element_id=anchor.id, page=page.page, bbox=fig, quote=out.evidence[:300])
    refs = [figure] + [on_page[i].ref() for i in dict.fromkeys(out.element_ids) if i in on_page][:3]
    return RuleItem(id="", category=out.category, statement=out.statement.strip(), value=out.value,
                    role=None, polarity=out.polarity, normative_level=out.normative_level, source_refs=refs,
                    visual=True, check=out.check, figure=figure)


async def extract_visual_rules(version_id: str, elements: list[El], title: str | None, existing: list[RuleItem],
                               warnings: list[str], progress=None) -> list[RuleItem]:
    """Returns new visual rules. Text rules that a diagram restates are enriched in place instead."""
    s = get_settings()
    async with SessionLocal() as session:
        pages = list(await session.scalars(select(Page).where(Page.version_id == version_id).order_by(Page.page)))
    chosen = select_pages(elements, pages, s.visual_max_reference_pages)
    by_page: dict[int, list[El]] = {}
    for e in elements:
        by_page.setdefault(e.page, []).append(e)
    found: list[RuleItem] = []
    for n, page in enumerate(chosen):
        if progress:
            await progress(n / max(len(chosen), 1), f"Reading diagrams on page {page.page}")
        els = by_page.get(page.page, [])
        try:
            render = shrink(await aget(page.image_key))
            out = await generate_json(
                "vision", "extract_visual_rules", VisualRulesOut, images=[(render, "image/png")], max_tokens=8000,
                guide_title=title or "Untitled guide", page=page.page,
                section=next((" > ".join(e.heading_path) for e in els if e.heading_path), "(none)"),
                page_text=page_text(els))
        except (LLMUnavailable, LLMRefusal, ValueError) as exc:
            warnings.append(f"Visual rules on page {page.page} skipped: {exc}")
            continue
        except Exception as exc:  # noqa: BLE001 - a bad page must not sink ingestion
            log.warning("visual rule extraction failed on page %s: %s", page.page, exc)
            warnings.append(f"Visual rules on page {page.page} skipped: {type(exc).__name__}")
            continue
        for o in out.rules:
            rule = to_rule(o, page, els)
            if rule is None or any(similar(rule.statement, r.statement, 0.8) for r in found):
                continue
            twin = next((r for r in existing if not r.visual and similar(rule.statement, r.statement)), None)
            if twin is not None:
                # The diagram illustrates a rule already stated in text: attach the figure to it
                twin.visual, twin.check, twin.figure = True, rule.check, rule.figure
                twin.value = twin.value or rule.value
                twin.source_refs = [*twin.source_refs, rule.figure][:4]
                continue
            found.append(rule)
    return found
