"""Semantic retrieval seam — exact in-memory cosine over an embedded corpus.

The advisory corpus is tiny (a handful of advisories, each a few dozen terms and
~15 red-flag indicators = dozens to low-hundreds of chunks). At that scale an
exact brute-force cosine search is the right-sized choice: it is *exact* and
fully deterministic, adds no vector-DB dependency, persistence, or secrets, and
preserves the project's reproducibility guarantee. A vector DB (FAISS/Chroma)
would add weight for no benefit here, and Chroma's default approximate (HNSW)
search would undercut determinism.

**Upgrade path:** if the corpus ever grows (e.g. real datasets), swapping in
FAISS ``IndexFlatIP`` is an isolated change behind this same
:class:`CosineRetriever` interface — callers index and query, never touching the
backend. See ``docs/advisory-methodology.md``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional, Sequence

import numpy as np

from .embeddings import Embedder, get_embedder


@dataclass
class RetrievedItem:
    """One corpus item and its cosine similarity to the query (0–1 for
    non-negative embeddings; up to [-1, 1] for signed vectors)."""

    score: float
    text: str
    metadata: dict = field(default_factory=dict)


class CosineRetriever:
    """Exact cosine search over a fixed document set (brute force, deterministic).

    Both the corpus and the query are embedded to L2-normalised vectors, so
    cosine similarity is a matrix–vector dot product. Ties are broken by original
    corpus order (stable sort) for reproducibility.
    """

    def __init__(self, embedder: Optional[Embedder] = None):
        self.embedder = embedder or get_embedder()
        self._texts: list[str] = []
        self._meta: list[dict] = []
        self._matrix: Optional[np.ndarray] = None

    def index(self, items: Sequence[tuple[str, dict]]) -> "CosineRetriever":
        """Embed and store ``(text, metadata)`` items. Returns self for chaining."""
        self._texts = [t for t, _ in items]
        self._meta = [m for _, m in items]
        if self._texts:
            self._matrix = self.embedder.embed(self._texts)
        else:
            self._matrix = np.zeros((0, self.embedder.dim), dtype=np.float32)
        return self

    def query(
        self, text: str, top_k: int = 5, min_score: float = 0.0,
    ) -> list[RetrievedItem]:
        """Return up to ``top_k`` items with cosine >= ``min_score``, best first."""
        if self._matrix is None or len(self._texts) == 0:
            return []
        q = self.embedder.embed([text])[0]
        sims = self._matrix @ q  # both normalised -> cosine
        order = np.argsort(-sims, kind="stable")  # deterministic tie order
        out: list[RetrievedItem] = []
        for i in order:
            s = float(sims[i])
            if s < min_score:
                continue
            out.append(RetrievedItem(score=round(s, 4), text=self._texts[i], metadata=self._meta[i]))
            if len(out) >= top_k:
                break
        return out
