import re

import pytest

from stylelens import jobs
from stylelens.config import get_settings
from stylelens.eval import samples
from stylelens.llm import fake_provider
from stylelens.visual import box_to_bbox, crop

TAGLINE = "Centre the tagline under the logo lockup at 2/3 of the logo width."
ROTATE = "Do not rotate the logo at an angle."
CLEAR = "Keep clear space around the logo equal to the height of the N in the wordmark on all sides."


def test_box_to_bbox_maps_gemini_boxes_into_page_points():
    # [ymin, xmin, ymax, xmax] over a 600x800 page
    assert box_to_bbox([100, 250, 500, 750], [0, 0, 600, 800]) == [150.0, 80.0, 450.0, 400.0]
    # inside an element frame
    assert box_to_bbox([0, 0, 1000, 1000], [10, 20, 110, 70]) == [10.0, 20.0, 110.0, 70.0]
    assert box_to_bbox([500, 500, 400, 600], [0, 0, 1, 1]) is None


def test_crop_keeps_context_and_upscales():
    from io import BytesIO

    from PIL import Image

    buf = BytesIO()
    Image.new("RGB", (1000, 1000), "white").save(buf, "PNG")
    out = Image.open(BytesIO(crop(buf.getvalue(), [0, 0, 1000, 1000], [400, 400, 450, 450], mark=True)))
    assert max(out.size) >= 768  # small regions are enlarged for the model


def _labels(rules_text: str) -> dict[str, str]:
    return {m.group(1): m.group(2) for m in re.finditer(r"^(R\d+) \[[^\]]*\] (.+?)(?: \||$)", rules_text, re.M)}


@pytest.fixture
def fake_vision(monkeypatch):
    monkeypatch.setattr(get_settings(), "llm_vision_model", "fake:fake")
    calls = {"verify": []}

    @fake_provider.register("extract_visual_rules")
    def _extract(meta, messages):
        text = meta.variables["page_text"]
        if "Clear Space" not in text:
            return {"rules": []}
        eid = re.search(r"\[(\w+)\] Clear Space", text).group(1)
        rule = lambda s, pol, box: {  # noqa: E731
            "statement": s, "category": "logo_rules", "polarity": pol, "normative_level": "must",
            "value": None, "check": "Locate the logo and compare.", "evidence": "Dimension marks in the figure.",
            "box_2d": box, "element_ids": [eid]}
        return {"rules": [rule(TAGLINE, "do", [100, 100, 300, 600]), rule(ROTATE, "dont", [300, 100, 500, 600]),
                          rule(CLEAR, "do", [100, 100, 300, 600])]}

    @fake_provider.register("detect_visual_subjects")
    def _detect(meta, messages):
        return {"subjects": [{"kind": "logo", "label": "Northwind logo", "box_2d": [100, 100, 300, 500]},
                             {"kind": "layout", "label": "page", "box_2d": [0, 0, 1000, 1000]}]}

    @fake_provider.register("visual_check")
    def _check(meta, messages):
        verdicts = []
        for label, stmt in _labels(meta.variables["rules"]).items():
            base = {"rule": label, "applicable": True, "measurement": None, "severity": "major",
                    "box_2d": [100, 100, 300, 500], "confidence": 0.85}
            if stmt == TAGLINE:
                verdicts.append(base | {"status": "deviation", "observation": "Tagline spans the full logo width.",
                                        "measurement": "tagline ≈ 1.0 × logo width (required 2/3)",
                                        "reasoning": "The guide sets the tagline at 2/3 of the logo width.",
                                        "summary": "Shrink the tagline to 2/3 of the logo width."})
            elif stmt == ROTATE:
                verdicts.append(base | {"status": "deviation", "observation": "Logo looks tilted.",
                                        "reasoning": "Rotation is forbidden.", "summary": "Logo is rotated."})
            elif stmt.startswith("Keep clear space"):
                verdicts.append(base | {"status": "compliant", "observation": "Ample space around the logo.",
                                        "reasoning": "Clear space exceeds the N height.", "summary": "Clear space respected."})
            else:
                verdicts.append(base | {"applicable": False, "status": "uncertain", "observation": "",
                                        "reasoning": "", "summary": ""})
        return {"verdicts": verdicts}

    @fake_provider.register("verify_visual")
    def _verify(meta, messages):
        calls["verify"].append(meta.variables["statement"])
        if meta.variables["statement"] == ROTATE:  # the second look disagrees: must be dropped
            return {"status": "compliant", "measurement": None, "reasoning": "The logo is upright.", "confidence": 0.8}
        return {"status": "deviation", "measurement": "tagline ≈ 0.95 × logo width",
                "reasoning": "The tagline is as wide as the logo.", "confidence": 0.9}

    yield calls
    for name in ("extract_visual_rules", "detect_visual_subjects", "visual_check", "verify_visual"):
        fake_provider.HANDLERS.pop(name, None)


async def _upload(client, name, data, role, filename):
    r = await client.post("/guides", files={"file": (filename, data, "application/octet-stream")},
                          data={"role": role, "name": name})
    assert r.status_code == 201, r.text
    return r.json()["id"]


async def test_visual_rules_extracted_and_checked(client, fake_vision):
    ref = await _upload(client, "Northwind", samples.northwind_guide(), "reference", "nw.pdf")
    flyer = await _upload(client, "Flyer", samples.northwind_flyer(), "candidate", "flyer.pdf")
    await jobs.drain_inline()

    profile = (await client.get(f"/guides/{ref}/profile")).json()
    logo = profile["logo_rules"]
    tag = next(r for r in logo if r["statement"] == TAGLINE)
    assert tag["visual"] and tag["figure"]["bbox"] and tag["check"]
    assert tag["source_refs"][0]["bbox"] == tag["figure"]["bbox"]
    # the diagram restating a text rule enriches that rule instead of duplicating it
    clear = [r for r in logo if "clear space" in r["statement"].lower()]
    assert len(clear) == 1 and clear[0]["visual"] and clear[0]["figure"]
    assert profile["stats"]["visual_rules"] >= 3
    flyer_profile = (await client.get(f"/guides/{flyer}/profile")).json()
    assert flyer_profile["stats"]["visual_rules"] == 0  # candidates are not mined for rules

    r = await client.post("/comparisons", json={"reference_id": ref, "candidate_id": flyer})
    cid = r.json()["id"]
    await jobs.drain_inline()
    comp = (await client.get(f"/comparisons/{cid}")).json()
    assert comp["status"] == "ready", comp["error"]
    assert comp["stages"]["visual_checks"]["status"] == "done"
    vis = [f for f in comp["findings"] if f["data"].get("engine") == "vision"]

    dev = [f for f in vis if f["status"] == "deviation"]
    assert [f["data"]["rule"]["statement"] for f in dev] == [TAGLINE] * len(dev) and dev
    f = dev[0]
    assert f["severity"] in ("major", "critical")  # "must" rules never drop below major
    assert f["data"]["verification"]["status"] == "deviation"
    assert "2/3" in f["data"]["measurement"]
    assert f["candidate_citations"][0]["bbox"] and f["reference_citations"][0]["bbox"] == tag["figure"]["bbox"]
    for url in (f["data"]["candidate_region"]["image_url"], f["data"]["reference_figure"]["image_url"]):
        assert (await client.get(url)).status_code == 200
    for c in f["reference_citations"] + f["candidate_citations"]:
        assert (await client.get(f"/chunks/{c['chunk_id']}")).status_code == 200

    assert not any(x["data"]["rule"]["statement"] == ROTATE for x in vis)  # rejected on second look
    assert ROTATE in fake_vision["verify"]
    assert any(x["status"] == "compliant" and "clear space" in x["data"]["rule"]["statement"].lower() for x in vis)
    stats = comp["summary"]["visual"]
    assert stats["confirmed"] >= 1 and stats["rejected_on_second_look"] >= 1

    pdf = (await client.get(f"/comparisons/{cid}/export?format=pdf")).content
    assert pdf.startswith(b"%PDF")
