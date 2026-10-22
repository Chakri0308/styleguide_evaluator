"""Image embeddings for visual similarity (logo / imagery comparison)."""

import io
import logging
import threading
from functools import lru_cache

import numpy as np

from stylelens.config import get_settings

log = logging.getLogger(__name__)


class HistogramImageEmbedder:
    """Deterministic 3-D colour histogram in Lab space (4×6×6 bins), L2-normalised. Captures palette and
    "busyness" rather than semantics — adequate for tests and offline use."""

    name = "hist"

    def embed(self, images: list[bytes]) -> np.ndarray:
        from PIL import Image

        from stylelens.colors import rgb_array_to_lab

        out = []
        for data in images:
            img = Image.open(io.BytesIO(data)).convert("RGB")
            img.thumbnail((96, 96))
            lab = rgb_array_to_lab(np.asarray(img).reshape(-1, 3))
            h, _ = np.histogramdd(lab, bins=(4, 6, 6), range=((0, 100), (-80, 80), (-80, 80)))
            v = np.sqrt(h.reshape(-1))  # Hellinger-style
            n = np.linalg.norm(v)
            out.append(v / n if n else v)
        return np.asarray(out, dtype=np.float32)


class ClipImageEmbedder:
    def __init__(self, model_id: str):
        from sentence_transformers import SentenceTransformer

        self.model = SentenceTransformer(model_id, device="cpu")
        self.name = f"local:{model_id}"
        self._lock = threading.Lock()

    def embed(self, images: list[bytes]) -> np.ndarray:
        from PIL import Image

        pil = [Image.open(io.BytesIO(d)).convert("RGB") for d in images]
        with self._lock:
            return self.model.encode(pil, normalize_embeddings=True, convert_to_numpy=True).astype(np.float32)


@lru_cache
def get_image_embedder():
    spec = get_settings().image_embedding_model
    kind, _, arg = spec.partition(":")
    if kind == "none":
        return None
    if kind == "hist":
        return HistogramImageEmbedder()
    if kind == "local":
        try:
            return ClipImageEmbedder(arg)
        except Exception as exc:  # noqa: BLE001 - model unavailable offline: degrade gracefully
            log.warning("image embedding model %s unavailable (%s); falling back to colour histograms", arg, exc)
            return HistogramImageEmbedder()
    raise ValueError(f"Unknown IMAGE_EMBEDDING_MODEL '{spec}'")
