import re

import pytest

from stylelens import jobs
from stylelens.eval import samples
from stylelens.extraction.colors import extract_colors
from stylelens.extraction.common import El
from stylelens.extraction.rules import heuristic_rules
from stylelens.extraction.typography import extract_typography
from stylelens.ingestion.parsers import get_parser
from stylelens.ingestion.parsers.base import assign_heading_paths, noop_progress
from stylelens.llm import fake_provider


def _elements(pdf: bytes):
    doc = get_parser("pdf").parse(pdf, "x.pdf", noop_progress)
    paths = assign_heading_paths(doc.elements)
    els = [El(id=f"e{i}", seq=i, page=e.page, type=e.type, text=e.text, heading_path=p,
              bbox=list(e.bbox) if e.bbox else None, level=e.level, meta=e.meta,
              image_key=f"img{i}" if e.image else None)
           for i, (e, p) in enumerate(zip(doc.elements, paths))]
    images = {f"img{i}": e.image for i, e in enumerate(doc.elements) if e.image}
    return els, images, doc.meta


@pytest.fixture(scope="module")
def northwind():
    return _elements(samples.northwind_guide())


def test_palette(northwind):
    els, images, _ = northwind
    colors, palettes = extract_colors(els, images)
    by_hex = {c.hex: c for c in colors}
    expected = {"#1B4F9C": ("Harbor Blue", "primary"), "#3B2A20": ("Roast", "text"),
                "#F2E3C6": ("Crema", "background"), "#D9622B": ("Ember", "accent")}
    for hex_, (name, role) in expected.items():
        assert by_hex[hex_].name == name
        assert by_hex[hex_].role == role
        assert "swatch" in by_hex[hex_].origin
    assert by_hex["#1B4F9C"].pantone == "2945 C" and by_hex["#1B4F9C"].cmyk == "100, 70, 0, 10"
    assert by_hex["#000000"].status == "prohibited"
    assert by_hex["#D9622B"].status == "approved"  # usage restriction, not a ban
    assert all(c.source_refs for c in colors)
    assert any(len(p) >= 2 for p in palettes.values())


def test_typography(northwind):
    els, _, meta = northwind
    items, fonts = extract_typography(els, meta)
    by_role = {i.role: i for i in items}
    assert by_role["h1"].family == "Fraunces" and by_role["h1"].size == "48px" and by_role["h1"].line_height == "56px"
    assert by_role["body"].family == "Inter"
    assert by_role["h1"].fallbacks == ["Georgia"]
    assert by_role["caption"].letter_spacing == "+1%"
    assert fonts and fonts[0].family.startswith("Helvetica")


def test_heuristic_rules(northwind):
    els, _, _ = northwind
    rules = heuristic_rules(els)
    cats = {r.category for r in rules}
    assert {"voice_tone", "logo_rules", "writing_rules", "accessibility", "color_usage", "typography_usage"} <= cats
    oxford = next(r for r in rules if "Oxford" in r.statement)
    assert oxford.category == "writing_rules" and oxford.polarity == "do"
    size = next(r for r in rules if "smaller than 24px" in r.statement)
    assert size.category == "logo_rules" and size.normative_level == "must" and size.value == "24px"
    assert not any(r.statement.startswith(("This document", "Figure")) for r in rules)
    assert all(r.source_refs and r.source_refs[0].page >= 1 for r in rules)


async def test_profile_via_llm_path_drops_uncited_rules(client, monkeypatch):
    from stylelens.config import get_settings

    monkeypatch.setattr(get_settings(), "llm_extraction_model", "fake:fake")

    @fake_provider.register("extract_rules")
    def _(meta, messages):
        text = messages[0]["content"][-1]["text"]
        ids = re.findall(r"\[([0-9a-f]{24}e\d{5})\]", text)
        rules = []
        for eid in ids:
            line = next(ln for ln in text.splitlines() if ln.startswith(f"[{eid}]"))
            if "Oxford" in line:
                rules.append({"statement": "Use the serial (Oxford) comma.", "category": "writing_rules",
                              "normative_level": "should", "polarity": "do", "value": None, "subject": "lists",
                              "element_ids": [eid], "quote": "serial (Oxford) comma"})
        if ids:
            rules.append({"statement": "Invented rule", "category": "misc_rules", "normative_level": "must",
                          "polarity": "do", "value": None, "subject": None, "element_ids": ["bogus"], "quote": ""})
        return {"rules": rules}

    try:
        r = await client.post("/guides", files={"file": ("nw.pdf", samples.northwind_guide(), "application/pdf")})
        gid = r.json()["id"]
        await jobs.drain_inline()
        profile = (await client.get(f"/guides/{gid}/profile")).json()
    finally:
        fake_provider.HANDLERS.pop("extract_rules")

    assert profile["stats"]["llm_used"] is True
    statements = [r["statement"] for r in profile["writing_rules"]]
    assert statements == ["Use the serial (Oxford) comma."]
    assert not profile["misc_rules"]
    ref = profile["writing_rules"][0]["source_refs"][0]
    assert ref["page"] >= 5 and ref["bbox"]
    assert {c["hex"] for c in profile["colors"]} >= {"#1B4F9C", "#F2E3C6"}
    assert profile["typography"] and profile["images"]
    logo = next(i for i in profile["images"] if i["kind"] == "logo" and i["example"] == "dont")
    assert logo["image_url"].startswith("/assets/")
