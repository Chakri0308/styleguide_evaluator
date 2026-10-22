"""Optional OCR via Tesseract. Returns None when Tesseract is unavailable."""

import io
import logging
import shutil

log = logging.getLogger(__name__)


def ocr_available() -> bool:
    if shutil.which("tesseract") is None:
        return False
    try:
        import pytesseract  # noqa: F401
    except ImportError:
        return False
    return True


def ocr_image(data: bytes) -> list[dict] | None:
    """OCR an image; returns text lines with pixel bboxes: [{text, bbox:(x0,y0,x1,y1), conf}]."""
    if not ocr_available():
        return None
    import pytesseract
    from PIL import Image

    try:
        img = Image.open(io.BytesIO(data)).convert("RGB")
        d = pytesseract.image_to_data(img, output_type=pytesseract.Output.DICT)
    except Exception as exc:  # noqa: BLE001
        log.warning("OCR failed: %s", exc)
        return None
    lines: dict[tuple, dict] = {}
    for i, word in enumerate(d["text"]):
        word = word.strip()
        conf = float(d["conf"][i])
        if not word or conf < 40:
            continue
        key = (d["block_num"][i], d["par_num"][i], d["line_num"][i])
        x, y, w, h = d["left"][i], d["top"][i], d["width"][i], d["height"][i]
        line = lines.setdefault(key, {"words": [], "bbox": [x, y, x + w, y + h], "conf": []})
        line["words"].append(word)
        line["conf"].append(conf)
        b = line["bbox"]
        line["bbox"] = [min(b[0], x), min(b[1], y), max(b[2], x + w), max(b[3], y + h)]
    return [
        {"text": " ".join(v["words"]), "bbox": tuple(v["bbox"]), "conf": sum(v["conf"]) / len(v["conf"])}
        for _, v in sorted(lines.items())
    ]
