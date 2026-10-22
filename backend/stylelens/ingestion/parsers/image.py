"""Raster image parser: the image is one page; OCR lines become positioned paragraphs."""

import io

from PIL import Image

from stylelens.ingestion.ocr import ocr_image
from stylelens.ingestion.parsers.base import IMAGE, PARAGRAPH, ParsedDocument, ParsedElement, ParsedPage, ProgressFn


class ImageParser:
    name = "pillow"

    def parse(self, data: bytes, filename: str, progress: ProgressFn) -> ParsedDocument:
        img = Image.open(io.BytesIO(data))
        img.load()
        if img.mode not in ("RGB", "RGBA"):
            img = img.convert("RGBA" if "A" in img.getbands() else "RGB")
        buf = io.BytesIO()
        img.save(buf, "PNG")
        png = buf.getvalue()
        w, h = img.size
        elements = [ParsedElement(IMAGE, "", 1, (0, 0, w, h), meta={"width_px": w, "height_px": h, "full_page": True},
                                  image=png, image_ext="png")]
        progress(0.5, "Running OCR")
        lines = ocr_image(png) or []
        if lines:
            elements[0].meta["ocr_text"] = " ".join(ln["text"] for ln in lines)[:4000]
        for ln in lines:
            elements.append(ParsedElement(PARAGRAPH, ln["text"], 1, tuple(ln["bbox"]),
                                          meta={"ocr": True, "ocr_conf": ln["conf"]}))
        progress(1.0, "Done")
        return ParsedDocument(parser=self.name, title=None, pages=[ParsedPage(1, float(w), float(h), render=png)],
                              elements=elements, meta={"pixel_size": [w, h]})
