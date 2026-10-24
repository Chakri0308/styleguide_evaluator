"""Image helpers shared by visual-rule extraction and visual comparison.

Vision models report regions as `box_2d = [ymin, xmin, ymax, xmax]` normalised to 0-1000 (Gemini's
native convention, also followed reliably by Claude). Internally regions are page-point bboxes
`[x0, y0, x1, y1]`, the same space as element bboxes, so highlights line up in the source viewer.
"""

import io

from PIL import Image, ImageDraw

MAX_SIDE = 1568


def box_to_bbox(box: list[float], frame: list[float]) -> list[float] | None:
    """0-1000 [ymin, xmin, ymax, xmax] inside `frame` ([x0, y0, x1, y1] in page points) → page bbox."""
    if len(box) != 4:
        return None
    ymin, xmin, ymax, xmax = (min(max(float(v), 0.0), 1000.0) for v in box)
    if xmax <= xmin or ymax <= ymin:
        return None
    fx0, fy0, fx1, fy1 = frame
    w, h = fx1 - fx0, fy1 - fy0
    return [round(fx0 + xmin / 1000 * w, 1), round(fy0 + ymin / 1000 * h, 1),
            round(fx0 + xmax / 1000 * w, 1), round(fy0 + ymax / 1000 * h, 1)]


def to_png(img: Image.Image, max_side: int = MAX_SIDE) -> bytes:
    img = img.convert("RGB")
    if max(img.size) > max_side:
        img.thumbnail((max_side, max_side))
    buf = io.BytesIO()
    img.save(buf, "PNG", optimize=True)
    return buf.getvalue()


def crop(render: bytes, frame: list[float], bbox: list[float], *, pad: float = 0.12, min_frac: float = 0.25,
         mark: bool = False, max_side: int = MAX_SIDE) -> bytes:
    """Crop `bbox` (page points) out of an image covering `frame` (page points), padded so the crop keeps
    context (clear space lives *around* the subject) and at least `min_frac` of the frame. With `mark`,
    the bbox itself is outlined in red."""
    img = Image.open(io.BytesIO(render)).convert("RGB")
    fx0, fy0, fx1, fy1 = frame
    sx, sy = img.width / max(fx1 - fx0, 1e-6), img.height / max(fy1 - fy0, 1e-6)
    x0, y0, x1, y1 = ((bbox[0] - fx0) * sx, (bbox[1] - fy0) * sy, (bbox[2] - fx0) * sx, (bbox[3] - fy0) * sy)
    w, h = x1 - x0, y1 - y0
    cw = max(w * (1 + 2 * pad), img.width * min_frac)
    ch = max(h * (1 + 2 * pad), img.height * min_frac)
    cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
    left, top = max(0, cx - cw / 2), max(0, cy - ch / 2)
    right, bottom = min(img.width, cx + cw / 2), min(img.height, cy + ch / 2)
    if mark:
        d = ImageDraw.Draw(img)
        lw = max(2, round(max(img.size) / 300))
        d.rectangle([x0, y0, x1, y1], outline=(225, 29, 72), width=lw)
    out = img.crop((round(left), round(top), round(right), round(bottom)))
    # Upscale small crops so fine detail (dimension marks, thin rules) stays legible to the model
    if max(out.size) < 768:
        f = 768 / max(out.size)
        out = out.resize((round(out.width * f), round(out.height * f)), Image.LANCZOS)
    return to_png(out, max_side)


def shrink(render: bytes, max_side: int = MAX_SIDE) -> bytes:
    return to_png(Image.open(io.BytesIO(render)), max_side)


def overlap(a: list[float] | None, b: list[float] | None) -> float:
    """Intersection area / area of `a`."""
    if not a or not b:
        return 0.0
    ix = max(0.0, min(a[2], b[2]) - max(a[0], b[0]))
    iy = max(0.0, min(a[3], b[3]) - max(a[1], b[1]))
    area = max((a[2] - a[0]) * (a[3] - a[1]), 1e-6)
    return ix * iy / area
