"""Embedding and reranking models, selected by config.

EMBEDDING_MODEL:  "local:<hf id>"  sentence-transformers model (default BAAI/bge-m3)
                  "hash:<dim>"     deterministic feature-hashing embedder (tests / offline only)
RERANKER_MODEL:   "local:<hf id>"  cross-encoder (default BAAI/bge-reranker-v2-m3)
                  "lexical"        token-overlap scorer (tests / offline only)
                  "none"           keep fusion order
"""

import asyncio
import hashlib
import math
import os
import re
import threading
from functools import lru_cache
from typing import Protocol

import numpy as np

from stylelens.config import get_settings

_TOKEN_RE = re.compile(r"[a-z0-9#]+")
_STOP = frozenset("a an and are as at be by can do does for from how i in is it its of on or our should that "
                  "the this to us we what when where which who why will with you your".split())


def tokens(text: str) -> list[str]:
    return [t for t in _TOKEN_RE.findall(text.lower()) if t not in _STOP and len(t) > 1]


def _stem(t: str) -> str:
    for suf in ("ing", "ies", "es", "ed", "s"):
        if len(t) > len(suf) + 3 and t.endswith(suf):
            return t[: -len(suf)] + ("y" if suf == "ies" else "")
    return t


class Embedder(Protocol):
    name: str
    dim: int

    def embed(self, texts: list[str], *, query: bool = False) -> np.ndarray: ...


class HashEmbedder:
    """Signed feature hashing of stemmed unigrams + bigrams. Deterministic; lexical only."""

    def __init__(self, dim: int):
        self.dim = dim
        self.name = f"hash:{dim}"

    def embed(self, texts, *, query=False):
        out = np.zeros((len(texts), self.dim), dtype=np.float32)
        for i, text in enumerate(texts):
            toks = [_stem(t) for t in tokens(text)]
            feats = toks + [f"{a}_{b}" for a, b in zip(toks, toks[1:], strict=False)]
            for f in feats:
                h = int.from_bytes(hashlib.blake2b(f.encode(), digest_size=8).digest(), "little")
                out[i, h % self.dim] += 1.0 if (h >> 63) & 1 else -1.0
            n = np.linalg.norm(out[i])
            if n:
                out[i] /= n
        return out


def _require_st():
    try:
        import sentence_transformers  # noqa: F401
    except ImportError as exc:
        raise RuntimeError(
            "Local embedding/reranking models need the ML extra: pip install '.[ml]' "
            "(or set EMBEDDING_MODEL=hash:1024 RERANKER_MODEL=lexical for offline testing)") from exc


class SentenceTransformerEmbedder:
    def __init__(self, model_id: str, dim: int):
        _require_st()
        from sentence_transformers import SentenceTransformer

        self.model = SentenceTransformer(model_id, device="cpu")
        self.name = f"local:{model_id}"
        self.dim = self.model.get_sentence_embedding_dimension() or dim
        self._lock = threading.Lock()

    def embed(self, texts, *, query=False):
        with self._lock:
            return self.model.encode(texts, batch_size=16, normalize_embeddings=True, show_progress_bar=False,
                                     convert_to_numpy=True).astype(np.float32)


class Reranker(Protocol):
    name: str
    default_threshold: float

    def score(self, query: str, passages: list[str]) -> list[float]: ...


class LexicalReranker:
    """Soft token-overlap score in [0, 1] (stemmed recall of query terms, weighted by IDF-ish length)."""

    name = "lexical"
    default_threshold = 0.3

    def score(self, query, passages):
        q = {_stem(t) for t in tokens(query)}
        if not q:
            return [0.0] * len(passages)
        out = []
        for p in passages:
            pt = {_stem(t) for t in tokens(p)}

            def match(t: str) -> bool:
                # exact stem, or a long shared prefix ("small"~"smaller", "photography"~"photographic")
                if t in pt:
                    return True
                if len(t) < 4:
                    return False
                for x in pt:
                    if len(x) < 4:
                        continue
                    n = len(os.path.commonprefix((t, x)))
                    if n >= max(4, 0.75 * min(len(t), len(x))):
                        return True
                return False

            hit = sum(1 + min(len(t), 10) / 10 for t in q if match(t))
            total = sum(1 + min(len(t), 10) / 10 for t in q)
            out.append(round(hit / total, 6))
        return out


class CrossEncoderReranker:
    default_threshold = 0.15

    def __init__(self, model_id: str):
        _require_st()
        from sentence_transformers import CrossEncoder

        self.model = CrossEncoder(model_id, device="cpu", max_length=512)
        self.name = f"local:{model_id}"
        self._lock = threading.Lock()

    def score(self, query, passages):
        if not passages:
            return []
        with self._lock:
            raw = self.model.predict([(query, p) for p in passages], batch_size=16, show_progress_bar=False)
        vals = [float(x) for x in np.asarray(raw).reshape(-1)]
        # Normalise logits to probabilities if the model returned unbounded scores
        if any(v < 0 or v > 1 for v in vals):
            vals = [1 / (1 + math.exp(-v)) for v in vals]
        return [round(v, 6) for v in vals]


class NoReranker:
    name = "none"
    default_threshold = 0.0

    def score(self, query, passages):
        return [1.0] * len(passages)


@lru_cache
def get_embedder() -> Embedder:
    s = get_settings()
    kind, _, arg = s.embedding_model.partition(":")
    if kind == "hash":
        return HashEmbedder(int(arg or s.embedding_dim))
    if kind == "local":
        emb = SentenceTransformerEmbedder(arg, s.embedding_dim)
        if emb.dim != s.embedding_dim:
            raise ValueError(f"{arg} produces {emb.dim}-d vectors but EMBEDDING_DIM={s.embedding_dim}")
        return emb
    raise ValueError(f"Unknown EMBEDDING_MODEL '{s.embedding_model}'")


@lru_cache
def get_reranker() -> Reranker:
    spec = get_settings().reranker_model
    kind, _, arg = spec.partition(":")
    if kind == "lexical":
        return LexicalReranker()
    if kind == "none":
        return NoReranker()
    if kind == "local":
        return CrossEncoderReranker(arg)
    raise ValueError(f"Unknown RERANKER_MODEL '{spec}'")


async def aembed(texts: list[str], *, query: bool = False) -> np.ndarray:
    return await asyncio.to_thread(get_embedder().embed, texts, query=query)


async def arerank(query: str, passages: list[str]) -> list[float]:
    return await asyncio.to_thread(get_reranker().score, query, passages)
