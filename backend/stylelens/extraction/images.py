"""Image understanding: captions, do/don't classification, dominant colours, and (when a vision model is
configured) a detailed description of what the image shows and which rules it illustrates."""

import io
import logging
import re

from pydantic import BaseModel

from stylelens.extraction.common import El
from stylelens.llm.base import LLMRefusal, LLMUnavailable
from stylelens.llm.client import generate_json, llm_available, model_spec
from stylelens.schema.profile import ImageItem

log = logging.getLogger(__name__)
CAPTION_RE = re.compile(r"^(fig(?:ure)?\.?\s*\d+|do\b|don'?t\b|correct|incorrect|example|✓|✗)", re.I)
DONT_RE = re.compile(r"\b(don'?t|do not|never|incorrect|wrong|avoid|misuse)\b|✗|✘", re.I)
DO_RE = re.compile(r"(^|\W)(do|correct|good|preferred)\b|✓|✔", re.I)
MAX_VLM_IMAGES = 40


class ImageDescription(BaseModel):
    description: str
    kind: str  # logo | photo | illustration | icon | diagram | swatch_sheet | screenshot | other
    example: str  # do | dont | neutral
    rules_depicted: list[str]
    text_in_image: str | None


def find_caption(img: El, elements_by_seq: dict[int, El]) -> str | None:
    for offset in (1, 2, -1):
        el = elements_by_seq.get(img.seq + offset)
        if el is None or el.page != img.page or el.type not in ("paragraph", "caption"):
            continue
        if len(el.text) > 220:
            continue
        if CAPTION_RE.match(el.text) or (img.bbox and el.bbox and 0 <= el.bbox[1] - img.bbox[3] <= 30):
            return el.text
    return None


def heuristic_kind(section: str, caption: str, ocr: str) -> str:
    s = f"{section} {caption}".lower()
    if "logo" in s or "wordmark" in s or "monogram" in s:
        return "logo"
    if re.search(r"photo|imagery|photograph", s):
        return "photo"
    if re.search(r"icon", s):
        return "icon"
    if re.search(r"illustrat", s):
        return "illustration"
    if re.search(r"palette|colou?r", s):
        return "swatch_sheet"
    if len(ocr) > 120:
        return "screenshot"
    return "other"


def _png(data: bytes) -> tuple[bytes, str]:
    from PIL import Image

    img = Image.open(io.BytesIO(data))
    if img.format in ("PNG", "JPEG", "WEBP", "GIF") and max(img.size) <= 1568:
        return data, f"image/{img.format.lower().replace('jpg', 'jpeg')}"
    img = img.convert("RGB")
    img.thumbnail((1568, 1568))
    buf = io.BytesIO()
    img.save(buf, "PNG")
    return buf.getvalue(), "image/png"


async def extract_images(elements: list[El], images: dict[str, bytes], palettes: dict[str, list[str]],
                         title: str | None, warnings: list[str]) -> list[ImageItem]:
    by_seq = {e.seq: e for e in elements}
    use_vlm = llm_available("vision")
    items: list[ImageItem] = []
    for n, el in enumerate(e for e in elements if e.type == "image" and e.image_key):
        caption = find_caption(el, by_seq)
        ocr = el.meta.get("ocr_text", "") or ""
        cue = f"{caption or ''} {el.section}"
        example = "dont" if DONT_RE.search(cue) else "do" if caption and DO_RE.search(caption) else "neutral"
        item = ImageItem(
            id=f"image-{n + 1}", element_id=el.id, page=el.page, bbox=el.bbox,
            image_url=f"/assets/{el.image_key}", kind=heuristic_kind(el.section, caption or "", ocr),
            example=example, caption=caption, dominant_colors=palettes.get(el.id, []),
            text_in_image=ocr or None,
            description=caption or (f"Image in {el.heading_path[-1]}" if el.heading_path else "Image"),
        )
        if use_vlm and n < MAX_VLM_IMAGES and el.image_key in images:
            try:
                data, media = _png(images[el.image_key])
                d = await generate_json(
                    "vision", "describe_image", ImageDescription, images=[(data, media)],
                    guide_title=title or "Untitled guide", section_path=el.section or "(none)",
                    caption=caption or "(none)", ocr_text=ocr[:1500] or "(none)",
                )
                item.description = d.description
                item.kind = d.kind or item.kind
                item.example = d.example if d.example in ("do", "dont", "neutral") else item.example
                item.rules_depicted = d.rules_depicted[:6]
                item.text_in_image = d.text_in_image or item.text_in_image
                item.described_by = model_spec("vision")
            except (LLMUnavailable, LLMRefusal, ValueError) as exc:
                warnings.append(f"Image {el.id}: vision description unavailable ({exc})")
        items.append(item)
    return items
