"""Layout-aware PDF (and SVG) parser built on PyMuPDF.

Produces headings (levels inferred from font size/weight), paragraphs, list items, tables, raster
images, and vector "swatches" (filled shapes — usually colour chips), each with page + bbox and
span-level font metadata. Scanned pages fall back to OCR.
"""

import re
from collections import Counter

import pymupdf

from stylelens.ingestion.ocr import ocr_available, ocr_image
from stylelens.ingestion.parsers.base import (
    HEADING,
    IMAGE,
    LIST_ITEM,
    PARAGRAPH,
    SWATCH,
    TABLE,
    ParsedDocument,
    ParsedElement,
    ParsedPage,
    ProgressFn,
)

BULLET_RE = re.compile(r"^\s*(?:[•●○▪▫■□◦‣⁃∙·\-–—*✓✔✗✘×→]|\(?\d{1,2}[.)]|\(?[a-z][.)])\s+")
RENDER_DPI = 110
OCR_DPI = 220
MIN_IMAGE_PX = 40
MIN_SWATCH_PT = 10


def _hex(rgb) -> str:
    r, g, b = (max(0, min(255, round(c * 255))) for c in rgb[:3])
    return f"#{r:02X}{g:02X}{b:02X}"


def _int_color_hex(c: int) -> str:
    return f"#{(c >> 16) & 255:02X}{(c >> 8) & 255:02X}{c & 255:02X}"


def _is_bold(span: dict) -> bool:
    name = span.get("font", "").lower()
    return bool(span.get("flags", 0) & 16) or any(w in name for w in ("bold", "black", "heavy", "semibold", "extrabold"))


def _clean_font(name: str) -> str:
    # Subset fonts look like "ABCDEF+Inter-Bold"
    return name.split("+", 1)[-1]


def _table_markdown(rows: list[list]) -> str:
    rows = [[(c or "").replace("\n", " ").strip() for c in r] for r in rows if any(r)]
    if not rows:
        return ""
    width = max(len(r) for r in rows)
    rows = [r + [""] * (width - len(r)) for r in rows]
    out = ["| " + " | ".join(rows[0]) + " |", "|" + "---|" * width]
    out += ["| " + " | ".join(r) + " |" for r in rows[1:]]
    return "\n".join(out)


def _extract_table(page, table) -> list[list[str]]:
    """Cell text via clipped extraction, which preserves word spacing better than Table.extract()."""
    rows = []
    for row in table.rows:
        cells = []
        for cell in row.cells:
            if cell is None:
                cells.append("")
                continue
            txt = page.get_text("text", clip=pymupdf.Rect(cell)).strip()
            cells.append(re.sub(r"\s+", " ", txt))
        rows.append(cells)
    return rows


def _merge_baselines(lines: list[dict]) -> list[dict]:
    """Join lines in a block that sit on the same baseline (e.g. a bullet glyph drawn separately)."""
    out: list[dict] = []
    for ln in lines:
        prev = out[-1] if out else None
        if prev is not None:
            pb, b = prev["bbox"], ln["bbox"]
            overlap = min(pb[3], b[3]) - max(pb[1], b[1])
            if overlap > 0.6 * min(pb[3] - pb[1], b[3] - b[1]) and b[0] >= pb[2] - 1 and b[0] - pb[2] < 40:
                out[-1] = {**prev, "spans": prev["spans"] + ln["spans"],
                           "bbox": (pb[0], min(pb[1], b[1]), b[2], max(pb[3], b[3]))}
                continue
        out.append(ln)
    return out


def _side_by_side(bbox, others) -> bool:
    """True when another line shares this line's vertical band but sits horizontally apart (a grid label)."""
    y0, y1 = bbox[1], bbox[3]
    for o in others:
        if o is bbox:
            continue
        overlap = min(y1, o[3]) - max(y0, o[1])
        if overlap > 0.5 * (y1 - y0) and (o[0] > bbox[2] + 4 or o[2] < bbox[0] - 4):
            return True
    return False


def _inside(inner, outer, tol: float = 2.0) -> bool:
    cx, cy = (inner[0] + inner[2]) / 2, (inner[1] + inner[3]) / 2
    return outer[0] - tol <= cx <= outer[2] + tol and outer[1] - tol <= cy <= outer[3] + tol


class PdfParser:
    name = "pymupdf"

    def __init__(self, filetype: str = "pdf"):
        self.filetype = filetype

    # -- helpers ------------------------------------------------------------------------------
    @staticmethod
    def _line_info(line: dict) -> dict:
        spans = [s for s in line["spans"] if s["text"].strip()]
        # Re-insert spaces between spans that are positioned apart (common with generated PDFs)
        parts: list[str] = []
        prev = None
        for s in line["spans"]:
            if prev is not None and s["bbox"][0] - prev["bbox"][2] > 0.2 * s["size"] \
                    and not parts[-1].endswith(" ") and not s["text"].startswith(" "):
                parts.append(" ")
            parts.append(s["text"])
            prev = s
        text = "".join(parts).strip()
        size = max((s["size"] for s in spans), default=0)
        bold = bool(spans) and all(_is_bold(s) for s in spans)
        return {"text": text, "size": round(size, 1), "bold": bold, "bbox": line["bbox"], "spans": spans}

    @staticmethod
    def _fonts(spans: list[dict]) -> list[dict]:
        seen, out = set(), []
        for s in spans:
            key = (_clean_font(s["font"]), round(s["size"], 1), _is_bold(s), s.get("color", 0))
            if key in seen:
                continue
            seen.add(key)
            out.append({"font": key[0], "size": key[1], "bold": key[2], "color": _int_color_hex(key[3]),
                        "chars": sum(len(x["text"]) for x in spans if _clean_font(x["font"]) == key[0])})
        return out

    # -- main ---------------------------------------------------------------------------------
    def parse(self, data: bytes, filename: str, progress: ProgressFn) -> ParsedDocument:
        doc = pymupdf.open(stream=data, filetype=self.filetype)
        n = doc.page_count
        page_dicts = []
        size_chars: Counter = Counter()
        for page in doc:
            d = page.get_text("dict", flags=pymupdf.TEXTFLAGS_DICT & ~pymupdf.TEXT_PRESERVE_LIGATURES)
            page_dicts.append(d)
            for block in d["blocks"]:
                for line in block.get("lines", []):
                    for s in line["spans"]:
                        size_chars[round(s["size"], 1)] += len(s["text"].strip())
        body = size_chars.most_common(1)[0][0] if size_chars else 10.0

        # Heading levels: distinct "large" sizes ranked descending; bold body-size lines go one below.
        heading_sizes = sorted({sz for sz, c in size_chars.items() if sz >= body * 1.15 and c > 0}, reverse=True)
        level_of = {sz: i + 1 for i, sz in enumerate(heading_sizes[:5])}
        bold_level = min(len(level_of) + 1, 6)

        pages: list[ParsedPage] = []
        elements: list[ParsedElement] = []
        fonts_used: Counter = Counter()

        for pno, page in enumerate(doc):
            num = pno + 1
            rect = page.rect
            pix = page.get_pixmap(dpi=RENDER_DPI)
            pages.append(ParsedPage(page=num, width=rect.width, height=rect.height, render=pix.tobytes("png")))
            d = page_dicts[pno]
            page_elements: list[tuple[float, ParsedElement]] = []  # (y, element) for non-text inserts
            text_elements: list[ParsedElement] = []

            # Tables
            table_boxes = []
            try:
                tables = page.find_tables().tables if self.filetype == "pdf" else []
            except Exception:  # noqa: BLE001 - table detection is best effort
                tables = []
            for t in tables:
                rows = _extract_table(page, t)
                if len(rows) < 2 or max(len(r) for r in rows) < 2:
                    continue
                md = _table_markdown(rows)
                if md:
                    table_boxes.append(tuple(t.bbox))
                    page_elements.append((t.bbox[1], ParsedElement(
                        TABLE, md, num, tuple(t.bbox), meta={"rows": [[c or "" for c in r] for r in rows]})))

            all_line_boxes = [tuple(ln["bbox"]) for blk in d["blocks"] for ln in blk.get("lines", [])
                              if "".join(s["text"] for s in ln["spans"]).strip()]

            # Text and image blocks
            for block in d["blocks"]:
                if block["type"] == 1:  # image
                    w, h = block.get("width", 0), block.get("height", 0)
                    if w < MIN_IMAGE_PX or h < MIN_IMAGE_PX:
                        continue
                    bx = tuple(block["bbox"])
                    if (bx[2] - bx[0]) * (bx[3] - bx[1]) > 0.97 * rect.width * rect.height:
                        meta = {"full_page": True}
                    else:
                        meta = {}
                    meta.update({"width_px": w, "height_px": h})
                    page_elements.append((bx[1], ParsedElement(
                        IMAGE, "", num, bx, meta=meta, image=block["image"], image_ext=block.get("ext", "png"))))
                    continue

                lines = [self._line_info(ln) for ln in _merge_baselines(block.get("lines", []))]
                lines = [ln for ln in lines if ln["text"] and not any(_inside(ln["bbox"], tb) for tb in table_boxes)]
                if not lines:
                    continue
                single_line_block = len(lines) == 1
                current: ParsedElement | None = None

                def flush():
                    nonlocal current
                    if current is not None and current.text.strip():
                        current.text = re.sub(r"\s+", " ", current.text).strip()
                        text_elements.append(current)
                    current = None

                for ln in lines:
                    for s in ln["spans"]:
                        fonts_used[_clean_font(s["font"])] += len(s["text"])
                    text = ln["text"]
                    is_big = ln["size"] >= body * 1.15 and len(text) <= 120
                    is_bold_heading = (ln["bold"] and single_line_block and len(text) <= 80
                                       and not text.endswith((".", ",", ";", ":")) and ln["size"] >= body * 0.95
                                       and not BULLET_RE.match(text)
                                       and not _side_by_side(tuple(ln["bbox"]), all_line_boxes))
                    if is_big or is_bold_heading:
                        level = level_of.get(ln["size"], bold_level) if is_big else bold_level
                        # Merge multi-line headings of the same size
                        if current is not None and current.type == HEADING and current.level == level:
                            current.text += " " + text
                            current.bbox = _union(current.bbox, ln["bbox"])
                            current.meta["fonts"] += self._fonts(ln["spans"])
                            continue
                        flush()
                        current = ParsedElement(HEADING, text, num, tuple(ln["bbox"]), level=level,
                                                meta={"fonts": self._fonts(ln["spans"]), "size": ln["size"]})
                        continue
                    if BULLET_RE.match(text):
                        flush()
                        current = ParsedElement(LIST_ITEM, BULLET_RE.sub("", text, count=1), num, tuple(ln["bbox"]),
                                                meta={"fonts": self._fonts(ln["spans"]), "marker": text.split()[0]})
                        continue
                    if current is not None and current.type in (PARAGRAPH, LIST_ITEM):
                        joiner = "" if current.text.endswith("-") else " "
                        current.text = (current.text[:-1] if joiner == "" else current.text) + joiner + text
                        current.bbox = _union(current.bbox, ln["bbox"])
                        current.meta["fonts"] = _merge_fonts(current.meta["fonts"], self._fonts(ln["spans"]))
                    else:
                        flush()
                        current = ParsedElement(PARAGRAPH, text, num, tuple(ln["bbox"]),
                                                meta={"fonts": self._fonts(ln["spans"])})
                flush()

            # Vector swatches (filled rectangles that are not page backgrounds)
            seen_rects = set()
            for path in page.get_drawings():
                fill = path.get("fill")
                r = path.get("rect")
                if fill is None or r is None:
                    continue
                w, h = r.width, r.height
                if w < MIN_SWATCH_PT or h < MIN_SWATCH_PT:
                    continue
                if w * h > 0.5 * rect.width * rect.height:
                    continue
                kinds = {it[0] for it in path.get("items", [])}
                if not kinds or not kinds <= {"re", "qu", "c", "l"}:
                    continue
                key = (round(r.x0), round(r.y0), round(r.x1), round(r.y1), _hex(fill))
                if key in seen_rects:
                    continue
                seen_rects.add(key)
                page_elements.append((r.y0, ParsedElement(
                    SWATCH, "", num, (r.x0, r.y0, r.x1, r.y1),
                    meta={"fill": _hex(fill), "opacity": path.get("fill_opacity", 1.0),
                          "rounded": "c" in kinds})))

            # OCR scanned pages
            text_chars = sum(len(e.text) for e in text_elements)
            if text_chars < 25 and ocr_available():
                hi = page.get_pixmap(dpi=OCR_DPI).tobytes("png")
                scale = 72 / OCR_DPI
                for ln in ocr_image(hi) or []:
                    b = tuple(v * scale for v in ln["bbox"])
                    text_elements.append(ParsedElement(PARAGRAPH, ln["text"], num, b,
                                                       meta={"ocr": True, "ocr_conf": ln["conf"]}))

            elements.extend(_interleave(text_elements, page_elements))
            progress((pno + 1) / n, f"Page {num} of {n}")

        # OCR text embedded in sizeable images
        if ocr_available():
            for el in elements:
                if el.type == IMAGE and el.image and el.meta.get("width_px", 0) * el.meta.get("height_px", 0) > 200 * 80:
                    lines = ocr_image(el.image)
                    if lines:
                        el.meta["ocr_text"] = " ".join(ln["text"] for ln in lines)[:4000]

        title = (doc.metadata or {}).get("title") or next(
            (e.text for e in elements if e.type == HEADING and e.level == 1), None)
        embedded = sorted({_clean_font(f[3]) for p in range(n) for f in doc.get_page_fonts(p)})
        return ParsedDocument(
            parser=f"{self.name}-{pymupdf.VersionBind}",
            title=title,
            pages=pages,
            elements=elements,
            meta={"body_font_size": body, "embedded_fonts": embedded,
                  "font_usage": dict(fonts_used.most_common(20)), "pdf_metadata": doc.metadata or {}},
        )


def _union(a, b):
    if a is None:
        return tuple(b)
    return (min(a[0], b[0]), min(a[1], b[1]), max(a[2], b[2]), max(a[3], b[3]))


def _merge_fonts(a: list[dict], b: list[dict]) -> list[dict]:
    keys = {(f["font"], f["size"], f["bold"], f["color"]) for f in a}
    return a + [f for f in b if (f["font"], f["size"], f["bold"], f["color"]) not in keys]


def _interleave(text: list[ParsedElement], others: list[tuple[float, ParsedElement]]) -> list[ParsedElement]:
    """Insert tables/images/swatches into the text stream by vertical position."""
    others = sorted(others, key=lambda t: (t[0], t[1].bbox[0] if t[1].bbox else 0))
    out: list[ParsedElement] = []
    i = 0
    for el in text:
        y = el.bbox[1] if el.bbox else 0
        while i < len(others) and others[i][0] < y - 1:
            out.append(others[i][1])
            i += 1
        out.append(el)
    out.extend(o for _, o in others[i:])
    return out
