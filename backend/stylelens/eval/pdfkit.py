"""Tiny PDF authoring helper (PyMuPDF) used to build the sample guides for tests and evals."""

import io

import pymupdf
from PIL import Image, ImageDraw, ImageFilter

PAGE_W, PAGE_H = 612, 792
MARGIN = 56


def hex_rgb(h: str) -> tuple[float, float, float]:
    h = h.lstrip("#")
    return tuple(int(h[i : i + 2], 16) / 255 for i in (0, 2, 4))  # type: ignore[return-value]


class PdfBuilder:
    def __init__(self, title: str, body_font: str = "helv", bold_font: str = "hebo", text_color: str = "#1A1A1A"):
        self.doc = pymupdf.open()
        self.doc.set_metadata({"title": title, "author": "StyleLens sample"})
        self.body_font = body_font
        self.bold_font = bold_font
        self.text_color = hex_rgb(text_color)
        self.page = None
        self.y = 0.0
        self.new_page()

    # -- layout --------------------------------------------------------------------------------
    def new_page(self):
        self.page = self.doc.new_page(width=PAGE_W, height=PAGE_H)
        self.y = MARGIN

    def ensure(self, h: float):
        if self.y + h > PAGE_H - MARGIN:
            self.new_page()

    def space(self, h: float = 8):
        self.y += h

    def _wrap(self, text: str, font: str, size: float, width: float) -> list[str]:
        words, lines, cur = text.split(), [], ""
        for w in words:
            trial = f"{cur} {w}".strip()
            if pymupdf.get_text_length(trial, fontname=font, fontsize=size) <= width:
                cur = trial
            else:
                if cur:
                    lines.append(cur)
                cur = w
        if cur:
            lines.append(cur)
        return lines

    def text(self, text: str, size: float = 10.5, font: str | None = None, color=None, indent: float = 0,
             leading: float = 1.45, width: float | None = None):
        font = font or self.body_font
        text = text.replace("—", " - ").replace("’", "'").replace("“", '"').replace("”", '"')
        width = width or (PAGE_W - 2 * MARGIN - indent)
        lines = self._wrap(text, font, size, width)
        for ln in lines:
            self.ensure(size * leading)
            self.page.insert_text((MARGIN + indent, self.y + size), ln, fontsize=size, fontname=font,
                                  color=color or self.text_color)
            self.y += size * leading

    # -- blocks --------------------------------------------------------------------------------
    def h1(self, text: str):
        self.ensure(70)
        self.space(10)
        self.text(text, size=26, font=self.bold_font, leading=1.2)
        self.space(10)

    def h2(self, text: str):
        self.ensure(50)
        self.space(12)
        self.text(text, size=17, font=self.bold_font, leading=1.25)
        self.space(4)

    def h3(self, text: str):
        self.ensure(36)
        self.space(6)
        self.text(text, size=12.5, font=self.bold_font, leading=1.3)
        self.space(1)

    def p(self, text: str):
        self.text(text)
        self.space(6)

    def bullets(self, items: list[str], marker: str = "•"):
        for it in items:
            it = it.replace("—", " - ")
            lines = self._wrap(it, self.body_font, 10.5, PAGE_W - 2 * MARGIN - 16)
            self.ensure(len(lines) * 15)
            self.page.insert_text((MARGIN, self.y + 10.5), marker, fontsize=10.5, fontname=self.body_font,
                                  color=self.text_color)
            # First line shares the marker baseline so the parser sees "• text"
            self.page.insert_text((MARGIN + 12, self.y + 10.5), lines[0], fontsize=10.5, fontname=self.body_font,
                                  color=self.text_color)
            self.y += 15.2
            for ln in lines[1:]:
                self.page.insert_text((MARGIN + 12, self.y + 10.5), ln, fontsize=10.5, fontname=self.body_font,
                                      color=self.text_color)
                self.y += 15.2
        self.space(6)

    def swatches(self, colors: list[dict]):
        """colors: [{name, hex, rgb, cmyk, pantone, role}] rendered as chips with spec labels."""
        col_w = (PAGE_W - 2 * MARGIN - 3 * 14) / 4
        for i in range(0, len(colors), 4):
            row = colors[i : i + 4]
            self.ensure(150)
            for j, c in enumerate(row):
                x = MARGIN + j * (col_w + 14)
                rect = pymupdf.Rect(x, self.y, x + col_w, self.y + 64)
                self.page.draw_rect(rect, color=None, fill=hex_rgb(c["hex"]), width=0)
                ty = self.y + 78
                self.page.insert_text((x, ty), c["name"], fontsize=10, fontname=self.bold_font, color=self.text_color)
                specs = [f"HEX {c['hex']}"]
                if c.get("rgb"):
                    specs.append(f"RGB {c['rgb']}")
                if c.get("cmyk"):
                    specs.append(f"CMYK {c['cmyk']}")
                if c.get("pantone"):
                    specs.append(f"Pantone {c['pantone']}")
                for k, s in enumerate(specs):
                    self.page.insert_text((x, ty + 13 + k * 11.5), s, fontsize=8, fontname=self.body_font,
                                          color=self.text_color)
            self.y += 78 + 13 + 4 * 11.5 + 12

    def table(self, rows: list[list[str]], col_widths: list[float] | None = None):
        width = PAGE_W - 2 * MARGIN
        n = len(rows[0])
        col_widths = col_widths or [width / n] * n
        row_h = 22
        self.ensure(row_h * len(rows) + 10)
        y0 = self.y
        for r, row in enumerate(rows):
            x = MARGIN
            for c, cell in enumerate(row):
                font = self.bold_font if r == 0 else self.body_font
                self.page.insert_text((x + 6, self.y + 14.5), cell, fontsize=9, fontname=font, color=self.text_color)
                x += col_widths[c]
            self.y += row_h
        # grid lines so table detection works
        line = (0.75, 0.75, 0.75)
        for r in range(len(rows) + 1):
            yy = y0 + r * row_h
            self.page.draw_line((MARGIN, yy), (MARGIN + width, yy), color=line, width=0.6)
        x = MARGIN
        for w in [0] + col_widths:
            x += w
            self.page.draw_line((x, y0), (x, y0 + row_h * len(rows)), color=line, width=0.6)
        self.page.draw_line((MARGIN, y0), (MARGIN, y0 + row_h * len(rows)), color=line, width=0.6)
        self.space(12)

    def image(self, png: bytes, width: float, height: float, caption: str | None = None):
        self.ensure(height + 30)
        rect = pymupdf.Rect(MARGIN, self.y, MARGIN + width, self.y + height)
        self.page.insert_image(rect, stream=png)
        self.y += height + 6
        if caption:
            self.text(caption, size=8.5, color=hex_rgb("#555555"))
        self.space(8)

    def save(self) -> bytes:
        return self.doc.tobytes(garbage=3, deflate=True)


# -- synthetic imagery --------------------------------------------------------------------------
def logo_png(primary: str, accent: str, text_mark: str = "", bg: str | None = None, busy: bool = False,
             size=(480, 200)) -> bytes:
    w, h = size
    img = Image.new("RGB", size, bg or "#FFFFFF")
    d = ImageDraw.Draw(img)
    if busy:
        import random

        rnd = random.Random(7)
        for _ in range(400):
            x, y = rnd.randrange(w), rnd.randrange(h)
            r = rnd.randrange(4, 30)
            d.ellipse((x - r, y - r, x + r, y + r), fill=tuple(rnd.randrange(256) for _ in range(3)))
        img = img.filter(ImageFilter.GaussianBlur(1.5))
        d = ImageDraw.Draw(img)
    d.ellipse((30, 40, 150, 160), fill=primary)
    d.ellipse((70, 80, 110, 120), fill=accent)
    if text_mark:
        d.rectangle((180, 85, 180 + 18 * len(text_mark), 115), fill=primary)
    buf = io.BytesIO()
    img.save(buf, "PNG")
    return buf.getvalue()


def photo_png(top: str, bottom: str, size=(480, 260), people: bool = True) -> bytes:
    w, h = size
    img = Image.new("RGB", size)
    a, b = [tuple(int(c.lstrip("#")[i : i + 2], 16) for i in (0, 2, 4)) for c in (top, bottom)]
    for y in range(h):
        t = y / h
        col = tuple(int(a[k] * (1 - t) + b[k] * t) for k in range(3))
        ImageDraw.Draw(img).line([(0, y), (w, y)], fill=col)
    d = ImageDraw.Draw(img)
    if people:
        for cx in (150, 300):
            d.ellipse((cx - 28, 70, cx + 28, 126), fill="#8D5B3E")
            d.rounded_rectangle((cx - 50, 130, cx + 50, 260), 30, fill="#2E3A59")
    img = img.filter(ImageFilter.GaussianBlur(0.8))
    buf = io.BytesIO()
    img.save(buf, "PNG")
    return buf.getvalue()
