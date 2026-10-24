"""Semantic comparison: align candidate units to reference passages with the hybrid retriever, then
judge each aligned set with an LLM (strict JSON, validated citations) or, offline, with a
polarity/value heuristic. Also finds reference rules the candidate never addresses ("missing")."""

import logging
import re
from dataclasses import dataclass

from pydantic import BaseModel

from stylelens.compare.cite import VersionIndex
from stylelens.compare.deterministic import fid
from stylelens.compare.schema import Category, FindingModel, Severity, finding_category
from stylelens.extraction.common import QUANTITY_RE, clauses, polarity
from stylelens.llm.base import LLMRefusal, LLMUnavailable
from stylelens.llm.client import generate_json, llm_available
from stylelens.retrieval.models import LexicalReranker, get_reranker
from stylelens.retrieval.search import retrieve
from stylelens.schema.profile import RuleItem, StyleProfile

log = logging.getLogger(__name__)
BATCH = 5


@dataclass
class Unit:
    key: str
    text: str
    chunk_id: str
    element_id: str | None
    category: str | None
    rule: RuleItem | None = None


@dataclass
class Aligned:
    unit: Unit
    ref_chunk_ids: list[str]
    scores: list[float]


def candidate_units(cand: StyleProfile, ci: VersionIndex, guide_like: bool) -> list[Unit]:
    units: list[Unit] = []
    if guide_like:
        for r in cand.all_rules():
            ref = r.source_refs[0] if r.source_refs else None
            cid = ci.element_to_chunk.get(ref.element_id) if ref else None
            if cid:
                units.append(Unit(f"u{len(units) + 1}", r.statement, cid, ref.element_id, r.category, r))
    else:
        for ch in sorted(ci.chunks.values(), key=lambda c: c.seq):
            if ch.kind == "child" and len(ch.text) > 20:
                units.append(Unit(f"u{len(units) + 1}", ch.text[:1500], ch.id, (ch.element_ids or [None])[0], ch.category))
    return units


async def align(units: list[Unit], ref_version: str) -> list[Aligned]:
    floor = get_reranker().default_threshold / 2
    out = []
    for u in units:
        res = await retrieve(u.text, [ref_version], top_k=4, threshold=0.0)
        hits = [h for h in res.hits if h.score >= floor]
        out.append(Aligned(u, [h.chunk_id for h in hits], [h.score for h in hits]))
    return out


# -- LLM judge ------------------------------------------------------------------------------------
class JudgeCitation(BaseModel):
    id: str
    quote: str


class JudgeFinding(BaseModel):
    category: Category
    status: str  # compliant | deviation | conflict | new
    severity: Severity
    summary: str
    reasoning: str
    reference_citations: list[JudgeCitation]
    candidate_citations: list[JudgeCitation]
    confidence: float


class JudgeOutput(BaseModel):
    findings: list[JudgeFinding]


def _render_batch(batch: list[Aligned], ri: VersionIndex, ci: VersionIndex) -> tuple[str, dict[str, str], dict[str, str]]:
    cand_alias: dict[str, str] = {}
    ref_alias: dict[str, str] = {}
    parts = []
    for a in batch:
        ca = f"C{len(cand_alias) + 1}"
        cand_alias[ca] = a.unit.chunk_id
        refs = []
        for rid in a.ref_chunk_ids:
            alias = next((k for k, v in ref_alias.items() if v == rid), None)
            if alias is None:
                alias = f"R{len(ref_alias) + 1}"
                ref_alias[alias] = rid
            refs.append(alias)
        parts.append(f'<candidate id="{ca}">\n{a.unit.text}\n</candidate>\nAligned reference passages: {", ".join(refs) or "none"}')
    ref_blocks = []
    for alias, rid in ref_alias.items():
        ch = ri.chunks[rid]
        ref_blocks.append(f'<reference id="{alias}" section="{" > ".join(ch.heading_path or [])}">\n{ch.text}\n</reference>')
    return "\n\n".join(ref_blocks + parts), cand_alias, ref_alias


async def judge_llm(aligned: list[Aligned], ri: VersionIndex, ci: VersionIndex, ref_title: str, cand_title: str,
                    progress=None) -> list[FindingModel]:
    out: list[FindingModel] = []
    batches = [aligned[i : i + BATCH] for i in range(0, len(aligned), BATCH)]
    for bi, batch in enumerate(batches):
        rendered, cand_alias, ref_alias = _render_batch(batch, ri, ci)
        try:
            res = await generate_json("generation", "judge_pair", JudgeOutput, max_tokens=8000, effort="medium",
                                      reference_title=ref_title, candidate_title=cand_title, pairs=rendered)
        except (LLMUnavailable, LLMRefusal, ValueError) as exc:
            log.warning("judge batch %d failed: %s", bi, exc)
            continue
        for f in res.findings:
            status = f.status if f.status in ("compliant", "deviation", "conflict", "new") else "deviation"
            ref_c = [c for c in (ri.cite_chunk(ref_alias[x.id], x.quote) for x in f.reference_citations
                                 if x.id in ref_alias) if c]
            cand_c = [c for c in (ci.cite_chunk(cand_alias[x.id], x.quote) for x in f.candidate_citations
                                  if x.id in cand_alias) if c]
            # Every finding needs a real citation: reference for judged statuses, candidate always.
            if not cand_c or (status != "new" and not ref_c):
                log.info("dropping uncited finding: %s", f.summary[:80])
                continue
            out.append(FindingModel(
                finding_id=fid("rule"), category=f.category, status=status, severity=f.severity,
                summary=f.summary, reasoning=f.reasoning, reference_citations=ref_c[:3], candidate_citations=cand_c[:2],
                confidence=max(0.0, min(1.0, f.confidence)), method="llm"))
        if progress:
            await progress((bi + 1) / len(batches), f"Judged {min((bi + 1) * BATCH, len(aligned))} of {len(aligned)}")
    return out


# -- offline heuristic judge ----------------------------------------------------------------------
def _rules_in_chunks(ref: StyleProfile, ri: VersionIndex, chunk_ids: list[str]) -> list[RuleItem]:
    els = {e for cid in chunk_ids for e in (ri.chunks[cid].element_ids or [])}
    return [r for r in ref.all_rules() if any(s.element_id in els for s in r.source_refs)]


def _shown(text: str) -> list[str]:
    return list(dict.fromkeys(QUANTITY_RE.findall(text)))


def _values(text: str) -> set[str]:
    return {re.sub(r"\s+", "", v.lower()) for v in QUANTITY_RE.findall(text)}


def judge_heuristic(aligned: list[Aligned], ref: StyleProfile, ri: VersionIndex, ci: VersionIndex) -> list[FindingModel]:
    lex = LexicalReranker()
    out = []
    for a in aligned:
        u = a.unit
        if u.rule is None:
            out += _asset_value_checks(a, ref, ri, ci, lex)
            continue
        cand_cite = ci.cite_chunk(u.chunk_id, u.text)
        if not cand_cite:
            continue
        rules = _rules_in_chunks(ref, ri, a.ref_chunk_ids)
        if not rules:
            out.append(FindingModel(
                finding_id=fid("rule"), category=finding_category(u.category or "misc_rules"), status="new",
                severity="info", summary=f"Not addressed by the reference: {u.text}", candidate_citations=[cand_cite],
                confidence=0.5, method="heuristic"))
            continue
        scores = lex.score(u.text, [r.statement for r in rules])
        same = finding_category(u.category or "")
        uvals = _values(u.text)
        boosted = [sc + (0.25 if finding_category(r.category) == same else 0.0)
                   + (0.1 if uvals and _values(r.statement) else 0.0) for r, sc in zip(rules, scores, strict=True)]
        best_i = max(range(len(rules)), key=lambda i: (boosted[i], -i))
        best, sim = rules[best_i], scores[best_i]
        ref_cites = ri.cite_refs([r.model_dump() for r in best.source_refs])
        if sim < 0.3 or not ref_cites:
            continue
        cat = finding_category(best.category)
        # Judge against the clause of the reference rule that best matches the candidate
        ref_clauses = clauses(best.statement) or [best.statement]
        cscores = lex.score(u.text, ref_clauses)
        clause = ref_clauses[max(range(len(ref_clauses)), key=lambda i: (cscores[i], -i))]
        ref_pol = polarity(clause)
        cv, rv = _values(u.text), _values(best.statement)
        conf = round(0.4 + sim / 2, 2)
        if cv and rv:
            if cv & rv:
                out.append(FindingModel(
                    finding_id=fid("rule"), category=cat, status="compliant", severity="info",
                    summary=f"Same value as the guide ({', '.join(sorted(cv & rv))}): {best.statement}",
                    reference_citations=ref_cites, candidate_citations=[cand_cite], confidence=conf, method="heuristic"))
            else:
                out.append(FindingModel(
                    finding_id=fid("rule"), category=cat, status="deviation", severity="major",
                    summary=f"Different value: candidate {', '.join(_shown(u.text))} vs guide {', '.join(_shown(best.statement))}.",
                    reasoning=f"“{u.text}” vs “{best.statement}”",
                    reference_citations=ref_cites, candidate_citations=[cand_cite], confidence=conf, method="heuristic"))
        elif u.rule.polarity != ref_pol:
            sev = "critical" if best.normative_level == "must" and cat in ("logo_rules", "accessibility") else "major"
            out.append(FindingModel(
                finding_id=fid("rule"), category=cat, status="conflict", severity=sev,
                summary=f"Contradicts the guide: “{u.text}” vs “{clause}”",
                reasoning="The candidate rule has the opposite polarity (do vs don't) of the closest reference rule.",
                reference_citations=ref_cites, candidate_citations=[cand_cite], confidence=conf, method="heuristic"))
        elif sim >= 0.5:
            out.append(FindingModel(
                finding_id=fid("rule"), category=cat, status="compliant", severity="info",
                summary=f"Consistent with the guide: {best.statement}",
                reference_citations=ref_cites, candidate_citations=[cand_cite], confidence=round(sim, 2),
                method="heuristic"))
    return out


def _asset_value_checks(a: Aligned, ref: StyleProfile, ri: VersionIndex, ci: VersionIndex,
                        lex: LexicalReranker) -> list[FindingModel]:
    """Offline check for copy/assets: sentences stating a quantity that differs from the closest rule."""
    from stylelens.chat.text import split_sentences

    out = []
    rules = [r for r in _rules_in_chunks(ref, ri, a.ref_chunk_ids) if _values(r.statement)]
    if not rules:
        return out
    for sent in split_sentences(a.unit.text):
        sv = _values(sent)
        if not sv:
            continue
        scores = lex.score(sent, [r.statement for r in rules])
        i = max(range(len(rules)), key=lambda k: (scores[k], -k))
        best, sim = rules[i], scores[i]
        rv = _values(best.statement)
        if sim < 0.4 or sv & rv:
            continue
        ref_cites = ri.cite_refs([x.model_dump() for x in best.source_refs])
        cand_cite = ci.cite_chunk(a.unit.chunk_id, sent)
        if ref_cites and cand_cite:
            out.append(FindingModel(
                finding_id=fid("rule"), category=finding_category(best.category), status="deviation",
                severity="major" if best.normative_level == "must" else "minor",
                summary=f"States {', '.join(_shown(sent))} where the guide specifies {', '.join(_shown(best.statement))}.",
                reasoning=f"“{sent.strip()}” vs “{best.statement}”", reference_citations=ref_cites,
                candidate_citations=[cand_cite], confidence=round(0.4 + sim / 2, 2), method="heuristic"))
    return out


async def find_missing(ref: StyleProfile, cand: StyleProfile, ri: VersionIndex, cand_version: str,
                       aligned: list[Aligned]) -> list[FindingModel]:
    """Must-level reference rules the candidate never addresses. A rule counts as addressed when a
    candidate unit aligned to the section it lives in, or when it can be retrieved from the candidate."""
    lex = LexicalReranker()
    addressed: set[str] = set()
    for a in aligned:
        rules = _rules_in_chunks(ref, ri, a.ref_chunk_ids)
        if not rules:
            continue
        for r, sc in zip(rules, lex.score(a.unit.text, [r.statement for r in rules]), strict=True):
            if sc >= 0.3:
                addressed.add(r.id)
    out: list[FindingModel] = []
    by_cat: dict[str, list[RuleItem]] = {}
    for r in ref.all_rules():
        cat = finding_category(r.category)
        if r.normative_level != "must" or cat == "colors":  # palette gaps are checked deterministically
            continue
        if r.id in addressed:
            continue
        res = await retrieve(r.statement, [cand_version], top_k=1)
        if not res.covered:
            by_cat.setdefault(cat, []).append(r)
    cand_cats = {finding_category(r.category) for r in cand.all_rules()}
    for cat, rules in sorted(by_cat.items()):
        if cat not in cand_cats:
            cites = [c for r in rules[:3] for c in ri.cite_refs([s.model_dump() for s in r.source_refs], 1)]
            out.append(FindingModel(
                finding_id=fid("missing"), category=cat, status="missing",
                severity="major" if len(rules) >= 2 else "minor",
                summary=f"The candidate has no {cat.replace('_', ' ')} guidance; the reference sets {len(rules)} "
                        f"required rule{'s' if len(rules) > 1 else ''} here.",
                reasoning="Examples: " + "; ".join(r.statement for r in rules[:3]),
                reference_citations=cites, confidence=0.75, method="deterministic",
                data={"rules": [r.statement for r in rules]}))
            continue
        for r in rules[:3]:
            cites = ri.cite_refs([s.model_dump() for s in r.source_refs], 1)
            if cites:
                out.append(FindingModel(
                    finding_id=fid("missing"), category=cat, status="missing", severity="info",
                    summary=f"Not addressed by the candidate: {r.statement}", reference_citations=cites,
                    confidence=0.55, method="deterministic"))
    return out


def use_llm() -> bool:
    return llm_available("generation")


def dedupe(findings: list[FindingModel]) -> list[FindingModel]:
    """Drop findings that restate another finding on the same candidate element and reference rule."""
    seen: dict[tuple, FindingModel] = {}
    order = {"deterministic": 0, "visual": 1, "llm": 2, "heuristic": 3}
    for f in sorted(findings, key=lambda f: order.get(f.method, 9)):
        cand = tuple(sorted({c.element_id or c.chunk_id for c in f.candidate_citations}))
        ref = tuple(sorted({c.element_id or c.chunk_id for c in f.reference_citations}))
        key = (f.category, cand, ref) if cand else (f.category, f.status, ref, f.summary)
        if rule := (f.data or {}).get("rule"):
            # Vision findings: one per rule and candidate page (several rules share a figure / page anchor)
            key = ("vision", rule["id"], f.status, tuple(c.page for c in f.candidate_citations))
        if key in seen and seen[key].status != "compliant":
            continue
        seen[key] = f
    return list(seen.values())
