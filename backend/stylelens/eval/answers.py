"""Answer-level evaluation: runs the real chat pipeline on the golden questions."""

import json

from stylelens.chat.service import NOT_COVERED_PREFIX, ChatRequest, run_chat
from stylelens.llm.client import llm_available, model_spec


async def _ask(guide_id: str, question: str) -> dict:
    out = {"answer": "", "citations": [], "invalid": [], "mode": None, "claims": []}
    async for ev in run_chat(ChatRequest(guide_id=guide_id, message=question)):
        data = json.loads(ev["data"])
        if ev["event"] == "token":
            out["answer"] += data["text"]
        elif ev["event"] == "citations":
            out.update(citations=data["citations"], invalid=data["invalid"], claims=data["claims"], answer=data["answer"])
        elif ev["event"] == "done":
            out["mode"] = data["mode"]
            out["cached"] = data["cached"]
    return out


async def eval_answers(versions: dict[str, tuple[str, str]], qa: list[dict]) -> dict:
    if not llm_available("generation"):
        print("  (no LLM configured — evaluating the extractive fallback)")
    rows = []
    for item in qa:
        guide_id = versions[item["guide"]][0]
        a = await _ask(guide_id, item["question"])
        b = await _ask(guide_id, item["question"])  # consistency: same question again
        answer = a["answer"]
        abstained = answer.strip().startswith(NOT_COVERED_PREFIX)
        kw = item["answer_keywords"]
        rows.append({
            "id": item["id"], "covered": item["covered"], "mode": a["mode"],
            "keyword_hit": (not kw) or any(k.lower() in answer.lower() for k in kw),
            "abstained": abstained,
            "n_citations": len(a["citations"]), "invalid_citations": len(a["invalid"]),
            "supported_claims": sum(1 for c in a["claims"] if c["supported"]), "claims": len(a["claims"]),
            "consistent": a["answer"] == b["answer"] and
                          [c["chunk_id"] for c in a["citations"]] == [c["chunk_id"] for c in b["citations"]],
            "answer": answer[:400],
        })
    cov = [r for r in rows if r["covered"]]
    unc = [r for r in rows if not r["covered"]]
    claims = sum(r["claims"] for r in rows)
    return {
        "model": model_spec("generation") if llm_available("generation") else "extractive (no LLM)",
        "answer_keyword_accuracy": round(sum(r["keyword_hit"] for r in cov) / max(len(cov), 1), 3),
        "answers_with_citations": round(sum(r["n_citations"] > 0 for r in cov) / max(len(cov), 1), 3),
        "citation_support_rate": round(sum(r["supported_claims"] for r in rows) / max(claims, 1), 3),
        "invalid_citations": sum(r["invalid_citations"] for r in rows),
        "false_refusals": sum(r["abstained"] for r in cov),
        "correct_refusals": f"{sum(r['abstained'] for r in unc)}/{len(unc)}",
        "consistency": round(sum(r["consistent"] for r in rows) / max(len(rows), 1), 3),
        "rows": rows,
    }
