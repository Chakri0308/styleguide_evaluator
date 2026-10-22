"""Colour parsing and maths: HEX/RGB/CMYK/HSL/Pantone parsing, sRGB → CIELAB (D65),
CIEDE2000 ΔE, and WCAG 2.x relative luminance / contrast ratio."""

import math
import re
from dataclasses import dataclass, field

# -- parsing --------------------------------------------------------------------------------------
HEX_RE = re.compile(r"(?<![\w&])#([0-9A-Fa-f]{6}|[0-9A-Fa-f]{3})(?![0-9A-Fa-f\w])")
RGB_RE = re.compile(
    r"\bRGB\s*[:(]?\s*(\d{1,3})\s*[,/ ]\s*(\d{1,3})\s*[,/ ]\s*(\d{1,3})\s*\)?", re.I)
RGB_FN_RE = re.compile(r"\brgba?\(\s*(\d{1,3})\s*,\s*(\d{1,3})\s*,\s*(\d{1,3})", re.I)
CMYK_RE = re.compile(
    r"\bCMYK\s*[:(]?\s*(\d{1,3})%?\s*[,/ ]\s*(\d{1,3})%?\s*[,/ ]\s*(\d{1,3})%?\s*[,/ ]\s*(\d{1,3})%?", re.I)
CMYK_LETTERS_RE = re.compile(r"\bC\s?(\d{1,3})\s+M\s?(\d{1,3})\s+Y\s?(\d{1,3})\s+K\s?(\d{1,3})\b")
HSL_RE = re.compile(r"\bhsla?\(\s*(\d{1,3}(?:\.\d+)?)\s*,\s*(\d{1,3})%\s*,\s*(\d{1,3})%", re.I)
PANTONE_RE = re.compile(
    r"\b(?:Pantone|PMS)\s*:?\s*((?:Cool|Warm)\s+Gr[ae]y\s+\d{1,2}\s*[CUM]?|[A-Za-z]+\s+[CUM]\b|\d{3,5}\s*[CUM]?\b)", re.I)


def norm_hex(h: str) -> str:
    h = h.lstrip("#").upper()
    if len(h) == 3:
        h = "".join(c * 2 for c in h)
    return f"#{h}"


def hex_to_rgb(h: str) -> tuple[int, int, int]:
    h = norm_hex(h)[1:]
    return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)


def rgb_to_hex(r: int, g: int, b: int) -> str:
    return f"#{r:02X}{g:02X}{b:02X}"


def cmyk_to_rgb(c: float, m: float, y: float, k: float) -> tuple[int, int, int]:
    c, m, y, k = (v / 100 for v in (c, m, y, k))
    return tuple(round(255 * (1 - x) * (1 - k)) for x in (c, m, y))  # type: ignore[return-value]


def hsl_to_rgb(h: float, s: float, light: float) -> tuple[int, int, int]:
    s, light = s / 100, light / 100
    c = (1 - abs(2 * light - 1)) * s
    x = c * (1 - abs((h / 60) % 2 - 1))
    m = light - c / 2
    r, g, b = [(c, x, 0), (x, c, 0), (0, c, x), (0, x, c), (x, 0, c), (c, 0, x)][int(h // 60) % 6]
    return tuple(round((v + m) * 255) for v in (r, g, b))  # type: ignore[return-value]


@dataclass
class ColorMention:
    hex: str  # canonical
    span: tuple[int, int]
    source: str  # hex | rgb | cmyk | hsl
    specs: dict = field(default_factory=dict)  # {"hex": .., "rgb": "r, g, b", "cmyk": .., "pantone": ..}


def find_colors(text: str) -> list[ColorMention]:
    """Find colour values in text. Specs that appear together (HEX + RGB + CMYK + Pantone of the same
    swatch) are merged into the hex mention they follow."""
    found: list[ColorMention] = []
    for m in HEX_RE.finditer(text):
        found.append(ColorMention(norm_hex(m.group(1)), m.span(), "hex", {"hex": norm_hex(m.group(1))}))
    for regex in (RGB_RE, RGB_FN_RE):
        for m in regex.finditer(text):
            r, g, b = (int(x) for x in m.groups())
            if max(r, g, b) <= 255:
                found.append(ColorMention(rgb_to_hex(r, g, b), m.span(), "rgb", {"rgb": f"{r}, {g}, {b}"}))
    for regex in (CMYK_RE, CMYK_LETTERS_RE):
        for m in regex.finditer(text):
            vals = [int(x) for x in m.groups()]
            if max(vals) <= 100:
                found.append(ColorMention(rgb_to_hex(*cmyk_to_rgb(*vals)), m.span(), "cmyk",
                                          {"cmyk": ", ".join(str(v) for v in vals)}))
    for m in HSL_RE.finditer(text):
        h, s, li = float(m.group(1)), float(m.group(2)), float(m.group(3))
        found.append(ColorMention(rgb_to_hex(*hsl_to_rgb(h, s, li)), m.span(), "hsl", {"hsl": f"{h:g}, {s:g}%, {li:g}%"}))
    found.sort(key=lambda c: c.span[0])
    pantones = [(m.span(), re.sub(r"\s+", " ", m.group(1)).strip()) for m in PANTONE_RE.finditer(text)]

    # Merge specs that describe the same swatch: anchor on HEX when present, else first value.
    merged: list[ColorMention] = []
    for c in found:
        if merged and c.source != "hex" and _close_spans(merged[-1], c, text) and \
                (c.source == "rgb" and delta_e(merged[-1].hex, c.hex) < 2.5 or c.source in ("cmyk", "hsl")):
            if c.source not in merged[-1].specs:
                merged[-1].specs[c.source] = c.specs[c.source]
            merged[-1].span = (merged[-1].span[0], c.span[1])
            continue
        merged.append(c)
    for span, value in pantones:
        target = min(merged, key=lambda c: abs(c.span[1] - span[0]), default=None)
        if target is not None and abs(target.span[1] - span[0]) < 60:
            target.specs.setdefault("pantone", value)
    return merged


def _close_spans(a: ColorMention, b: ColorMention, text: str) -> bool:
    gap = text[a.span[1] : b.span[0]]
    return len(gap) < 40 and not re.search(r"[.;]\s", gap)


# -- colour science -------------------------------------------------------------------------------
def _srgb_to_linear(c: float) -> float:
    c = c / 255
    return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4


def hex_to_lab(h: str) -> tuple[float, float, float]:
    r, g, b = (_srgb_to_linear(v) for v in hex_to_rgb(h))
    x = (0.4124564 * r + 0.3575761 * g + 0.1804375 * b) / 0.95047
    y = (0.2126729 * r + 0.7151522 * g + 0.0721750 * b) / 1.0
    z = (0.0193339 * r + 0.1191920 * g + 0.9503041 * b) / 1.08883

    def f(t):
        return t ** (1 / 3) if t > 216 / 24389 else (24389 / 27 * t + 16) / 116

    fx, fy, fz = f(x), f(y), f(z)
    return 116 * fy - 16, 500 * (fx - fy), 200 * (fy - fz)


def rgb_array_to_lab(arr):
    """Vectorised sRGB (N×3 uint8) → Lab (N×3 float)."""
    import numpy as np

    c = arr.astype("float64") / 255
    lin = np.where(c <= 0.04045, c / 12.92, ((c + 0.055) / 1.055) ** 2.4)
    m = np.array([[0.4124564, 0.3575761, 0.1804375], [0.2126729, 0.7151522, 0.0721750],
                  [0.0193339, 0.1191920, 0.9503041]])
    xyz = lin @ m.T / np.array([0.95047, 1.0, 1.08883])
    f = np.where(xyz > 216 / 24389, np.cbrt(xyz), (24389 / 27 * xyz + 16) / 116)
    return np.stack([116 * f[:, 1] - 16, 500 * (f[:, 0] - f[:, 1]), 200 * (f[:, 1] - f[:, 2])], axis=1)


def lab_to_hex(lab: tuple[float, float, float]) -> str:
    L, a, b = lab
    fy = (L + 16) / 116
    fx, fz = fy + a / 500, fy - b / 200

    def finv(t):
        return t**3 if t**3 > 216 / 24389 else (116 * t - 16) / (24389 / 27)

    x, y, z = finv(fx) * 0.95047, finv(fy), finv(fz) * 1.08883
    rl = 3.2404542 * x - 1.5371385 * y - 0.4985314 * z
    gl = -0.9692660 * x + 1.8760108 * y + 0.0415560 * z
    bl = 0.0556434 * x - 0.2040259 * y + 1.0572252 * z

    def enc(c):
        c = max(0.0, min(1.0, c))
        v = 12.92 * c if c <= 0.0031308 else 1.055 * c ** (1 / 2.4) - 0.055
        return round(v * 255)

    return rgb_to_hex(enc(rl), enc(gl), enc(bl))


def ciede2000(lab1, lab2) -> float:
    """CIEDE2000 colour difference (Sharma et al. 2005 reference implementation)."""
    L1, a1, b1 = lab1
    L2, a2, b2 = lab2
    C1, C2 = math.hypot(a1, b1), math.hypot(a2, b2)
    Cbar = (C1 + C2) / 2
    G = 0.5 * (1 - math.sqrt(Cbar**7 / (Cbar**7 + 25**7)))
    a1p, a2p = (1 + G) * a1, (1 + G) * a2
    C1p, C2p = math.hypot(a1p, b1), math.hypot(a2p, b2)
    h1p = math.degrees(math.atan2(b1, a1p)) % 360 if (a1p or b1) else 0.0
    h2p = math.degrees(math.atan2(b2, a2p)) % 360 if (a2p or b2) else 0.0
    dLp = L2 - L1
    dCp = C2p - C1p
    if C1p * C2p == 0:
        dhp = 0.0
    elif abs(h2p - h1p) <= 180:
        dhp = h2p - h1p
    elif h2p - h1p > 180:
        dhp = h2p - h1p - 360
    else:
        dhp = h2p - h1p + 360
    dHp = 2 * math.sqrt(C1p * C2p) * math.sin(math.radians(dhp / 2))
    Lbarp = (L1 + L2) / 2
    Cbarp = (C1p + C2p) / 2
    if C1p * C2p == 0:
        hbarp = h1p + h2p
    elif abs(h1p - h2p) <= 180:
        hbarp = (h1p + h2p) / 2
    elif h1p + h2p < 360:
        hbarp = (h1p + h2p + 360) / 2
    else:
        hbarp = (h1p + h2p - 360) / 2
    T = (1 - 0.17 * math.cos(math.radians(hbarp - 30)) + 0.24 * math.cos(math.radians(2 * hbarp))
         + 0.32 * math.cos(math.radians(3 * hbarp + 6)) - 0.20 * math.cos(math.radians(4 * hbarp - 63)))
    dtheta = 30 * math.exp(-(((hbarp - 275) / 25) ** 2))
    Rc = 2 * math.sqrt(Cbarp**7 / (Cbarp**7 + 25**7))
    Sl = 1 + 0.015 * (Lbarp - 50) ** 2 / math.sqrt(20 + (Lbarp - 50) ** 2)
    Sc = 1 + 0.045 * Cbarp
    Sh = 1 + 0.015 * Cbarp * T
    Rt = -math.sin(math.radians(2 * dtheta)) * Rc
    return math.sqrt((dLp / Sl) ** 2 + (dCp / Sc) ** 2 + (dHp / Sh) ** 2 + Rt * (dCp / Sc) * (dHp / Sh))


def delta_e(hex1: str, hex2: str) -> float:
    return ciede2000(hex_to_lab(hex1), hex_to_lab(hex2))


def relative_luminance(h: str) -> float:
    r, g, b = (_srgb_to_linear(v) for v in hex_to_rgb(h))
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def contrast_ratio(fg: str, bg: str) -> float:
    l1, l2 = sorted((relative_luminance(fg), relative_luminance(bg)), reverse=True)
    return (l1 + 0.05) / (l2 + 0.05)


def wcag_level(ratio: float, large_text: bool = False) -> str:
    if ratio >= (4.5 if large_text else 7):
        return "AAA"
    if ratio >= (3 if large_text else 4.5):
        return "AA"
    return "fail"


def color_name_hint(h: str) -> str:
    """Coarse hue family, used for UI labels when a guide gives no name."""
    L, a, b = hex_to_lab(h)
    C = math.hypot(a, b)
    if C < 8:
        return "black" if L < 20 else "white" if L > 92 else "gray"
    hue = math.degrees(math.atan2(b, a)) % 360
    for limit, name in [(20, "pink"), (50, "red"), (75, "orange"), (100, "yellow"), (150, "green"),
                        (200, "teal"), (285, "blue"), (330, "purple"), (360, "pink")]:
        if hue < limit:
            return ("dark " if L < 35 else "light " if L > 80 else "") + name
    return "color"
