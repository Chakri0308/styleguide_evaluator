import pytest

from stylelens.colors import (
    ciede2000,
    cmyk_to_rgb,
    color_name_hint,
    contrast_ratio,
    delta_e,
    find_colors,
    hex_to_lab,
    lab_to_hex,
    norm_hex,
    wcag_level,
)

# Reference pairs from Sharma, Wu & Dalal (2005), "The CIEDE2000 Color-Difference Formula"
SHARMA = [
    ((50.0000, 2.6772, -79.7751), (50.0000, 0.0000, -82.7485), 2.0425),
    ((50.0000, 3.1571, -77.2803), (50.0000, 0.0000, -82.7485), 2.8615),
    ((50.0000, -1.3802, -84.2814), (50.0000, 0.0000, -82.7485), 1.0000),
    ((50.0000, 0.0000, 0.0000), (50.0000, -1.0000, 2.0000), 2.3669),
    ((50.0000, 2.4900, -0.0010), (50.0000, -2.4900, 0.0009), 7.1792),
    ((50.0000, 2.5000, 0.0000), (73.0000, 25.0000, -18.0000), 27.1492),
    ((60.2574, -34.0099, 36.2677), (60.4626, -34.1751, 39.4387), 1.2644),
    ((22.7233, 20.0904, -46.6940), (23.0331, 14.9730, -42.5619), 2.0373),
    ((90.8027, -2.0831, 1.4410), (91.1528, -1.6435, 0.0447), 1.4441),
    ((2.0776, 0.0795, -1.1350), (0.9033, -0.0636, -0.5514), 0.9082),
]


@pytest.mark.parametrize("lab1,lab2,expected", SHARMA)
def test_ciede2000_reference(lab1, lab2, expected):
    assert ciede2000(lab1, lab2) == pytest.approx(expected, abs=1e-4)
    assert ciede2000(lab2, lab1) == pytest.approx(expected, abs=1e-4)


def test_lab_roundtrip_and_known_values():
    L, a, b = hex_to_lab("#FFFFFF")
    assert L == pytest.approx(100, abs=0.01) and abs(a) < 0.01 and abs(b) < 0.01
    assert hex_to_lab("#FF0000") == pytest.approx((53.24, 80.09, 67.20), abs=0.05)
    for h in ("#1B4F9C", "#F2E3C6", "#3B2A20", "#00FF7F"):
        assert lab_to_hex(hex_to_lab(h)) == h


def test_delta_e_identity_and_near():
    assert delta_e("#1B4F9C", "#1b4f9c") == 0
    assert delta_e("#1B4F9C", "#1D51A0") < 3       # near match
    assert delta_e("#F2E3C6", "#E8C9A0") > 5       # clear deviation


def test_contrast_ratio():
    assert contrast_ratio("#000000", "#FFFFFF") == pytest.approx(21.0)
    assert contrast_ratio("#FFFFFF", "#FFFFFF") == pytest.approx(1.0)
    assert contrast_ratio("#767676", "#FFFFFF") == pytest.approx(4.54, abs=0.01)
    assert wcag_level(contrast_ratio("#A0A0A0", "#FFFFFF")) == "fail"
    assert wcag_level(4.6) == "AA" and wcag_level(7.2) == "AAA" and wcag_level(3.2, large_text=True) == "AA"


def test_find_colors_merges_specs():
    text = "HEX #1B4F9C RGB 27, 79, 156 CMYK 100, 70, 0, 10 Pantone 2945 C"
    found = find_colors(text)
    assert len(found) == 1
    assert found[0].hex == "#1B4F9C"
    assert found[0].specs == {"hex": "#1B4F9C", "rgb": "27, 79, 156", "cmyk": "100, 70, 0, 10", "pantone": "2945 C"}


def test_find_colors_variants():
    text = "Use #fff on rgb(0, 85, 255); avoid hsl(120, 100%, 50%). Accent is C0 M70 Y90 K5. Not #12345 or &#1234;"
    hexes = [c.hex for c in find_colors(text)]
    assert hexes[0] == "#FFFFFF"
    assert "#0055FF" in hexes and "#00FF00" in hexes
    assert norm_hex("abc") == "#AABBCC"
    assert cmyk_to_rgb(0, 70, 90, 5) == (242, 73, 24)
    assert len(hexes) == 4


def test_color_name_hint():
    assert color_name_hint("#1B4F9C") == "dark blue"
    assert color_name_hint("#4A90E2") == "blue"
    assert color_name_hint("#FFFFFF") == "white"
