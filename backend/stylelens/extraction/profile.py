"""Build the canonical StyleProfile for a guide version."""

import logging

from pydantic import BaseModel
from sqlalchemy import select

from stylelens.colors import hex_to_lab
from stylelens.db.models import Element, Guide, GuideVersion
from stylelens.db.session import SessionLocal
from stylelens.extraction.colors import extract_colors
from stylelens.extraction.common import El, from_row
from stylelens.extraction.images import extract_images
from stylelens.extraction.rules import heuristic_rules, llm_rules
from stylelens.extraction.typography import extract_typography
from stylelens.llm.base import LLMRefusal, LLMUnavailable
from stylelens.llm.client import generate_json, llm_available, model_spec
from stylelens.schema.profile import RULE_CATEGORIES, ColorItem, ProfileStats, StyleProfile
from stylelens.storage import aget

log = logging.getLogger(__name__)


class ColorVerdict(BaseModel):
    id: str
    keep: bool
    name: str | None
    role: str | None
    status: str  # approved | prohibited
    usage: list[str]


class ColorReview(BaseModel):
    colors: list[ColorVerdict]


async def _review_colors(colors: list[ColorItem], title: str | None, warnings: list[str]) -> list[ColorItem]:
    """LLM validation of regex/pixel colour candidates: drop false positives, fix names/roles."""
    if not colors or not llm_available("extraction"):
        return colors
    listing = "\n".join(
        f"- id={c.id} hex={c.hex} name={c.name or '?'} role={c.role or '?'} status={c.status} "
        f"origin={'+'.join(c.origin)} context: " + " | ".join(c.usage[:3])[:500]
        for c in colors)
    try:
        review = await generate_json("extraction", "validate_colors", ColorReview,
                                     guide_title=title or "Untitled guide", candidates=listing)
    except (LLMUnavailable, LLMRefusal, ValueError) as exc:
        warnings.append(f"Color validation skipped: {exc}")
        return colors
    verdicts = {v.id: v for v in review.colors}
    out = []
    for c in colors:
        v = verdicts.get(c.id)
        if v is None:
            out.append(c)
            continue
        if not v.keep:
            continue
        c.name = v.name or c.name
        c.role = v.role or c.role
        c.status = "prohibited" if v.status == "prohibited" else "approved"
        if v.usage:
            c.usage = list(dict.fromkeys(v.usage + c.usage))[:8]
        if "llm" not in c.origin:
            c.origin.append("llm")
        out.append(c)
    return out


async def build_profile(version_id: str, progress=None) -> StyleProfile:
    async def report(p: float, msg: str):
        if progress:
            await progress(p, msg)

    async with SessionLocal() as session:
        version = await session.get(GuideVersion, version_id)
        guide = await session.get(Guide, version.guide_id)
        rows = list(await session.scalars(
            select(Element).where(Element.version_id == version_id).order_by(Element.seq)))
        title, doc_meta, fmt, page_count = version.title, version.meta or {}, guide.format, version.page_count
    elements: list[El] = [from_row(r) for r in rows]
    warnings: list[str] = []

    images: dict[str, bytes] = {}
    for el in elements:
        if el.image_key:
            try:
                images[el.image_key] = await aget(el.image_key)
            except Exception:  # noqa: BLE001
                warnings.append(f"Missing image asset for {el.id}")

    await report(0.1, "Colors")
    colors, palettes = extract_colors(elements, images, image_only_doc=fmt == "image")
    colors = await _review_colors(colors, title, warnings)
    for c in colors:
        c.lab = [round(v, 2) for v in hex_to_lab(c.hex)]

    await report(0.3, "Typography")
    typography, fonts = extract_typography(elements, doc_meta)

    await report(0.45, "Rules")
    llm_used = False
    if llm_available("extraction"):
        try:
            rules = await llm_rules(elements, title)
            llm_used = True
        except (LLMUnavailable, LLMRefusal, ValueError) as exc:
            warnings.append(f"LLM rule extraction failed, used heuristics: {exc}")
            rules = heuristic_rules(elements)
    else:
        warnings.append("No LLM configured: rules extracted with heuristics. Set ANTHROPIC_API_KEY for full extraction.")
        rules = heuristic_rules(elements)

    await report(0.75, "Images")
    image_items = await extract_images(elements, images, palettes, title, warnings)

    profile = StyleProfile(version_id=version_id, title=title, colors=colors, typography=typography,
                           images=image_items, fonts_detected=fonts)
    for i, r in enumerate(rules):
        r.id = f"rule-{i + 1}"
        getattr(profile, r.category).append(r)
    first_para = next((e.text for e in elements if e.type == "paragraph" and len(e.text) > 60), None)
    profile.summary = first_para
    profile.stats = ProfileStats(
        pages=page_count, elements=len(elements), rules=len(rules), colors=len(colors), images=len(image_items),
        llm_used=llm_used, extraction_model=model_spec("extraction") if llm_used else None, warnings=warnings)
    assert all(hasattr(profile, c) for c in RULE_CATEGORIES)
    await report(1.0, f"{len(colors)} colors, {len(typography)} type styles, {len(rules)} rules")
    return profile
