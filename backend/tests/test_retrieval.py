import pytest

from stylelens import jobs
from stylelens.eval import samples
from stylelens.extraction.common import El
from stylelens.retrieval.chunking import CHILD_MAX_TOKENS, build_chunks, estimate_tokens
from stylelens.retrieval.search import rrf, tsquery_string


@pytest.fixture
async def northwind(client):
    r = await client.post("/guides", files={"file": ("nw.pdf", samples.northwind_guide(), "application/pdf")},
                          data={"name": "Northwind"})
    await jobs.drain_inline()
    return r.json()["id"]


def _el(i, typ, text, path, page=1):
    return El(id=f"e{i}", seq=i, page=page, type=typ, text=text, heading_path=path, bbox=[0, i * 10, 100, i * 10 + 8])


def test_chunking_structure():
    big_table = "| a | b |\n" + "\n".join(f"| row {i} | value {i} with several words |" for i in range(80))
    els = [
        _el(0, "heading", "Color", ["Color"]),
        _el(1, "paragraph", "Intro " * 50, ["Color"]),
        _el(2, "table", big_table, ["Color"]),
        *[_el(3 + i, "list_item", f"Rule number {i} about colour usage and contrast. " * 3, ["Color"]) for i in range(30)],
        _el(40, "heading", "Logo", ["Logo"]),
        _el(41, "paragraph", "Keep clear space.", ["Logo"]),
        _el(42, "image", "", ["Logo"]),
    ]
    els[-1].image_key = "k"
    chunks = build_chunks("v1", "Guide", els, {"e42": {"caption": "Logo on white", "kind": "logo", "example": "do"}})
    parents = [c for c in chunks if c.kind == "parent"]
    children = [c for c in chunks if c.kind == "child"]
    images = [c for c in chunks if c.kind == "image"]
    assert [p.heading_path for p in parents] == [["Color"], ["Logo"]]
    # the oversized table stays whole in exactly one child
    assert sum("row 79" in c.text for c in children) == 1
    assert all(c.parent_id for c in children)
    # children respect the size budget unless a single element is larger
    for c in children:
        assert c.token_count <= CHILD_MAX_TOKENS or len(c.element_ids) == 1 or "| a | b |" in c.text
    # every element appears in exactly one child (no splitting / duplication)
    covered = [eid for c in children for eid in c.element_ids]
    assert len(covered) == len(set(covered))
    assert images[0].text.startswith("[Image - logo (do example)]") and "Caption: Logo on white" in images[0].text
    assert "Section: Logo" in images[0].context_header
    # deterministic ids
    again = build_chunks("v1", "Guide", els, {"e42": {"caption": "Logo on white"}})
    assert [c.id for c in again] == [c.id for c in chunks]
    assert estimate_tokens("one two three") == 2


def test_rrf_tie_break_is_stable():
    fused = rrf([["b", "a"], ["a", "b"]], k=60)
    assert [cid for cid, _ in fused] == ["a", "b"]  # equal scores -> id order
    assert tsquery_string("What's the #1B4F9C logo's min size?") == "1b4f9c | logo | min | size"


async def test_retrieval_end_to_end(client, northwind):
    r = await client.post("/search", json={"query": "How small can the logo be?"})
    body = r.json()
    assert body["covered"] is True
    top = body["hits"][0]
    assert "Minimum Size" in top["heading_path"] or "24px" in top["snippet"]
    assert top["guide_id"] == northwind and top["regions"]

    chunk = (await client.get(f"/chunks/{top['chunk_id']}")).json()
    assert chunk["guide_id"] == northwind and chunk["page_start"] >= 1

    # same question -> identical results (cache + deterministic ordering)
    again = (await client.post("/search", json={"query": "How small can the logo be?"})).json()
    assert [h["chunk_id"] for h in again["hits"]] == [h["chunk_id"] for h in body["hits"]]

    colors = (await client.post("/search", json={"query": "Which colour is used for calls to action?"})).json()
    assert colors["intent"] == "color_usage"
    assert any("Ember" in h["snippet"] for h in colors["hits"][:3])


async def test_uncovered_question(client, northwind):
    r = await client.post("/search", json={"query": "quarterly revenue forecast spreadsheet macros"})
    assert r.json()["covered"] is False


async def test_reingest_creates_new_index_version(client, northwind):
    v1 = (await client.get(f"/guides/{northwind}")).json()["current_version_id"]
    await client.post(f"/guides/{northwind}/reingest")
    await jobs.drain_inline()
    v2 = (await client.get(f"/guides/{northwind}")).json()["current_version_id"]
    assert v1 != v2
    hits = (await client.post("/search", json={"query": "logo clear space"})).json()["hits"]
    assert hits and all(h["chunk_id"] for h in hits)
