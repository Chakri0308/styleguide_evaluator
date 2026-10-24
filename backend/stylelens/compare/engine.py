"""Comparison orchestration: aligning → deterministic checks → judging → scoring."""

import logging
from collections import Counter, defaultdict
from datetime import UTC, datetime

from sqlalchemy import delete
from sqlalchemy.orm.attributes import flag_modified

from stylelens import events
from stylelens.compare import deterministic as det
from stylelens.compare import semantic, visual
from stylelens.compare.cite import load_index
from stylelens.compare.schema import CATEGORIES, FindingModel
from stylelens.db.models import Comparison, Finding, Guide, GuideVersion, StyleProfile as ProfileRow
from stylelens.db.session import SessionLocal
from stylelens.schema.profile import StyleProfile

log = logging.getLogger(__name__)
SEVERITY_WEIGHT = {"critical": 4.0, "major": 3.0, "minor": 1.5, "info": 0.5}
STATUS_ORDER = {"conflict": 0, "deviation": 1, "missing": 2, "new": 3, "compliant": 4}
SEVERITY_ORDER = {"critical": 0, "major": 1, "minor": 2, "info": 3}


class CompareReporter:
    def __init__(self, comparison_id: str):
        self.id = comparison_id

    async def update(self, stage: str, *, status=None, progress=None, message=None, overall=None, error=None):
        async with SessionLocal() as session:
            c = await session.get(Comparison, self.id)
            if c is None:
                return
            st = dict(c.stages.get(stage, {"status": "pending", "progress": 0.0, "message": ""}))
            if status:
                st["status"] = status
                if status == "running":
                    st.setdefault("started_at", events.now_iso())
                if status in ("done", "failed"):
                    st["finished_at"] = events.now_iso()
                    if status == "done":
                        st["progress"] = 1.0
            if progress is not None:
                st["progress"] = round(max(0.0, min(1.0, progress)), 3)
            if message is not None:
                st["message"] = message
            c.stages = {**c.stages, stage: st}
            flag_modified(c, "stages")
            if overall:
                c.status = overall
                if overall in ("ready", "failed"):
                    c.finished_at = datetime.now(UTC)
            if error:
                c.error = error
            await session.commit()
            payload = {"comparison_id": c.id, "status": c.status, "stages": c.stages, "error": c.error}
        await events.publish("compare", self.id, payload)


def score(findings: list[FindingModel]) -> dict:
    by_cat: dict[str, list[FindingModel]] = defaultdict(list)
    for f in findings:
        by_cat[f.category].append(f)
    categories = {}
    total_pass = total_fail = 0.0
    for cat in CATEGORIES:
        fs = by_cat.get(cat, [])
        if not fs:
            continue
        passes = sum(1.0 for f in fs if f.status == "compliant")
        fails = sum(SEVERITY_WEIGHT[f.severity] for f in fs if f.status != "compliant")
        total_pass += passes + 1
        total_fail += fails
        # +1 prior pass per category keeps sparse reports (one finding) from reading as total failure
        categories[cat] = {
            "score": round(100 * (passes + 1) / (passes + 1 + fails), 1),
            "counts": dict(Counter(f.status for f in fs)),
            "total": len(fs),
        }
    overall = round(100 * total_pass / (total_pass + total_fail), 1) if total_pass + total_fail else 100.0
    return {
        "score": overall,
        "categories": categories,
        "by_status": dict(Counter(f.status for f in findings)),
        "by_severity": dict(Counter(f.severity for f in findings if f.status != "compliant")),
        "total": len(findings),
    }


async def _load(version_id: str) -> StyleProfile:
    async with SessionLocal() as session:
        row = await session.get(ProfileRow, version_id)
        if row is None:
            raise RuntimeError("Guide profile missing; re-ingest the guide.")
        return StyleProfile.model_validate(row.data)


async def run_comparison(comparison_id: str) -> None:
    r = CompareReporter(comparison_id)
    stage = "aligning"
    try:
        async with SessionLocal() as session:
            comp = await session.get(Comparison, comparison_id)
            rv, cv = comp.reference_version_id, comp.candidate_version_id
            ref_title = (await session.get(GuideVersion, rv)).title or "Reference guide"
            cand_v = await session.get(GuideVersion, cv)
            cand_title = cand_v.title or (await session.get(Guide, cand_v.guide_id)).name
        ref, cand = await _load(rv), await _load(cv)
        ri, ci = await load_index(rv), await load_index(cv)
        guide_like = len(cand.all_rules()) >= 6
        det.reset_ids()

        await r.update("aligning", status="running", overall="processing")
        units = semantic.candidate_units(cand, ci, guide_like)
        aligned = await semantic.align(units, rv)
        await r.update("aligning", status="done",
                       message=f"{len(units)} candidate {'rules' if guide_like else 'passages'} aligned")

        stage = "deterministic_checks"
        await r.update(stage, status="running")
        findings = []
        findings += det.check_colors(ref, cand, ri, ci, guide_like)
        findings += det.check_contrast(ref, cand, ri, ci)
        findings += det.check_typography(ref, cand, ri, ci)
        findings += det.check_phrases(ref, ri, ci)
        findings += det.check_logo_backgrounds(ref, cand, ri, ci)
        findings += det.check_visual_examples(ref, cand, ri, ci)
        await r.update(stage, status="done", message=f"{len(findings)} findings from color, contrast, type and copy checks")

        stage = "visual_checks"
        await r.update(stage, status="running")
        visual_stats = None
        if visual.available(ref):
            checker = visual.VisualChecker(comparison_id, ref, ri, ci, ref_title, cand_title)

            async def vprog(p, m):
                await r.update("visual_checks", progress=p, message=m)

            vf = await checker.run(vprog)
            findings += vf
            st = checker.stats
            visual_stats = {"pages": st.pages, "rules": st.rules, "judged": st.judged, "confirmed": st.confirmed,
                            "rejected_on_second_look": st.rejected, "uncertain": st.uncertain, "errors": st.errors[:5]}
            msg = (f"{st.rules} visual rules on {st.pages} page(s): {st.confirmed} confirmed deviations, "
                   f"{st.rejected} rejected on second look")
        else:
            msg = "Skipped (needs a vision model and visual rules in the reference)"
        await r.update(stage, status="done", message=msg)

        stage = "judging"
        await r.update(stage, status="running")
        if semantic.use_llm():
            async def prog(p, m):
                await r.update("judging", progress=p, message=m)

            judged = await semantic.judge_llm(aligned, ri, ci, ref_title, cand_title, prog)
            how = "LLM judgment"
        else:
            judged = semantic.judge_heuristic(aligned, ref, ri, ci)
            how = "heuristic judgment (no LLM configured)"
        findings += judged
        if guide_like:
            findings += await semantic.find_missing(ref, cand, ri, cv, aligned)
        findings = semantic.dedupe(findings)
        await r.update(stage, status="done", message=f"{len(judged)} findings from {how}")

        stage = "scoring"
        await r.update(stage, status="running")
        findings.sort(key=lambda f: (STATUS_ORDER[f.status], SEVERITY_ORDER[f.severity], f.category, f.finding_id))
        summary = score(findings)
        summary["mode"] = "llm" if semantic.use_llm() else "offline"
        summary["candidate_kind"] = "style_guide" if guide_like else "asset"
        summary["visual"] = visual_stats
        async with SessionLocal() as session:
            await session.execute(delete(Finding).where(Finding.comparison_id == comparison_id))
            for i, f in enumerate(findings):
                session.add(Finding(
                    comparison_id=comparison_id, seq=i, finding_id=f.finding_id, category=f.category, status=f.status,
                    severity=f.severity, method=f.method, summary=f.summary, reasoning=f.reasoning,
                    reference_citations=[c.model_dump() for c in f.reference_citations],
                    candidate_citations=[c.model_dump() for c in f.candidate_citations],
                    confidence=f.confidence, data=f.data))
            comp = await session.get(Comparison, comparison_id)
            comp.score = summary["score"]
            comp.summary = summary
            await session.commit()
        await r.update(stage, status="done", message=f"Score {summary['score']:.0f}/100", overall="ready")
    except Exception as exc:  # noqa: BLE001
        log.exception("comparison %s failed", comparison_id)
        await r.update(stage, status="failed", message=str(exc)[:300], overall="failed", error=f"{type(exc).__name__}: {exc}")
