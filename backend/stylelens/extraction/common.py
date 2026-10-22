"""Shared helpers for extractors: a light element view, clause splitting, directive detection."""

import re
from dataclasses import dataclass, field

from stylelens.schema.profile import NormativeLevel, Polarity, SourceRef


@dataclass
class El:
    id: str
    seq: int
    page: int
    type: str
    text: str
    heading_path: list[str]
    bbox: list[float] | None = None
    level: int | None = None
    meta: dict = field(default_factory=dict)
    image_key: str | None = None

    def ref(self, quote: str = "") -> SourceRef:
        return SourceRef(element_id=self.id, page=self.page, bbox=self.bbox, quote=(quote or self.text)[:300])

    @property
    def section(self) -> str:
        return " > ".join(self.heading_path)


def from_row(row) -> El:
    return El(id=row.id, seq=row.seq, page=row.page, type=row.type, text=row.text or "",
              heading_path=list(row.heading_path or []), bbox=row.bbox, level=row.level,
              meta=row.meta or {}, image_key=row.image_key)


CLAUSE_SPLIT = re.compile(r"(?<=[.!?;])\s+(?=[A-Z\"“(])|;\s+")


def clauses(text: str) -> list[str]:
    return [c.strip() for c in CLAUSE_SPLIT.split(text) if c.strip()]


NEG_RE = re.compile(r"\b(never|do not|don't|dont|must not|should not|shouldn't|cannot|can't|avoid|no longer|not allowed|prohibited|forbidden)\b", re.I)
MUST_RE = re.compile(r"\b(must|never|always|required|requires|shall|do not|don't|only|at least|no smaller than|no more than|minimum|maximum|reserved)\b", re.I)
SHOULD_RE = re.compile(r"\b(should|avoid|prefer|preferred|recommend(?:ed)?|try to|ideally|aim)\b", re.I)
MAY_RE = re.compile(r"\b(may|can|allowed|optional(?:ly)?|permitted|acceptable)\b", re.I)
DIRECTIVE_RE = re.compile(
    r"\b(must|never|always|should|do not|don't|avoid|use|keep|prefer|required|may|only|at least|no more than|"
    r"minimum|maximum|reserved|write|address|place|pair|set|apply|ensure|make sure|limit|spell out|capitali[sz]e)\b",
    re.I)
QUANTITY_RE = re.compile(r"\d+(?:\.\d+)?\s?(?:px|pt|mm|cm|in|em|rem|%|:1|x)\b|\d+\s?(?:by|x|×)\s?\d+\s?px", re.I)


def normative_level(text: str) -> NormativeLevel:
    if MUST_RE.search(text):
        return "must"
    if SHOULD_RE.search(text):
        return "should"
    if MAY_RE.search(text):
        return "may"
    return "should"


def polarity(text: str, marker: str | None = None, section: str = "") -> Polarity:
    if marker and marker.strip() in ("✗", "✘", "×", "x", "X"):
        return "dont"
    if NEG_RE.search(text):
        return "dont"
    if re.search(r"\b(misuse|don'?ts?|incorrect|never)\b", section, re.I) and not re.match(r"\s*(do|use)\b", text, re.I):
        return "dont"
    return "do"


CATEGORY_KEYWORDS: list[tuple[str, tuple[str, ...]]] = [
    ("logo_rules", ("logo", "logotype", "wordmark", "monogram", "lockup", "brandmark", "clear space", "clearspace")),
    ("accessibility", ("accessib", "a11y", "wcag", "contrast", "alt text", "screen reader", "touch target", "dynamic type")),
    ("color_usage", ("color", "colour", "palette", "swatch", "pantone")),
    ("typography_usage", ("typograph", "typeface", "font", "type scale", "letter spacing", "line height", "heading size")),
    ("voice_tone", ("voice", "tone", "personality", "persona", "sound like", "brand character")),
    ("writing_rules", ("writing", "grammar", "mechanic", "punctuation", "spelling", "words", "content style",
                       "reading level", "terminology", "language", "copy", "dates", "numbers", "capitali")),
    ("imagery_rules", ("imagery", "photo", "photograph", "illustration", "icon", "image", "video", "graphic")),
    ("components", ("component", "button", "form", "input", "card", "navigation", "ui ", "ui:", "modal", "link")),
    ("spacing_grid", ("spacing", "grid", "layout", "margin", "gutter", "column", "padding", "whitespace")),
]


def categorize(section: str, text: str) -> str:
    """Pick a rule category from the heading path first, then from the rule text."""
    sec = section.lower()
    # deepest heading wins: score keywords by the heading depth they appear at
    parts = [p.lower() for p in section.split(" > ")] if section else []
    for part in reversed(parts):
        for cat, kws in CATEGORY_KEYWORDS:
            if any(k in part for k in kws):
                return cat
    low = text.lower()
    for cat, kws in CATEGORY_KEYWORDS:
        if any(k in low for k in kws):
            return cat
    return "misc_rules" if sec or low else "misc_rules"
