"""HTML parser (stdlib html.parser): headings, paragraphs, list items, tables, image alt text, and the
page's CSS (inline styles and <style> blocks) surfaced as a synthetic "Stylesheet" section so colour
and typography extraction can see declared colours and font families."""

import re
from html.parser import HTMLParser

from stylelens.ingestion.parsers.base import (
    CODE,
    HEADING,
    IMAGE,
    LIST_ITEM,
    PARAGRAPH,
    TABLE,
    ParsedDocument,
    ParsedElement,
    ParsedPage,
    ProgressFn,
)
from stylelens.ingestion.parsers.markdown import _decode
from stylelens.ingestion.parsers.pdf import _table_markdown

BLOCK = {"p", "div", "section", "article", "header", "footer", "main", "aside", "blockquote", "figcaption", "dd", "dt"}
SKIP = {"script", "noscript", "svg", "template", "head"}


class _Walker(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.elements: list[ParsedElement] = []
        self.buf: list[str] = []
        self.kind: str | None = None
        self.level: int | None = None
        self.skip = 0
        self.in_style = False
        self.css: list[str] = []
        self.title: str | None = None
        self.in_title = False
        self.table: list[list[str]] | None = None
        self.cell: list[str] | None = None
        self.pre = False

    def flush(self):
        text = re.sub(r"\s+", " ", "".join(self.buf)).strip() if not self.pre else "".join(self.buf).strip("\n")
        if text and self.kind:
            self.elements.append(ParsedElement(self.kind, text, 1, None, level=self.level))
        self.buf, self.kind, self.level = [], None, None

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if a.get("style"):
            self.css.append(a["style"])
        if tag in SKIP:
            self.skip += 1
            return
        if tag == "style":
            self.in_style = True
        elif tag == "title":
            self.in_title = True
        elif re.fullmatch(r"h[1-6]", tag):
            self.flush()
            self.kind, self.level = HEADING, int(tag[1])
        elif tag == "li":
            self.flush()
            self.kind = LIST_ITEM
        elif tag in ("pre", "code") and self.kind is None:
            self.flush()
            self.kind, self.pre = CODE, tag == "pre"
        elif tag in BLOCK:
            self.flush()
            self.kind = PARAGRAPH
        elif tag == "br":
            self.buf.append(" ")
        elif tag == "table":
            self.flush()
            self.table = []
        elif tag == "tr" and self.table is not None:
            self.table.append([])
        elif tag in ("td", "th") and self.table is not None:
            self.cell = []
        elif tag == "img":
            alt = (a.get("alt") or "").strip()
            self.elements.append(ParsedElement(IMAGE, "", 1, None, meta={"alt": alt, "src": (a.get("src") or "")[:300]}))
            if alt:
                self.elements.append(ParsedElement(PARAGRAPH, alt, 1, None, meta={"alt_text": True}))

    def handle_endtag(self, tag):
        if tag in SKIP:
            self.skip = max(0, self.skip - 1)
            return
        if tag == "style":
            self.in_style = False
        elif tag == "title":
            self.in_title = False
        elif tag in ("td", "th") and self.table is not None and self.cell is not None:
            if self.table:
                self.table[-1].append(re.sub(r"\s+", " ", "".join(self.cell)).strip())
            self.cell = None
        elif tag == "table" and self.table is not None:
            md = _table_markdown(self.table)
            if md:
                self.elements.append(ParsedElement(TABLE, md, 1, None, meta={"rows": self.table}))
            self.table = None
        elif re.fullmatch(r"h[1-6]", tag) or tag in BLOCK or tag == "li" or tag == "pre":
            self.flush()
            self.pre = False

    def handle_data(self, data):
        if self.in_style:
            self.css.append(data)
            return
        if self.in_title:
            self.title = (self.title or "") + data.strip()
            return
        if self.skip:
            return
        if self.cell is not None:
            self.cell.append(data)
            return
        if self.kind is None and data.strip():
            self.kind = PARAGRAPH
        self.buf.append(data)


def css_summary(css: str) -> list[str]:
    """Readable statements from CSS: custom properties, colours and font stacks."""
    out = []
    for name, value in re.findall(r"(--[\w-]+)\s*:\s*([^;}{]+)", css):
        out.append(f"CSS variable {name}: {value.strip()}")
    fams = list(dict.fromkeys(f.strip() for f in re.findall(r"font-family\s*:\s*([^;}{]+)", css, re.I)))
    for fam in fams[:12]:
        out.append(f"Typeface: {fam.split(',')[0].strip(chr(34) + chr(39) + ' ')} (font-family: {fam})")
    colors = list(dict.fromkeys(re.findall(r"#[0-9a-fA-F]{6}\b|#[0-9a-fA-F]{3}\b|rgba?\([^)]*\)", css)))
    if colors:
        out.append("Colors declared in CSS: " + ", ".join(colors[:40]))
    return out


class HtmlParser:
    name = "html.parser"

    def parse(self, data: bytes, filename: str, progress: ProgressFn) -> ParsedDocument:
        w = _Walker()
        w.feed(_decode(data))
        w.close()
        w.flush()
        elements = w.elements
        lines = css_summary("\n".join(w.css))
        if lines:
            elements.append(ParsedElement(HEADING, "Stylesheet typography and colors", 1, None, level=1,
                                          meta={"synthetic": True}))
            elements += [ParsedElement(LIST_ITEM, ln, 1, None, meta={"css": True}) for ln in lines]
        progress(1.0, "Done")
        title = w.title or next((e.text for e in elements if e.type == HEADING), None)
        return ParsedDocument(parser=self.name, title=title, pages=[ParsedPage(1, 612.0, 792.0)], elements=elements,
                              meta={"paged": False})
