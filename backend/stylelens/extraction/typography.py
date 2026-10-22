"""Typography extraction: type-scale tables, "Role: Family Weight size/line-height" declarations,
fallback stacks, and fonts actually used in the PDF (span metadata)."""

import re
from collections import defaultdict

from stylelens.extraction.common import El, normative_level
from stylelens.schema.profile import FontUsage, TypographyItem

WEIGHTS = {
    "thin": "100", "hairline": "100", "extralight": "200", "extra light": "200", "ultralight": "200",
    "light": "300", "regular": "400", "normal": "400", "book": "400", "roman": "400", "medium": "500",
    "semibold": "600", "semi bold": "600", "demibold": "600", "bold": "700", "extrabold": "800",
    "extra bold": "800", "heavy": "800", "black": "900",
}
WEIGHT_RE = re.compile(r"\b(" + "|".join(sorted((re.escape(w) for w in WEIGHTS), key=len, reverse=True))
                       + r"|[1-9]00)\b", re.I)
KNOWN_FONTS = [
    "Inter", "Roboto", "Open Sans", "Lato", "Montserrat", "Poppins", "Source Sans 3", "Source Sans Pro",
    "Source Serif", "Noto Sans", "Noto Serif", "Raleway", "Nunito", "Nunito Sans", "Work Sans", "Rubik",
    "IBM Plex Sans", "IBM Plex Serif", "IBM Plex Mono", "DM Sans", "DM Serif Display", "Manrope", "Karla",
    "Fraunces", "Playfair Display", "Merriweather", "Lora", "PT Sans", "PT Serif", "Libre Baskerville",
    "Crimson Pro", "EB Garamond", "Cormorant", "Space Grotesk", "Space Mono", "JetBrains Mono", "Fira Sans",
    "Fira Code", "Ubuntu", "Oswald", "Barlow", "Mulish", "Quicksand", "Archivo", "Instrument Sans",
    "Instrument Serif", "Geist", "Geist Mono", "Helvetica Neue", "Helvetica", "Arial", "Georgia",
    "Times New Roman", "Times", "Verdana", "Futura", "Gotham", "Proxima Nova", "Avenir Next", "Avenir",
    "Gill Sans", "Garamond", "Baskerville", "Didot", "Bodoni", "Akzidenz-Grotesk", "Univers", "Frutiger",
    "San Francisco", "SF Pro", "SF Pro Text", "SF Pro Display", "Segoe UI", "Calibri", "Cambria",
    "Courier New", "Courier", "Menlo", "Monaco", "Comic Sans", "Comic Sans MS", "Tahoma", "Trebuchet MS",
    "Graphik", "Circular", "Apercu", "GT America", "GT Walsheim", "Neue Haas Grotesk", "Söhne", "Sohne",
    "Recoleta", "Canela", "Tiempos", "Publico", "Atlas Grotesk", "Aktiv Grotesk", "Brandon Grotesque",
]
_FONT_RE = re.compile(r"\b(" + "|".join(sorted((re.escape(f) for f in KNOWN_FONTS), key=len, reverse=True)) + r")\b")
SIZE_RE = re.compile(r"(\d+(?:\.\d+)?)\s?(px|pt|rem|em)\b(?:\s*/\s*(\d+(?:\.\d+)?)\s?(px|pt|rem|em|%)?)?", re.I)
LH_RE = re.compile(r"line[- ]height\s*(?:is|of|:)?\s*(\d+(?:\.\d+)?\s?(?:px|pt|%|em|rem)?)", re.I)
TRACKING_RE = re.compile(r"([+-]?\d+(?:\.\d+)?\s?(?:%|em|px))\s*(?:letter[- ]spacing|tracking)|(?:letter[- ]spacing|tracking)\s*(?:of|:)?\s*([+-]?\d+(?:\.\d+)?\s?(?:%|em|px))", re.I)
ROLE_PREFIX_RE = re.compile(
    r"^\s*(display|headlines?|headings?|titles?|h[1-6]|body(?: copy| text)?|text|captions?|labels?|ui|"
    r"buttons?|code|mono(?:space)?|subheads?|eyebrows?|quotes?|typeface|primary typeface|secondary typeface)\s*[:—–-]\s*", re.I)
ROLE_NORMALISE = {
    "headline": "headline", "headlines": "headline", "heading": "heading", "headings": "heading",
    "title": "title", "titles": "title", "body copy": "body", "body text": "body", "body": "body",
    "text": "body", "caption": "caption", "captions": "caption", "label": "label", "labels": "label",
    "button": "button", "buttons": "button", "mono": "code", "monospace": "code", "subhead": "subhead",
    "subheads": "subhead", "typeface": "primary", "primary typeface": "primary", "secondary typeface": "secondary",
}


def find_fonts(text: str) -> list[str]:
    return list(dict.fromkeys(m.group(1) for m in _FONT_RE.finditer(text)))


def _weight(text: str) -> str | None:
    m = WEIGHT_RE.search(text)
    if not m:
        return None
    w = m.group(1).lower()
    label = w.title() if not w.isdigit() else None
    num = WEIGHTS.get(w, w)
    return f"{label} ({num})" if label else num


def _size(text: str) -> tuple[str | None, str | None]:
    m = SIZE_RE.search(text)
    if not m:
        return None, None
    size = f"{m.group(1)}{m.group(2).lower()}"
    lh = f"{m.group(3)}{(m.group(4) or m.group(2)).lower()}" if m.group(3) else None
    return size, lh


def _summary(family: str, weight: str | None, size: str | None, lh: str | None) -> str:
    parts = [family]
    if weight:
        parts.append(weight.split(" (")[0] if "(" in weight else weight)
    if size:
        parts.append(f"{size}/{lh}" if lh else size)
    return " ".join(parts)


def _role_from(label: str) -> str:
    low = label.strip().lower()
    if re.fullmatch(r"h[1-6]", low):
        return low
    return ROLE_NORMALISE.get(low, low)


def extract_typography(elements: list[El], doc_meta: dict | None = None) -> tuple[list[TypographyItem], list[FontUsage]]:
    items: list[TypographyItem] = []
    fallbacks: dict[str, list[str]] = {}

    def add(role, family, weight, size, lh, el: El, quote: str, tracking=None, case=None):
        for it in items:
            if it.role == role and it.family == family and (it.size == size or not size or not it.size):
                it.size = it.size or size
                it.line_height = it.line_height or lh
                it.weight = it.weight or weight
                it.source_refs.append(el.ref(quote))
                return
        items.append(TypographyItem(
            id=f"type-{len(items) + 1}", role=role, family=family, weight=weight, size=size, line_height=lh,
            letter_spacing=tracking, case=case, value=_summary(family, weight, size, lh),
            normative_level=normative_level(quote), usage=[quote[:200]], source_refs=[el.ref(quote)]))

    for el in elements:
        if el.type == "table" and el.meta.get("rows"):
            rows = el.meta["rows"]
            header = [h.lower() for h in rows[0]]
            role_col = next((i for i, h in enumerate(header) if re.search(r"style|level|element|role|token|name", h)), None)
            font_col = next((i for i, h in enumerate(header) if re.search(r"typeface|font|family", h)), None)
            if role_col is None or font_col is None:
                continue
            size_col = next((i for i, h in enumerate(header) if "size" in h), None)
            lh_col = next((i for i, h in enumerate(header) if "line" in h and size_col != header.index(h)), None)
            tr_col = next((i for i, h in enumerate(header) if "spacing" in h or "tracking" in h), None)
            for row in rows[1:]:
                if len(row) <= max(role_col, font_col):
                    continue
                fams = find_fonts(row[font_col]) or ([row[font_col].split()[0]] if row[font_col].strip() else [])
                if not fams:
                    continue
                size, lh = _size(row[size_col]) if size_col is not None and size_col < len(row) else (None, None)
                if lh is None and lh_col is not None and lh_col < len(row):
                    lh = row[lh_col].strip() or None
                tracking = row[tr_col].strip() if tr_col is not None and tr_col < len(row) else None
                add(_role_from(row[role_col]), fams[0], _weight(row[font_col]), size, lh, el, " | ".join(row), tracking)
            continue

        if el.type not in ("list_item", "paragraph", "heading"):
            continue
        text = el.text
        if re.match(r"^\s*fallbacks?\s*[:—–-]", text, re.I):
            for part in re.split(r";", text.split(":", 1)[-1]):
                m = re.match(r"\s*(.+?)\s+for\s+(.+?)\.?\s*$", part)
                if m:
                    fallbacks[m.group(2).strip()] = [f.strip() for f in m.group(1).split(",") if f.strip()]
            continue
        prefix = ROLE_PREFIX_RE.match(text)
        in_type_section = re.search(r"typ(e|ography)|font", el.section, re.I)
        fams = find_fonts(text)
        if not fams or not (prefix or in_type_section):
            continue
        role = _role_from(prefix.group(1)) if prefix else "primary"
        body = text[prefix.end():] if prefix else text
        size, lh = _size(body)
        if lh is None and (m := LH_RE.search(body)):
            lh = m.group(1)
        tr = TRACKING_RE.search(body)
        case = "uppercase" if re.search(r"all caps|uppercase", body, re.I) else (
            "sentence" if re.search(r"sentence case", body, re.I) else None)
        weight = _weight(body.split(".")[0])
        # "Text: Inter Regular (400) and Inter Medium (500)" — one item per family mention
        for fam in fams:
            add(role, fam, weight, size, lh, el, text, (tr.group(1) or tr.group(2)) if tr else None, case)

    for it in items:
        it.fallbacks = fallbacks.get(it.family, [])

    # Fonts observed in the document itself
    usage: dict[str, FontUsage] = {}
    embedded = set((doc_meta or {}).get("embedded_fonts", []))
    sizes: dict[str, set] = defaultdict(set)
    for el in elements:
        for f in el.meta.get("fonts", []) or []:
            fam = f.get("font")
            if not fam:
                continue
            u = usage.setdefault(fam, FontUsage(family=fam, embedded=fam in embedded))
            u.chars += int(f.get("chars") or 0)
            u.bold = u.bold or bool(f.get("bold"))
            if f.get("size"):
                sizes[fam].add(float(f["size"]))
    for fam, u in usage.items():
        u.sizes = sorted(sizes[fam])
    detected = sorted(usage.values(), key=lambda u: -u.chars)
    return items, detected
