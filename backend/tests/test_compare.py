import pytest

from stylelens import jobs
from stylelens.compare.deterministic import banned_patterns
from stylelens.compare.engine import score
from stylelens.compare.schema import FindingModel
from stylelens.eval import samples
from stylelens.schema.profile import RuleItem, SourceRef, StyleProfile


async def upload(client, name, data, role, filename):
    r = await client.post("/guides", files={"file": (filename, data, "application/octet-stream")},
                          data={"role": role, "name": name})
    assert r.status_code == 201, r.text
    return r.json()["id"]


@pytest.fixture
async def pair(client):
    ref = await upload(client, "Northwind", samples.northwind_guide(), "reference", "nw.pdf")
    flyer = await upload(client, "Flyer", samples.northwind_flyer(), "candidate", "flyer.pdf")
    await jobs.drain_inline()
    return ref, flyer


def _rule(stmt, pol="dont", cat="writing_rules"):
    return RuleItem(id="r1", category=cat, statement=stmt, polarity=pol, normative_level="must",
                    source_refs=[SourceRef(element_id="e1", page=1)])


def test_banned_patterns_from_reference_rules():
    prof = StyleProfile(version_id="v", writing_rules=[
        _rule('Write dates as "March 4, 2025". Do not use ordinal suffixes like "4th".'),
        _rule('Prices: "$4.50", never "4.50 USD" in consumer copy.'),
        _rule('Use "small-batch" instead of "artisanal".', pol="do"),
    ])
    pats = {label: p for p, label, _ in banned_patterns(prof)}
    assert "ordinal date suffix" in pats and pats["ordinal date suffix"].search("December 1st")
    assert not pats["ordinal date suffix"].search("March 4, 2025")
    usd = next(p for label, p in pats.items() if "USD" in label)
    assert usd.search("for 12.99 USD")
    assert pats['"artisanal"'].search("Artisanal roasters")


def test_scoring():
    mk = lambda st, sev: FindingModel(finding_id="x", category="colors", status=st, severity=sev, summary="s")  # noqa: E731
    s = score([mk("compliant", "info"), mk("compliant", "info"), mk("deviation", "major")])
    assert s["categories"]["colors"]["score"] == pytest.approx(50.0)  # (2 + 1 prior) / (3 + 3)
    assert s["score"] == pytest.approx(50.0)
    assert score([])["score"] == 100.0


async def test_asset_comparison_end_to_end(client, pair):
    ref, flyer = pair
    r = await client.post("/comparisons", json={"reference_id": ref, "candidate_id": flyer})
    assert r.status_code == 201
    cid = r.json()["id"]
    await jobs.drain_inline()
    comp = (await client.get(f"/comparisons/{cid}")).json()
    assert comp["status"] == "ready", comp["error"]
    assert comp["summary"]["candidate_kind"] == "asset"
    f = comp["findings"]
    text = " ".join(x["summary"] for x in f).lower()
    # seeded flyer problems
    assert any(x["category"] == "colors" and "#ff5a1f" in x["summary"].lower() for x in f)       # off-palette orange
    assert any(x["category"] == "colors" and x["status"] == "compliant" for x in f)               # Harbor Blue exact
    assert "best" in text or "unbelievable" in text or "world-class" in text                      # hype words
    assert "ordinal" in text or "1st" in text                                                     # date format
    assert any(x["category"] == "logo_rules" for x in f)                                          # logo on busy bg
    visual = [x for x in f if x["method"] == "visual"]
    assert any("don't" in x["summary"] for x in visual)  # image embedding matches the don't example
    # every finding cites real chunks
    for x in f:
        cites = x["reference_citations"] + x["candidate_citations"]
        assert cites
        for c in cites:
            assert (await client.get(f"/chunks/{c['chunk_id']}")).status_code == 200
    assert 0 <= comp["score"] < 80

    lst = (await client.get("/comparisons")).json()
    assert lst[0]["id"] == cid and lst[0]["candidate_name"] == "Flyer"

    js = await client.get(f"/comparisons/{cid}/export", params={"format": "json"})
    assert js.status_code == 200 and js.json()["findings"]
    pdf = await client.get(f"/comparisons/{cid}/export", params={"format": "pdf"})
    assert pdf.status_code == 200 and pdf.content.startswith(b"%PDF")


async def test_comparison_validation(client, pair):
    ref, _ = pair
    assert (await client.post("/comparisons", json={"reference_id": ref, "candidate_id": ref})).status_code == 422
    assert (await client.post("/comparisons", json={"reference_id": ref, "candidate_id": "nope"})).status_code == 404
