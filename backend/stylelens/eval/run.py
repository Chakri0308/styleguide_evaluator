"""Evaluation harness: `make eval` / `python -m stylelens.eval.run [--answers] [--compare]`.

Ingests the sample guides (once; reused by content hash), then measures:
  * retrieval  — Recall@1/3/5, MRR, nDCG@5 on the golden questions, and abstention on out-of-scope ones
  * answers    — (with --answers, needs an LLM) keyword accuracy, citation validity, refusal behaviour
  * comparison — (with --compare) precision/recall of findings against seeded deviations

Use the overrides (--top-k, --threshold, --rrf-k, --candidates) to tune retrieval settings.
"""

import argparse
import asyncio
import hashlib
import json
import math
import os
import sys
import time
from pathlib import Path

os.environ.setdefault("JOB_MODE", "inline")


def _use_eval_database() -> None:
    """Run against `<db>_eval` (created + migrated on demand) so eval data never shows up in the app."""
    if os.environ.get("STYLELENS_EVAL_SAME_DB") == "1":
        return
    from stylelens.config import get_settings as _gs

    base = _gs().database_url
    if base.rsplit("/", 1)[-1].endswith("_eval"):
        return
    url = f"{base}_eval"
    os.environ["DATABASE_URL"] = url
    _gs.cache_clear()
    import psycopg2
    from alembic import command
    from alembic.config import Config

    sync = url.replace("+asyncpg", "")
    server, dbname = sync.rsplit("/", 1)
    conn = psycopg2.connect(f"{server}/postgres")
    conn.autocommit = True
    with conn.cursor() as cur:
        cur.execute("SELECT 1 FROM pg_database WHERE datname = %s", (dbname,))
        if cur.fetchone() is None:
            cur.execute(f'CREATE DATABASE "{dbname}"')
    conn.close()
    root = Path(__file__).resolve().parents[2]
    cfg = Config(str(root / "alembic.ini"))
    cfg.set_main_option("script_location", str(root / "alembic"))
    command.upgrade(cfg, "head")


_use_eval_database()

from sqlalchemy import select  # noqa: E402

from stylelens.config import get_settings  # noqa: E402
from stylelens.db.models import Guide, GuideVersion  # noqa: E402
from stylelens.db.session import SessionLocal  # noqa: E402
from stylelens.eval import samples  # noqa: E402

GOLDEN = Path(__file__).parent / "golden"
SAMPLE_FILES = {
    "northwind": ("northwind_guide.pdf", "reference"),
    "lumen": ("lumen_guide.pdf", "reference"),
    "northwind_partner": ("northwind_partner.pdf", "candidate"),
    "northwind_flyer": ("northwind_flyer.pdf", "candidate"),
    "lumen_release_notes": ("lumen_release_notes.md", "candidate"),
}


async def ensure_ingested(names: list[str]) -> dict[str, tuple[str, str]]:
    """Returns {name: (guide_id, version_id)}, ingesting samples whose content isn't indexed yet."""
    from stylelens.formats import detect_format, mime_for
    from stylelens.ingestion.pipeline import run_ingestion
    from stylelens.storage import aput

    data_by_file = {
        "northwind_guide.pdf": samples.northwind_guide, "lumen_guide.pdf": samples.lumen_guide,
        "northwind_partner.pdf": samples.northwind_partner_guide, "northwind_flyer.pdf": samples.northwind_flyer,
        "lumen_release_notes.md": lambda: samples.LUMEN_RELEASE_NOTES.encode(),
    }
    out = {}
    for name in names:
        filename, role = SAMPLE_FILES[name]
        data = data_by_file[filename]()
        sha = hashlib.sha256(data).hexdigest()
        async with SessionLocal() as session:
            rows = list(await session.execute(
                select(Guide, GuideVersion).join(GuideVersion, GuideVersion.id == Guide.current_version_id)
                .where(Guide.sha256 == sha, Guide.status == "ready")))
            match = next(((g, v) for g, v in rows if (v.embedding_model or "") == _embedder_name()), None)
        if match:
            out[name] = (match[0].id, match[1].id)
            continue
        print(f"  ingesting {filename} …", flush=True)
        from stylelens.events import INGEST_STAGES, initial_stages

        fmt = detect_format(filename, data[:16])
        async with SessionLocal() as session:
            g = Guide(name=f"[eval] {Path(filename).stem}", role=role, filename=filename, mime_type=mime_for(fmt, filename),
                      format=fmt, size_bytes=len(data), sha256=sha, storage_key="", status="processing")
            session.add(g)
            await session.flush()
            g.storage_key = f"guides/{g.id}/original/{filename}"
            v = GuideVersion(guide_id=g.id, version=1, status="queued", stages=initial_stages(INGEST_STAGES))
            session.add(v)
            await session.flush()
            g.current_version_id = v.id
            await session.commit()
            gid, vid = g.id, v.id
        await aput(f"guides/{gid}/original/{filename}", data)
        await run_ingestion(vid)
        async with SessionLocal() as session:
            v = await session.get(GuideVersion, vid)
            if v.status != "ready":
                raise RuntimeError(f"ingestion failed for {filename}: {v.error}")
        out[name] = (gid, vid)
    return out


def _embedder_name() -> str:
    from stylelens.retrieval.models import get_embedder

    return get_embedder().name


def _relevant(hit, item) -> bool:
    path = " > ".join(hit.heading_path).lower()
    text = hit.text.lower()
    return any(s.lower() in path for s in item["expected_sections"]) and (
        not item["expected_phrases"] or any(p.lower() in text or p.lower() in path for p in item["expected_phrases"])
    ) or any(p.lower() in text for p in item["expected_phrases"] if len(p) > 3)


async def eval_retrieval(versions: dict[str, tuple[str, str]], qa: list[dict]) -> dict:
    from stylelens.retrieval.search import retrieve

    rows = []
    for item in qa:
        vid = versions[item["guide"]][1]
        t0 = time.perf_counter()
        ranked = await retrieve(item["question"], [vid], top_k=10, threshold=0.0, use_cache=False)
        default = await retrieve(item["question"], [vid], use_cache=False)
        ms = (time.perf_counter() - t0) * 1000
        rel = [_relevant(h, item) for h in ranked.hits] if item["covered"] else []
        first = next((i for i, r in enumerate(rel) if r), None)
        dcg = sum(1 / math.log2(i + 2) for i, r in enumerate(rel[:5]) if r)
        ideal = sorted(rel, reverse=True)[:5]
        idcg = sum(1 / math.log2(i + 2) for i, r in enumerate(ideal) if r)
        rows.append({
            "id": item["id"], "covered": item["covered"], "question": item["question"],
            "first_relevant_rank": None if first is None else first + 1,
            "recall@1": first is not None and first < 1, "recall@3": first is not None and first < 3,
            "recall@5": first is not None and first < 5, "mrr": 0 if first is None else 1 / (first + 1),
            "ndcg@5": (dcg / idcg) if idcg else 0.0,
            "abstained": not default.covered, "top_section": " > ".join(ranked.hits[0].heading_path) if ranked.hits else None,
            "top_score": ranked.hits[0].score if ranked.hits else None, "ms": round(ms),
        })
    covered = [r for r in rows if r["covered"]]
    uncovered = [r for r in rows if not r["covered"]]

    def mean(key, rs):
        return round(sum(float(r[key]) for r in rs) / max(len(rs), 1), 3)

    return {
        "n_questions": len(covered), "n_out_of_scope": len(uncovered),
        "recall@1": mean("recall@1", covered), "recall@3": mean("recall@3", covered),
        "recall@5": mean("recall@5", covered), "mrr": mean("mrr", covered), "ndcg@5": mean("ndcg@5", covered),
        "false_abstentions": sum(1 for r in covered if r["abstained"]),
        "correct_abstentions": sum(1 for r in uncovered if r["abstained"]),
        "p50_ms": sorted(r["ms"] for r in rows)[len(rows) // 2],
        "rows": rows,
    }


def print_table(title: str, metrics: dict[str, object]) -> None:
    width = max(len(k) for k in metrics) + 2
    print(f"\n{title}\n" + "─" * (width + 14))
    for k, v in metrics.items():
        print(f"{k:<{width}}{v}")


async def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--answers", action="store_true", help="also evaluate generated answers (needs an LLM)")
    ap.add_argument("--compare", action="store_true", help="also evaluate the comparison engine")
    ap.add_argument("--top-k", type=int)
    ap.add_argument("--threshold", type=float)
    ap.add_argument("--rrf-k", type=int)
    ap.add_argument("--candidates", type=int)
    ap.add_argument("--show-misses", action="store_true")
    args = ap.parse_args(argv)

    s = get_settings()
    for attr, val in (("rerank_top_k", args.top_k), ("rerank_threshold", args.threshold), ("rrf_k", args.rrf_k),
                      ("retrieval_candidates", args.candidates)):
        if val is not None:
            setattr(s, attr, val)

    from stylelens.retrieval.models import get_embedder, get_reranker

    print(f"StyleLens eval · embedder={get_embedder().name} · reranker={get_reranker().name} · "
          f"threshold={s.rerank_threshold if s.rerank_threshold is not None else get_reranker().default_threshold} · rrf_k={s.rrf_k} · candidates={s.retrieval_candidates}")
    if get_embedder().name.startswith("hash"):
        print("NOTE: hashing embedder + lexical reranker are offline test models; numbers do not reflect bge-m3.")
    qa = json.loads((GOLDEN / "qa.json").read_text())
    names = sorted({q["guide"] for q in qa} | ({"northwind_partner"} if args.compare else set()))
    versions = await ensure_ingested(names)

    report: dict = {"settings": {"embedder": get_embedder().name, "reranker": get_reranker().name,
                                 "threshold": s.rerank_threshold, "rrf_k": s.rrf_k,
                                 "candidates": s.retrieval_candidates, "top_k": s.rerank_top_k}}
    r = await eval_retrieval(versions, qa)
    report["retrieval"] = r
    print_table("Retrieval", {k: v for k, v in r.items() if k != "rows"})
    if args.show_misses:
        for row in r["rows"]:
            if row["covered"] and not row["recall@3"]:
                print(f"  miss {row['id']}: {row['question']!r} → top: {row['top_section']} ({row['top_score']})")
            if not row["covered"] and not row["abstained"]:
                print(f"  answered out-of-scope {row['id']}: top: {row['top_section']} ({row['top_score']})")

    if args.answers:
        from stylelens.eval.answers import eval_answers

        a = await eval_answers(versions, qa)
        report["answers"] = a
        print_table("Answers", {k: v for k, v in a.items() if k != "rows"})
    if args.compare:
        from stylelens.eval.compare_eval import eval_compare

        c = await eval_compare(versions)
        report["compare"] = c
        print_table("Comparison", {k: v for k, v in c.items() if k not in ("rows", "unmatched_findings")})

    out_dir = Path(".data/eval")
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"report-{time.strftime('%Y%m%d-%H%M%S')}.json"
    path.write_text(json.dumps(report, indent=1, default=str))
    print(f"\nFull report: {path}")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
