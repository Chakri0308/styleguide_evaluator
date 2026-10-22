"""Comparison evaluation: precision/recall of findings against seeded deviations (golden/compare.json)."""

import json
from pathlib import Path

from sqlalchemy import select

from stylelens.compare.engine import run_comparison
from stylelens.db.models import Comparison, Finding
from stylelens.db.session import SessionLocal
from stylelens.events import COMPARE_STAGES, initial_stages

GOLDEN = Path(__file__).parent / "golden" / "compare.json"


def _text(f: Finding) -> str:
    quotes = " ".join(c.get("quote", "") for c in [*f.reference_citations, *f.candidate_citations])
    return f"{f.summary} {f.reasoning} {quotes}".lower()


def matches(f: Finding, exp: dict) -> bool:
    return f.category == exp["category"] and f.status in exp["status"] and \
        any(k.lower() in _text(f) for k in exp["keywords"])


async def eval_compare(versions: dict[str, tuple[str, str]]) -> dict:
    golden = json.loads(GOLDEN.read_text())
    ref_v, cand_v = versions["northwind"][1], versions["northwind_partner"][1]
    async with SessionLocal() as session:
        comp = Comparison(reference_version_id=ref_v, candidate_version_id=cand_v, status="queued",
                          stages=initial_stages(COMPARE_STAGES))
        session.add(comp)
        await session.commit()
        cid = comp.id
    await run_comparison(cid)
    async with SessionLocal() as session:
        comp = await session.get(Comparison, cid)
        findings = list(await session.scalars(select(Finding).where(Finding.comparison_id == cid)))
    expected = golden["expected"]
    hit = {e["id"]: next((f.finding_id for f in findings if matches(f, e)), None) for e in expected}
    # Precision over seeded issue types; "missing" findings are reported separately because the golden
    # set lists seeded gaps, not every rule a partial candidate legitimately omits.
    flagged = [f for f in findings if f.status in ("conflict", "deviation", "new")]
    exp_issues = [e for e in expected if e["status"] != ["compliant"]]
    exp_flags = [e for e in exp_issues if e["status"] != ["missing"]]
    matched_flags = [f for f in flagged if any(matches(f, e) for e in exp_flags)]
    cited = sum(1 for f in findings if f.reference_citations or f.candidate_citations)
    return {
        "status": comp.status,
        "score": comp.score,
        "findings": len(findings),
        "recall": round(sum(1 for e in expected if hit[e["id"]]) / len(expected), 3),
        "issue_recall": round(sum(1 for e in exp_issues if hit[e["id"]]) / max(len(exp_issues), 1), 3),
        "precision@issues": round(len(matched_flags) / max(len(flagged), 1), 3),
        "findings_with_citations": f"{cited}/{len(findings)}",
        "missing_findings": sum(1 for f in findings if f.status == "missing"),
        "missed": [e["id"] for e in expected if not hit[e["id"]]],
        "unmatched_findings": [f"{f.status}/{f.category}: {f.summary[:120]}" for f in flagged if f not in matched_flags],
        "rows": [{"expected": e["id"], "finding": hit[e["id"]]} for e in expected],
    }
