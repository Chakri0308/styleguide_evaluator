"""Visual rule checks: look at each candidate page with a vision model and judge it against the
reference guide's visual rules (clear space, lockups, proportions, placement, misuse, imagery style),
showing the model the guide's own figures for each rule.

Precision comes from three gates: a rule is only judged on a page where its subject was detected,
the verdict must name what was seen and where, and every deviation is re-checked by an independent
second look at a zoomed crop (with the guide's figure) before it is reported.
"""

import asyncio
import logging
import re
from dataclasses import dataclass, field
from typing import Literal

from pydantic import BaseModel
from sqlalchemy import select

from stylelens.compare.cite import VersionIndex
from stylelens.compare.deterministic import fid
from stylelens.compare.schema import CitationRef, FindingModel, finding_category
from stylelens.config import get_settings
from stylelens.db.models import Page
from stylelens.db.session import SessionLocal
from stylelens.llm.base import LLMRefusal, LLMUnavailable
from stylelens.llm.client import generate_json, llm_available, model_spec
from stylelens.schema.profile import RuleItem, StyleProfile
from stylelens.storage import aget, aput
from stylelens.visual import box_to_bbox, crop, overlap, shrink

log = logging.getLogger(__name__)
VISUAL_CATEGORIES = {"logo_rules", "imagery_rules", "spacing_grid"}
MAX_RULES = 60
BATCH = 10
MAX_FIGURES = 6
CONCURRENCY = 4
SEVERITY_RANK = {"info": 0, "minor": 1, "major": 2, "critical": 3}
GROUP_SUBJECTS = {
    "logo": {"logo", "tagline", "cta"},
    "imagery": {"photo", "illustration", "icon"},
    "layout": {"layout", "headline", "cta", "chart", "logo", "tagline", "photo", "illustration", "icon"},
}
LOGO_RE = re.compile(r"logo|lock-?up|wordmark|symbol|monogram|tagline|clear\s*space|exclusion", re.I)
IMAGERY_RE = re.compile(r"photo|imagery|image|illustrat|icon", re.I)

SubjectKind = Literal["logo", "tagline", "cta", "headline", "photo", "illustration", "icon", "chart", "layout"]


class Subject(BaseModel):
    kind: SubjectKind
    label: str
    box_2d: list[float]


class SubjectsOut(BaseModel):
    subjects: list[Subject]


class RuleVerdict(BaseModel):
    rule: str
    applicable: bool
    status: Literal["compliant", "deviation", "uncertain"]
    observation: str
    measurement: str | None
    reasoning: str
    summary: str
    severity: Literal["critical", "major", "minor", "info"]
    box_2d: list[float]
    confidence: float


class VisualCheckOut(BaseModel):
    verdicts: list[RuleVerdict]


class VerifyOut(BaseModel):
    status: Literal["compliant", "deviation", "uncertain"]
    measurement: str | None
    reasoning: str
    confidence: float


@dataclass
class Target:
    """A candidate page render (or, for formats without renders, an embedded image)."""

    page: int
    image: bytes
    frame: list[float] | None  # page-point box the image covers; None when unknown
    element_id: str | None = None


@dataclass
class Stats:
    pages: int = 0
    rules: int = 0
    judged: int = 0
    confirmed: int = 0
    rejected: int = 0
    uncertain: int = 0
    errors: list[str] = field(default_factory=list)


def visual_rules(ref: StyleProfile) -> list[RuleItem]:
    rules = [r for r in ref.all_rules() if r.visual or r.category in VISUAL_CATEGORIES]
    rules.sort(key=lambda r: (not r.visual, {"must": 0, "should": 1, "may": 2}[r.normative_level]))
    return rules[:MAX_RULES]


def rule_group(r: RuleItem) -> str:
    if r.category == "logo_rules" or LOGO_RE.search(r.statement):
        return "logo"
    if r.category == "imagery_rules" or IMAGERY_RE.search(r.statement):
        return "imagery"
    return "layout"


def describe_rule(label: str, r: RuleItem, fig: str | None) -> str:
    parts = [f"{label} [{r.normative_level} · {r.polarity} · {r.category}] {r.statement}"]
    if r.value:
        parts.append(f"value: {r.value}")
    if r.check:
        parts.append(f"check: {r.check}")
    if fig:
        parts.append(f"reference figure: {fig}")
    return " | ".join(parts)


def clamp_severity(sev: str, r: RuleItem) -> str:
    if r.normative_level == "must" and SEVERITY_RANK[sev] < SEVERITY_RANK["major"]:
        return "major"
    if r.normative_level == "may" and SEVERITY_RANK[sev] > SEVERITY_RANK["minor"]:
        return "minor"
    return "minor" if sev == "info" else sev


class VisualChecker:
    def __init__(self, comparison_id: str, ref: StyleProfile, ri: VersionIndex, ci: VersionIndex,
                 ref_title: str, cand_title: str):
        self.comparison_id = comparison_id
        self.ref, self.ri, self.ci = ref, ri, ci
        self.ref_title, self.cand_title = ref_title, cand_title
        self.rules = visual_rules(ref)
        self.labels = {f"R{i + 1}": r for i, r in enumerate(self.rules)}
        self.stats = Stats(rules=len(self.rules))
        self._ref_pages: dict[int, tuple[bytes, list[float]] | None] = {}
        self._figures: dict[str, bytes | None] = {}
        self._sem = asyncio.Semaphore(CONCURRENCY)
        self._lock = asyncio.Lock()

    # -- inputs --------------------------------------------------------------------------------
    async def targets(self) -> list[Target]:
        limit = get_settings().visual_max_candidate_pages
        async with SessionLocal() as session:
            pages = list(await session.scalars(
                select(Page).where(Page.version_id == self.ci.version_id).order_by(Page.page)))
        out = []
        for p in pages:
            if p.image_key and len(out) < limit:
                out.append(Target(p.page, shrink(await aget(p.image_key)), [0.0, 0.0, float(p.width), float(p.height)]))
        if out:
            return out
        # No page renders (DOCX/PPTX/HTML): judge the embedded images instead
        for el in sorted(self.ci.elements.values(), key=lambda e: e.seq):
            if el.type == "image" and el.image_key and len(out) < limit:
                try:
                    out.append(Target(el.page, shrink(await aget(el.image_key)), el.bbox, el.id))
                except Exception:  # noqa: BLE001 - unreadable asset
                    continue
        return out

    async def ref_page(self, page: int) -> tuple[bytes, list[float]] | None:
        async with self._lock:
            if page not in self._ref_pages:
                async with SessionLocal() as session:
                    row = await session.scalar(select(Page).where(Page.version_id == self.ri.version_id, Page.page == page))
                self._ref_pages[page] = (
                    (await aget(row.image_key), [0.0, 0.0, float(row.width), float(row.height)])
                    if row is not None and row.image_key else None)
            return self._ref_pages[page]

    async def figure_png(self, r: RuleItem) -> bytes | None:
        if r.figure is None or r.figure.bbox is None:
            return None
        key = f"{r.figure.page}:{r.figure.bbox}"
        if key not in self._figures:
            page = await self.ref_page(r.figure.page)
            self._figures[key] = crop(page[0], page[1], r.figure.bbox, pad=0.08, min_frac=0.15) if page else None
        return self._figures[key]

    # -- regions and citations -----------------------------------------------------------------
    def region(self, t: Target, box: list[float]) -> list[float] | None:
        return box_to_bbox(box, t.frame) if t.frame else None

    def cand_cite(self, t: Target, bbox: list[float] | None, quote: str) -> CitationRef | None:
        if t.element_id:
            return self.ci.cite_element(t.element_id, quote, bbox=bbox)
        return self.ci.cite_region(t.page, bbox, quote)

    async def save(self, name: str, png: bytes | None) -> str | None:
        if png is None:
            return None
        key = f"comparisons/{self.comparison_id}/visual/{name}.png"
        await aput(key, png, "image/png")
        return f"/assets/{key}"

    # -- model calls ---------------------------------------------------------------------------
    async def detect(self, t: Target) -> list[Subject]:
        out = await generate_json("vision", "detect_visual_subjects", SubjectsOut, images=[(t.image, "image/png")],
                                  max_tokens=3000, document_title=self.cand_title, page=t.page)
        return out.subjects

    async def judge(self, t: Target, labels: list[str], subjects: list[Subject]) -> list[RuleVerdict]:
        figs: dict[tuple, str] = {}
        images: list[tuple[bytes, str]] = [(t.image, "image/png")]
        lines = []
        for label in labels:
            r = self.labels[label]
            fig_label = None
            if r.figure is not None and r.figure.bbox is not None:
                key = (r.figure.page, tuple(r.figure.bbox))
                if key not in figs and len(figs) < MAX_FIGURES and (png := await self.figure_png(r)):
                    figs[key] = f"F{len(figs) + 1}"
                    images.append((png, "image/png"))
                fig_label = figs.get(key)
                fig_label = f"{fig_label} (guide p. {r.figure.page})" if fig_label else None
            lines.append(describe_rule(label, r, fig_label))
        listing = "\n".join(f"- {s.kind}: {s.label} at {[round(v) for v in s.box_2d]}" for s in subjects) or "(none)"
        out = await generate_json("vision", "visual_check", VisualCheckOut, images=images, max_tokens=8000,
                                  reference_title=self.ref_title, candidate_title=self.cand_title, page=t.page,
                                  subjects=listing, rules="\n".join(lines))
        return [v for v in out.verdicts if v.rule in labels]

    async def verify(self, t: Target, r: RuleItem, v: RuleVerdict, subjects: list[Subject]) -> tuple[VerifyOut, bytes]:
        frame = [0.0, 0.0, 1000.0, 1000.0]
        ymin, xmin, ymax, xmax = v.box_2d
        zoom = crop(t.image, frame, [xmin, ymin, xmax, ymax], pad=0.35, min_frac=0.3, mark=True)
        images = [(zoom, "image/png")]
        if fig := await self.figure_png(r):
            images.append((fig, "image/png"))
        best = max(subjects, key=lambda s: overlap([xmin, ymin, xmax, ymax], [s.box_2d[1], s.box_2d[0], s.box_2d[3], s.box_2d[2]]),
                   default=None) if subjects and len(v.box_2d) == 4 else None
        out = await generate_json("vision", "verify_visual", VerifyOut, images=images, max_tokens=2000,
                                  statement=r.statement, value=r.value or "", check=r.check or "",
                                  normative_level=r.normative_level, polarity=r.polarity,
                                  subject=best.label if best else "the outlined region")
        return out, zoom

    # -- per page --------------------------------------------------------------------------------
    async def check_target(self, t: Target) -> list[tuple[str, RuleVerdict, VerifyOut | None, bytes | None, Target]]:
        async with self._sem:
            subjects = await self.detect(t)
            kinds = {s.kind for s in subjects} | {"layout"}
            labels = [lb for lb, r in self.labels.items() if GROUP_SUBJECTS[rule_group(r)] & kinds]
            results = []
            for i in range(0, len(labels), BATCH):
                for v in await self.judge(t, labels[i:i + BATCH], subjects):
                    if not v.applicable or len(v.box_2d) != 4:
                        continue
                    self.stats.judged += 1
                    if v.status == "uncertain":
                        self.stats.uncertain += 1
                        continue
                    if v.status == "deviation":
                        ver, zoom = await self.verify(t, self.labels[v.rule], v, subjects)
                        results.append((v.rule, v, ver, zoom, t))
                    else:
                        results.append((v.rule, v, None, None, t))
            return results

    async def run(self, progress=None) -> list[FindingModel]:
        if not self.rules:
            return []
        targets = await self.targets()
        self.stats.pages = len(targets)
        done = 0

        async def one(t: Target):
            nonlocal done
            try:
                return await self.check_target(t)
            except (LLMUnavailable, LLMRefusal, ValueError) as exc:
                self.stats.errors.append(f"page {t.page}: {exc}")
                return []
            finally:
                done += 1
                if progress:
                    await progress(done / max(len(targets), 1), f"Checked page {t.page} ({done} of {len(targets)})")

        results = [x for page in await asyncio.gather(*(one(t) for t in targets)) for x in page]
        return await self.findings(results)

    async def findings(self, results) -> list[FindingModel]:
        min_conf = get_settings().visual_min_confidence
        out: list[FindingModel] = []
        compliant: dict[str, list] = {}
        for label, v, ver, zoom, t in sorted(results, key=lambda x: (x[4].page, int(x[0][1:]))):
            r = self.labels[label]
            if v.status == "compliant":
                if v.confidence >= min_conf:
                    compliant.setdefault(label, []).append((v, t))
                continue
            conf = round((v.confidence + ver.confidence) / 2, 2)
            if ver.status != "deviation" or ver.confidence < 0.5 or conf < min_conf:
                self.stats.rejected += 1
                continue
            self.stats.confirmed += 1
            f = await self.finding(r, label, "deviation", v, t, conf, ver=ver, zoom=zoom)
            if f:
                out.append(f)
        for label, items in compliant.items():
            v, t = max(items, key=lambda x: x[0].confidence)
            f = await self.finding(self.labels[label], label, "compliant", v, t, round(v.confidence, 2),
                                   extra=[(iv, it) for iv, it in items if it is not t][:2])
            if f:
                out.append(f)
        return out

    async def finding(self, r: RuleItem, label: str, status: str, v: RuleVerdict, t: Target, conf: float, *,
                      ver: VerifyOut | None = None, zoom: bytes | None = None, extra=()) -> FindingModel | None:
        from stylelens.compare.deterministic import _refs

        bbox = self.region(t, v.box_2d)
        cand = self.cand_cite(t, bbox, v.observation)
        refs = self.ri.cite_refs(_refs(r))
        if cand is None or not refs:
            return None
        cands = [cand] + [c for iv, it in extra if (c := self.cand_cite(it, self.region(it, iv.box_2d), iv.observation))]
        finding_id = fid("vis")
        if zoom is None:
            ymin, xmin, ymax, xmax = v.box_2d
            zoom = crop(t.image, [0.0, 0.0, 1000.0, 1000.0], [xmin, ymin, xmax, ymax], pad=0.35, min_frac=0.3, mark=True)
        cand_url = await self.save(f"{finding_id}-candidate", zoom)
        ref_url = await self.save(f"{finding_id}-reference", await self.figure_png(r))
        reasoning = v.reasoning
        if ver is not None:
            reasoning += f" Second look confirmed: {ver.reasoning}"
        return FindingModel(
            finding_id=finding_id, category=finding_category(r.category), status=status,
            severity="info" if status == "compliant" else clamp_severity(v.severity, r),
            summary=v.summary or v.observation, reasoning=reasoning,
            reference_citations=refs, candidate_citations=cands, confidence=conf, method="visual",
            data={
                "engine": "vision",
                "model": model_spec("vision"),
                "rule": {"id": r.id, "label": label, "statement": r.statement, "value": r.value,
                         "check": r.check, "normative_level": r.normative_level, "polarity": r.polarity,
                         "category": r.category, "from_figure": r.figure is not None},
                "observation": v.observation,
                "measurement": v.measurement,
                "verification": ver.model_dump() if ver else None,
                "reference_figure": ({"page": r.figure.page, "bbox": r.figure.bbox, "image_url": ref_url}
                                     if r.figure else None),
                "candidate_region": {"page": t.page, "bbox": bbox, "image_url": cand_url},
            })


def available(ref: StyleProfile) -> bool:
    return get_settings().visual_checks and llm_available("vision") and bool(visual_rules(ref))
