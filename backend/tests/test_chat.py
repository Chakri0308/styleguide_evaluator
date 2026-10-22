import json

import pytest

from stylelens import jobs
from stylelens.chat.citations import cited_numbers, lexical_support, strip_invalid
from stylelens.chat.text import split_sentences
from stylelens.config import get_settings
from stylelens.eval import samples
from stylelens.llm import fake_provider


def parse_sse(raw: str) -> list[tuple[str, dict]]:
    events, name, data = [], None, []
    for line in raw.splitlines():
        if line.startswith("event:"):
            name = line[6:].strip()
        elif line.startswith("data:"):
            data.append(line[5:].strip())
        elif not line.strip() and name:
            events.append((name, json.loads("\n".join(data))))
            name, data = None, []
    if name:
        events.append((name, json.loads("\n".join(data))))
    return events


async def ask(client, guide_id, message, conversation_id=None):
    r = await client.post("/chat", json={"guide_id": guide_id, "message": message, "conversation_id": conversation_id})
    assert r.status_code == 200
    events = parse_sse(r.text)
    names = [n for n, _ in events]
    assert names[-1] == "done", names
    get = lambda n: next(d for k, d in events if k == n)  # noqa: E731
    answer = "".join(d["text"] for k, d in events if k == "token")
    return answer, get("citations"), get("followups"), get("done"), get("sources")


@pytest.fixture
async def guide(client):
    r = await client.post("/guides", files={"file": ("nw.pdf", samples.northwind_guide(), "application/pdf")},
                          data={"name": "Northwind"})
    await jobs.drain_inline()
    return r.json()["id"]


def test_sentence_split_keeps_citations():
    text = "Use Harbor Blue for buttons [2]. Never use pure black [3][4].\n- Body text is 16px [1]."
    assert split_sentences(text) == ["Use Harbor Blue for buttons [2].", "Never use pure black [3][4].",
                                     "Body text is 16px [1]."]
    assert cited_numbers("a [2] b [3, 4] c [2]") == [2, 3, 4]
    assert strip_invalid("x [1][9] y [1, 9]", {1}) == "x [1] y [1]"


def test_lexical_support_checks_values():
    src = "The full logo must never be reproduced smaller than 24px tall on screen."
    assert lexical_support("The logo must be at least 24px tall [1].", src)[0]
    ok, why = lexical_support("The logo must be at least 32px tall [1].", src)
    assert not ok and "32px" in why


async def test_grounded_answer_with_verified_citations(client, guide):
    answer, cites, follow, done, sources = await ask(client, guide, "How small can the logo be?")
    assert done["mode"] == "llm"
    assert "[" in answer and cites["citations"]
    c = cites["citations"][0]
    assert c["chunk_id"] and c["page"] >= 1 and c["supported"] is True
    assert c["regions"] and c["heading_path"]
    assert len(follow["questions"]) >= 1
    # the cited chunk resolves via the citation-preview endpoint
    chunk = (await client.get(f"/chunks/{c['chunk_id']}")).json()
    assert chunk["guide_id"] == guide


async def test_same_question_same_answer(client, guide):
    first = await ask(client, guide, "What is the primary brand color?")
    second = await ask(client, guide, "What is the primary brand color?")  # new conversation
    assert first[0] == second[0]
    assert [c["chunk_id"] for c in first[1]["citations"]] == [c["chunk_id"] for c in second[1]["citations"]]
    assert second[3]["cached"] is True


async def test_not_covered(client, guide):
    answer, cites, follow, done, _ = await ask(client, guide, "quarterly revenue forecast spreadsheet macros")
    assert done["mode"] == "not_covered"
    assert answer.startswith("The guide doesn't cover")
    assert cites["citations"] == [] and follow["questions"] == []


async def test_extractive_mode_without_llm(client, guide, monkeypatch):
    monkeypatch.setattr(get_settings(), "llm_generation_model", "anthropic:claude-opus-5-5")
    monkeypatch.setattr(get_settings(), "anthropic_api_key", None)
    answer, cites, *_ , done, _ = await ask(client, guide, "How should dates be written?")
    assert done["mode"] == "extractive"
    assert answer.startswith("Here's what the guide says:")
    assert cites["citations"] and all(c["supported"] for c in cites["citations"])


async def test_invalid_citations_are_dropped(client, guide):
    fake_provider.HANDLERS["answer"] = lambda meta, messages: "The logo minimum is 24px tall [1][42]."
    try:
        answer, cites, *_ = await ask(client, guide, "logo minimum size in pixels on screen?")
    finally:
        fake_provider.HANDLERS.pop("answer")
    assert 42 in cites["invalid"]
    assert "[42]" not in cites["answer"]


async def test_followup_uses_history_and_feedback(client, guide):
    _, _, _, done, _ = await ask(client, guide, "What typeface is used for headlines?")
    conv = done["conversation_id"]
    _, _, _, done2, _ = await ask(client, guide, "And for body copy?", conversation_id=conv)
    assert done2["conversation_id"] == conv
    msgs = (await client.get(f"/conversations/{conv}/messages")).json()
    assert [m["role"] for m in msgs] == ["user", "assistant", "user", "assistant"]
    r = await client.post(f"/messages/{done2['message_id']}/feedback", json={"rating": 1})
    assert r.status_code == 204
