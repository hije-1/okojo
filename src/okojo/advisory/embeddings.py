"""Embedding backends behind a small, swappable interface.

Phase 3 is Okojo's first embedding dependency. Two deliberate choices shape this
module (see ``docs/advisory-methodology.md``):

* **Local model, never an API.** Embeddings are computed by a local
  sentence-transformers model (``all-MiniLM-L6-v2``). No network call, no API
  key — the offline / no-secrets / deterministic property is a compliance and
  reproducibility feature, not an accident.
* **Graceful degradation.** If sentence-transformers (torch) isn't installed,
  :class:`LexicalFallbackEmbedder` takes over: a deterministic, dependency-free
  hashed-feature embedder so the pipeline and its eval still run. This mirrors
  the generator's Faker/``_fakelite`` fallback. The fallback flags *lexical*
  resemblance only — it is not a semantic model.

Both backends implement the same tiny :class:`Embedder` interface and return
L2-normalised float32 vectors, so cosine similarity is a plain dot product and a
FAISS/ANN backend could drop in later without touching callers.
"""

from __future__ import annotations

import hashlib
import re
from typing import Protocol, Sequence, runtime_checkable

import numpy as np

_TOKEN_RE = re.compile(r"[a-z0-9]+")

# Pinned local model — see docs/advisory-methodology.md. Small, CPU-friendly,
# widely used; deterministic for a fixed model + input on CPU.
DEFAULT_MODEL = "sentence-transformers/all-MiniLM-L6-v2"


@runtime_checkable
class Embedder(Protocol):
    """Maps texts to L2-normalised vectors. The one seam retrieval depends on."""

    name: str
    dim: int

    def embed(self, texts: Sequence[str]) -> np.ndarray:  # (n, dim) float32
        ...


def _l2_normalize(mat: np.ndarray) -> np.ndarray:
    norms = np.linalg.norm(mat, axis=1, keepdims=True)
    norms[norms == 0] = 1.0
    return (mat / norms).astype(np.float32)


class LexicalFallbackEmbedder:
    """Deterministic, dependency-free embedder (no torch required).

    Hashes word tokens into a fixed-width signed vector, L2-normalised, so cosine
    captures word-level overlap between texts. Word-level (rather than character)
    features are used deliberately: they discriminate a genuine paraphrase of a
    red-flag indicator from a merely topical decoy far more cleanly (shared
    trigrams inflate the baseline similarity of unrelated text). Fully
    deterministic across runs and platforms (uses :mod:`hashlib`, never Python's
    salted ``hash()``). It is a *fallback* that surfaces lexical resemblance —
    not a semantic model; genuine paraphrase/synonymy matching is what the local
    sentence-transformers backend provides when installed.
    """

    name = "lexical-fallback-v1"

    def __init__(self, dim: int = 512):
        self.dim = dim

    def _features(self, text: str) -> list[str]:
        return [f"w:{t}" for t in _TOKEN_RE.findall(text.lower())]

    def embed(self, texts: Sequence[str]) -> np.ndarray:
        vecs = np.zeros((len(texts), self.dim), dtype=np.float32)
        for i, text in enumerate(texts):
            for feat in self._features(text):
                h = int.from_bytes(hashlib.blake2b(feat.encode("utf-8"), digest_size=8).digest(), "big")
                idx = h % self.dim
                sign = 1.0 if (h >> 1) & 1 == 0 else -1.0  # signed hashing damps collisions
                vecs[i, idx] += sign
        return _l2_normalize(vecs)


class SentenceTransformerEmbedder:
    """Local sentence-transformers backend (the intended production path)."""

    def __init__(self, model_name: str = DEFAULT_MODEL):
        from sentence_transformers import SentenceTransformer  # lazy: no torch at import

        self.name = model_name
        self._model = SentenceTransformer(model_name)
        self.dim = int(self._model.get_sentence_embedding_dimension())

    def embed(self, texts: Sequence[str]) -> np.ndarray:
        vecs = self._model.encode(
            list(texts), normalize_embeddings=True, convert_to_numpy=True,
        )
        return np.asarray(vecs, dtype=np.float32)


def get_embedder(prefer_model: bool = True) -> Embedder:
    """Return the local model if available, else the deterministic fallback.

    ``prefer_model=False`` forces the fallback (used by hermetic tests).
    """
    if prefer_model:
        try:
            return SentenceTransformerEmbedder()
        except Exception:
            # sentence-transformers/torch not installed, or model unavailable
            # offline — degrade to the deterministic lexical embedder.
            pass
    return LexicalFallbackEmbedder()
