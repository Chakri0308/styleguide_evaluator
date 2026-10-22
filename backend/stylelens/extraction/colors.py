"""Colour extraction: text mentions (HEX/RGB/CMYK/HSL/Pantone), vector swatches, and image pixels
(k-means in Lab), merged by perceptual distance and annotated with names, roles and usage."""

import io
import re
from collections import defaultdict

import numpy as np

from stylelens.colors import ciede2000, find_colors, hex_to_lab, lab_to_hex, rgb_array_to_lab
from stylelens.extraction.common import El, NEG_RE, clauses, normative_level
from stylelens.schema.profile import ColorItem, SourceRef

MERGE_DE = 1.5
ROLE_WORDS = [
    ("primary", ("primary", "main brand", "lead colour", "lead color", "hero")),
    ("secondary", ("secondary", "supporting")),
    ("accent", ("accent", "call to action", "call-to-action", "cta", "highlight")),
    ("background", ("background", "surface", "canvas", "paper")),
    ("text", ("body text", "text colour", "text color", "for text", "copy", "type colour")),
    ("neutral", ("neutral", "gray", "grey")),
    ("error", ("error", "alert", "danger", "destructive", "critical")),
    ("success", ("success", "positive", "confirm")),
    ("warning", ("warning", "caution")),
    ("link", ("link",)),
]
NAME_BEFORE_RE = re.compile(r"([A-Z][\w'’-]*(?:\s+[A-Z0-9][\w'’-]*){0,3})\s*[(:—–-]\s*$")
SPEC_LINE_RE = re.compile(r"^\s*(HEX|RGB|CMYK|HSL|PMS|Pantone|#)", re.I)


def _short_label(text: str) -> bool:
    words = text.split()
    return 0 < len(words) <= 4 and not re.search(r"\d|#", text) and len(text) <= 40


def _name_from_context(el: El, start: int, elements_by_seq: dict[int, El]) -> str | None:
    before = el.text[:start]
    if el.type == "table":
        cell = before.rsplit("|", 1)[-1].strip()
        if _short_label(cell):
            return cell
    m = NAME_BEFORE_RE.search(before)
    if m:
        name = m.group(1).strip()
        if name.upper() not in ("HEX", "RGB", "CMYK", "HSL", "PMS") and not re.match(r"^(Use|The|A|An|Never|Do)\b", name):
            return name
    # Spec block ("HEX #… RGB …") directly under a short label
    if SPEC_LINE_RE.match(el.text):
        prev = elements_by_seq.get(el.seq - 1)
        if prev and prev.page == el.page and _short_label(prev.text):
            return prev.text.strip()
    return None


def _swatch_label(sw: El, text_els: list[El]) -> tuple[str | None, El | None]:
    """Nearest short text directly below (or inside) the swatch, horizontally overlapping."""
    if not sw.bbox:
        return None, None
    x0, y0, x1, y1 = sw.bbox
    best, best_d = None, 1e9
    for t in text_els:
        if t.page != sw.page or not t.bbox or not t.text.strip():
            continue
        tx0, ty0, tx1, ty1 = t.bbox
        h_overlap = min(x1, tx1) - max(x0, tx0)
        if h_overlap <= 0:
            continue
        inside = ty0 >= y0 - 1 and ty1 <= y1 + 1
        below = 0 <= ty0 - y1 <= 40
        right = 0 <= tx0 - x1 <= 30 and min(y1, ty1) - max(y0, ty0) > 0
        if not (inside or below or right):
            continue
        d = 0 if inside else (ty0 - y1 if below else tx0 - x1)
        if d < best_d and (_short_label(t.text) or SPEC_LINE_RE.match(t.text)):
            best, best_d = t, d
    if best is None:
        return None, None
    if _short_label(best.text):
        return best.text.strip(), best
    return None, best


def dominant_colors(image_bytes: bytes, k: int = 5, min_share: float = 0.04) -> list[tuple[str, float]]:
    """k-means clustering in Lab space; returns [(hex, share)] sorted by share."""
    from PIL import Image
    from sklearn.cluster import KMeans

    img = Image.open(io.BytesIO(image_bytes)).convert("RGBA")
    img.thumbnail((160, 160))
    arr = np.asarray(img).reshape(-1, 4)
    arr = arr[arr[:, 3] > 200][:, :3]  # drop transparent pixels
    if len(arr) < k:
        return []
    lab = rgb_array_to_lab(arr)
    km = KMeans(n_clusters=k, n_init=4, random_state=0).fit(lab)
    counts = np.bincount(km.labels_, minlength=k) / len(lab)
    out = [(lab_to_hex(tuple(c)), float(s)) for c, s in zip(km.cluster_centers_, counts, strict=True) if s >= min_share]
    return sorted(out, key=lambda t: (-t[1], t[0]))


class _Cand:
    def __init__(self, hex_: str):
        self.hex = hex_
        self.lab = hex_to_lab(hex_)
        self.names: list[str] = []
        self.specs: dict[str, str] = {}
        self.refs: list[SourceRef] = []
        self.origin: set[str] = set()
        self.clauses: list[str] = []
        self.prohibited_votes = 0
        self.approved_votes = 0
        self.first_seq = 10**9


def extract_colors(elements: list[El], images: dict[str, bytes] | None = None,
                   image_only_doc: bool = False) -> tuple[list[ColorItem], dict[str, list[str]]]:
    """Returns colour items plus {element_id: dominant hexes} for image elements."""
    by_seq = {e.seq: e for e in elements}
    text_els = [e for e in elements if e.type not in ("image", "swatch") and e.text]
    cands: list[_Cand] = []

    def add(hex_: str) -> _Cand:
        lab = hex_to_lab(hex_)
        for c in cands:
            if ciede2000(c.lab, lab) < MERGE_DE:
                return c
        c = _Cand(hex_)
        cands.append(c)
        return c

    # 1) Vector swatches (strongest signal of a palette)
    used_label_ids: set[str] = set()
    for sw in (e for e in elements if e.type == "swatch"):
        fill = sw.meta.get("fill")
        if not fill:
            continue
        label, label_el = _swatch_label(sw, text_els)
        # Ignore decorative fills with no nearby label or spec text
        spec_el = None
        if label_el is not None:
            nxt = by_seq.get(label_el.seq + 1)
            spec_el = label_el if SPEC_LINE_RE.match(label_el.text) else (nxt if nxt and SPEC_LINE_RE.match(nxt.text) else None)
        if label is None and spec_el is None:
            continue
        c = add(fill)
        c.origin.add("swatch")
        c.first_seq = min(c.first_seq, sw.seq)
        c.approved_votes += 1
        if label:
            c.names.append(label)
            used_label_ids.add(label_el.id)
        c.refs.append(sw.ref(f"{label or ''} swatch {fill}".strip()))

    # 2) Text mentions
    for el in text_els:
        for mention in find_colors(el.text):
            c = add(mention.hex)
            c.origin.add("text")
            c.first_seq = min(c.first_seq, el.seq)
            for k, v in mention.specs.items():
                c.specs.setdefault(k, v)
            name = _name_from_context(el, mention.span[0], by_seq)
            if name:
                c.names.append(name)
            units = el.text.splitlines() if el.type == "table" else clauses(el.text)
            clause = next((cl for cl in units if mention.hex[1:].lower() in cl.lower()
                           or el.text[mention.span[0]:mention.span[1]] in cl), el.text)
            c.clauses.append(clause)
            # A colour is prohibited when a negation governs it ("never use pure black #000000"),
            # i.e. the negation precedes the mention; "Ember (#D9622B) must not be used for X"
            # restricts usage of an approved colour instead.
            raw = el.text[mention.span[0]:mention.span[1]]
            pos = clause.find(raw)
            neg = NEG_RE.search(clause)
            negated = neg is not None and pos >= 0 and neg.start() < pos and \
                not re.search(r"\b(on|over|with|against|behind)\b", clause[neg.end():pos])
            if negated:
                c.prohibited_votes += 1
            else:
                c.approved_votes += 1
            c.refs.append(el.ref(clause))

    # 3) Image pixels: dominant colours per image (always recorded); palette only for image-only docs
    image_palettes: dict[str, list[str]] = {}
    for el in (e for e in elements if e.type == "image" and e.image_key and images and e.image_key in images):
        try:
            dom = dominant_colors(images[el.image_key])
        except Exception:  # noqa: BLE001
            dom = []
        image_palettes[el.id] = [h for h, _ in dom]
        if image_only_doc and not cands:
            for h, share in dom:
                c = add(h)
                c.origin.add("image")
                c.first_seq = min(c.first_seq, el.seq)
                c.approved_votes += 1
                c.refs.append(el.ref(f"Dominant colour {h} ({share:.0%} of image)"))

    table_votes = _table_role_votes(elements)

    # Usage clauses: any sentence mentioning the colour by name
    all_clauses = [(el, cl) for el in text_els for cl in clauses(el.text)]
    items: list[ColorItem] = []
    for i, c in enumerate(sorted(cands, key=lambda c: (c.first_seq, c.hex))):
        name = _best_name(c.names)
        usage = list(dict.fromkeys(c.clauses))
        if name:
            for el, cl in all_clauses:
                if re.search(rf"\b{re.escape(name)}\b", cl) and cl not in usage and not SPEC_LINE_RE.match(cl):
                    usage.append(cl)
                    if not any(r.element_id == el.id for r in c.refs):
                        c.refs.append(el.ref(cl))
        role = _infer_role(name, usage, table_votes.get(c.hex))
        prohibited = c.prohibited_votes > 0 and c.approved_votes == 0
        items.append(ColorItem(
            id=f"color-{i + 1}",
            name=name,
            role=role,
            value=c.hex,
            hex=c.hex,
            rgb=c.specs.get("rgb"),
            cmyk=c.specs.get("cmyk"),
            hsl=c.specs.get("hsl"),
            pantone=c.specs.get("pantone"),
            lab=[round(v, 2) for v in c.lab],
            normative_level="must" if prohibited or any(normative_level(u) == "must" for u in usage) else "should",
            status="prohibited" if prohibited else "approved",
            usage=usage[:8],
            origin=sorted(c.origin),
            source_refs=c.refs[:10],
        ))
    return items, image_palettes


def _best_name(names: list[str]) -> str | None:
    if not names:
        return None
    counts: dict[str, int] = defaultdict(int)
    for n in names:
        counts[n] += 1
    return sorted(counts, key=lambda n: (-counts[n], len(n)))[0]


def _infer_role(name: str | None, usage: list[str], table_votes: dict[str, int] | None = None) -> str | None:
    """Role from the colour's name, then the role word closest to the name in prose, then table columns."""
    if name:
        for role, words in ROLE_WORDS:
            if any(w in name.lower() for w in words):
                return role
    best: tuple[int, str] | None = None
    for u in usage:
        if "|" in u:  # table rows are handled through column headers
            continue
        low = u.lower()
        anchor = low.find(name.lower()) if name and name.lower() in low else 0
        for role, words in ROLE_WORDS:
            for w in words:
                for m in re.finditer(rf"\b{re.escape(w)}\b", low):
                    d = abs(m.start() - anchor)
                    if d <= 90 and (best is None or d < best[0]):
                        best = (d, role)
    if best:
        return best[1]
    if table_votes:
        return max(sorted(table_votes), key=lambda r: table_votes[r])
    return None


def _table_role_votes(elements: list[El]) -> dict[str, dict[str, int]]:
    """{hex: {role: count}} from tables whose column headers name a role (Text / Background / ...)."""
    votes: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    for el in elements:
        rows = el.meta.get("rows") if el.type == "table" else None
        if not rows:
            continue
        header_roles = []
        for h in rows[0]:
            hl = (h or "").lower()
            header_roles.append(next((role for role, words in ROLE_WORDS if any(w in hl for w in words + (role,))), None))
        for row in rows[1:]:
            for cell, role in zip(row, header_roles, strict=False):
                if role:
                    for m in find_colors(cell or ""):
                        votes[m.hex][role] += 1
    return votes
