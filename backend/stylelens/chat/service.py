"""Grounded chat: retrieve → (not covered | extractive | LLM stream) → verify citations → follow-ups.

Answers are a pure function of (standalone question, retrieved sources, model, prompt version,
comparison state), which is what makes them cacheable and consistent across conversations; chat
history is used only to rewrite follow-up questions into standalone ones.
"""

import json
import logging
import re
from collections.abc import AsyncIterator
from dataclasses import dataclass

from pydantic import BaseModel
from sqlalchemy import select

from stylelens.chat.citations import CITE_RE, strip_invalid, verify
from stylelens.chat.text import split_sentences
from stylelens.db.models import Comparison, Conversation, Finding, Guide, Message
from stylelens.db.session import SessionLocal
from stylelens.llm import prompts
from stylelens.llm.base import LLMRefusal, LLMUnavailable
from stylelens.llm.client import cache_get, cache_key, cache_put, generate_json, llm_available, model_spec, stream_text
from stylelens.retrieval.context import Context, assemble
from stylelens.retrieval.models import get_embedder, get_reranker
from stylelens.retrieval.search import RETRIEVAL_VERSION, retrieve

log = logging.getLogger(__name__)
HISTORY_TURNS = 6
NOT_COVERED_PREFIX = "The guide doesn't cover"


class FollowUps(BaseModel):
    questions: list[str]


@dataclass
class ChatRequest:
    guide_id: str
    message: str
    conversation_id: str | None = None
    comparison_id: str | None = None


def event(name: str, data) -> dict:
    return {"event": name, "data": json.dumps(data, default=str)}


async def _comparison_context(comparison_id: str | None) -> tuple[str | None, str | None, str]:
    """Returns (candidate version id, findings summary text, digest for cache keys)."""
    if not comparison_id:
        return None, None, ""
    async with SessionLocal() as session:
        comp = await session.get(Comparison, comparison_id)
        if comp is None:
            return None, None, ""
        findings = list(await session.scalars(
            select(Finding).where(Finding.comparison_id == comparison_id).order_by(Finding.seq)))
    lines = [f"Overall compliance score: {comp.score:.0f}/100" if comp.score is not None else "Comparison in progress"]
    for f in findings[:60]:
        lines.append(f"- [{f.finding_id}] {f.status.upper()} ({f.severity}, {f.category}): {f.summary}"
                     + (f" — {f.reasoning[:240]}" if f.reasoning else ""))
    text = "\n".join(lines)
    return comp.candidate_version_id, text, f"{comparison_id}:{comp.status}:{len(findings)}"


async def _history(conversation_id: str) -> list[dict]:
    async with SessionLocal() as session:
        rows = list(await session.scalars(
            select(Message).where(Message.conversation_id == conversation_id)
            .order_by(Message.created_at.desc()).limit(HISTORY_TURNS * 2)))
    return [{"role": m.role, "content": m.content} for m in reversed(rows)]


def extractive_answer(ctx: Context) -> str:
    """Offline fallback (no LLM): quote the most relevant passages with citations."""
    best = sorted(ctx.sources, key=lambda s: -s.score)[:3]
    lines = ["Here's what the guide says:"]
    for s in sorted(best, key=lambda s: s.n):
        leaf = s.heading_path[-1] if s.heading_path else None
        if s.kind == "image":
            parts = [ln.split(":", 1)[1].strip() for ln in s.text.splitlines()
                     if ln.startswith(("Caption:", "Description:"))][:1]
            body = " ".join(parts)
        else:
            parts = [ln.lstrip("- ").strip() for ln in s.text.splitlines() if ln.strip() and ln.strip() != leaf]
            body = " ".join(split_sentences(" ".join(parts))[:2])
        body = re.sub(r"\s+", " ", body).strip()
        if body:
            lines.append(f"- {body[:320]} [{s.n}]")
    return "\n".join(lines)


async def followups(question: str, answer: str, ctx: Context) -> list[str]:
    sections = list(dict.fromkeys(" > ".join(s.heading_path[-2:]) for s in ctx.sources if s.heading_path))
    if llm_available("fast") and ctx.sources:
        try:
            out = await generate_json("fast", "suggest_followups", FollowUps, max_tokens=600, question=question,
                                      answer=answer[:1500], sections="\n".join(f"- {s}" for s in sections[:10]))
            qs = [q.strip() for q in out.questions if q.strip()][:3]
            if qs:
                return qs
        except (LLMUnavailable, LLMRefusal, ValueError):
            pass
    leaves = list(dict.fromkeys(s.heading_path[-1] for s in ctx.sources if s.heading_path))
    return [f"What does the guide say about {leaf.lower().lstrip('0123456789. ')}?" for leaf in leaves[:3]]


async def run_chat(req: ChatRequest) -> AsyncIterator[dict]:
    async with SessionLocal() as session:
        guide = await session.get(Guide, req.guide_id)
        if guide is None or guide.status != "ready" or not guide.current_version_id:
            yield event("error", {"message": "This guide isn't ready yet."})
            return
        conv = await session.get(Conversation, req.conversation_id) if req.conversation_id else None
        if conv is None:
            conv = Conversation(guide_id=guide.id, comparison_id=req.comparison_id, title=req.message[:120])
            session.add(conv)
            await session.flush()
        user_msg = Message(conversation_id=conv.id, role="user", content=req.message)
        session.add(user_msg)
        await session.commit()
        conv_id, guide_name, ref_version = conv.id, guide.name, guide.current_version_id

    history = await _history(conv_id)
    history = history[:-1]  # exclude the message just stored
    cand_version, comparison_text, comparison_digest = await _comparison_context(req.comparison_id)
    versions = [ref_version] + ([cand_version] if cand_version else [])
    yield event("status", {"stage": "retrieving", "conversation_id": conv_id})

    result = await retrieve(req.message, versions, history=history)
    labels = {ref_version: f"{guide_name} (reference)"}
    if cand_version:
        labels[cand_version] = "Candidate document"
    ctx = await assemble(result.hits, labels)
    sources = ctx.by_number()
    yield event("sources", {"standalone_query": result.standalone_query,
                            "sources": [s.citation() for s in ctx.sources]})

    mode = "llm"
    prompt_id = prompts.load("answer").id
    gen_model = model_spec("generation")
    key = cache_key("answer", prompt_id, gen_model, result.standalone_query, sorted(versions),
                    [s.chunk_id for s in ctx.sources], comparison_digest, RETRIEVAL_VERSION,
                    get_embedder().name, get_reranker().name)
    cached = await cache_get(key)
    answer = ""
    if cached is not None:
        mode = cached["mode"]
        answer = cached["answer"]
        for piece in re.findall(r"\S+\s*", answer):
            yield event("token", {"text": piece})
    elif not result.covered and not comparison_text:
        mode = "not_covered"
        answer = f"{NOT_COVERED_PREFIX} this — I couldn't find anything relevant in “{guide_name}”."
        yield event("token", {"text": answer})
    elif not llm_available("generation"):
        mode = "extractive"
        answer = extractive_answer(ctx)
        for piece in re.findall(r"\S+\s*", answer):
            yield event("token", {"text": piece})
    else:
        yield event("status", {"stage": "generating"})
        try:
            model_id, tokens, prompt_id = await stream_text(
                "generation", "answer", question=result.standalone_query, context=ctx.rendered,
                comparison=comparison_text)
            async for t in tokens:
                answer += t
                yield event("token", {"text": t})
        except (LLMUnavailable, LLMRefusal) as exc:
            mode = "error"
            msg = f"\n\n_The model couldn't answer this ({exc})._"
            answer += msg
            yield event("token", {"text": msg})

    if cached is not None and "citations" in cached:
        clean, citations, claims, invalid = cached["clean"], cached["citations"], cached["claims"], cached["invalid"]
        unsupported = {c["n"] for c in citations if not c["supported"]}
    else:
        # Verify citations; drop references to sources that don't exist
        verification = await verify(answer, sources, use_llm=mode == "llm")
        clean = strip_invalid(answer, set(sources))
        unsupported = verification.unsupported_numbers()
        citations = []
        for n in sorted(set(verification.used)):
            c = sources[n].citation()
            c["supported"] = n not in unsupported
            citations.append(c)
        claims = [{"sentence": c.sentence, "numbers": c.numbers, "supported": c.supported, "reason": c.reason}
                  for c in verification.claims]
        invalid = verification.invalid
    yield event("citations", {"citations": citations, "invalid": invalid, "answer": clean, "claims": claims})

    if cached is None and mode in ("llm", "extractive", "not_covered") and answer:
        await cache_put(key, "answer", {"mode": mode, "answer": answer, "clean": clean, "citations": citations,
                                        "claims": claims, "invalid": invalid})

    fkey = cache_key("followups", key)
    fcached = await cache_get(fkey)
    if fcached is not None:
        suggestions = fcached["followups"]
    else:
        suggestions = await followups(result.standalone_query, clean, ctx) if mode != "not_covered" else []
        if mode != "error":
            await cache_put(fkey, "followups", {"followups": suggestions})
    yield event("followups", {"questions": suggestions})

    async with SessionLocal() as session:
        msg = Message(conversation_id=conv_id, role="assistant", content=clean, citations=citations, meta={
            "mode": mode, "cached": cached is not None, "standalone_query": result.standalone_query,
            "model": gen_model if mode == "llm" else None, "prompt": prompt_id, "covered": result.covered,
            "followups": suggestions, "invalid_citations": invalid,
            "unsupported": sorted(unsupported), "retrieval": [{"chunk_id": h.chunk_id, "score": h.score}
                                                             for h in result.hits]})
        session.add(msg)
        await session.commit()
        yield event("done", {"message_id": msg.id, "conversation_id": conv_id, "mode": mode,
                             "cached": cached is not None})


def is_not_covered(text: str) -> bool:
    return text.strip().startswith(NOT_COVERED_PREFIX) or not CITE_RE.search(text)
