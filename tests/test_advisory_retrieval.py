"""Embedder + retriever seam — deterministic, swappable, degrades gracefully."""

from __future__ import annotations

import numpy as np
import pytest

from okojo.advisory.embeddings import (
    Embedder,
    LexicalFallbackEmbedder,
    SentenceTransformerEmbedder,
    get_embedder,
)
from okojo.advisory.retrieval import CosineRetriever

_DOCS = [
    ("crude oil and petroleum shipment settlement via a front company", {"id": "A"}),
    ("bitumen cargo financed through a shadow-banking intermediary", {"id": "B"}),
    ("quarterly payroll for the marketing team", {"id": "C"}),
]


def test_fallback_embeddings_are_normalised_and_deterministic():
    emb = LexicalFallbackEmbedder()
    m1 = emb.embed([d for d, _ in _DOCS])
    m2 = emb.embed([d for d, _ in _DOCS])
    assert m1.shape == (3, emb.dim)
    # every row is unit length (or zero, guarded) and byte-identical across runs
    norms = np.linalg.norm(m1, axis=1)
    assert np.allclose(norms, 1.0, atol=1e-5)
    assert np.array_equal(m1, m2)


def test_fallback_satisfies_embedder_protocol():
    assert isinstance(LexicalFallbackEmbedder(), Embedder)


def test_get_embedder_returns_working_embedder():
    # sentence-transformers is optional; whichever backend is returned must work.
    emb = get_embedder()
    v = emb.embed(["hello world"])
    assert v.shape == (1, emb.dim)


def test_get_embedder_force_fallback():
    emb = get_embedder(prefer_model=False)
    assert isinstance(emb, LexicalFallbackEmbedder)


def test_retriever_ranks_self_first():
    r = CosineRetriever(LexicalFallbackEmbedder()).index(_DOCS)
    hits = r.query("crude oil and petroleum shipment settlement via a front company")
    assert hits
    assert hits[0].metadata["id"] == "A"
    assert hits[0].score > 0.99  # self-similarity ~ 1.0


def test_retriever_separates_related_from_unrelated():
    r = CosineRetriever(LexicalFallbackEmbedder()).index(_DOCS)
    hits = {h.metadata["id"]: h.score for h in r.query("oil and petroleum trade", top_k=3)}
    # oil/petroleum docs outscore the payroll decoy
    assert hits.get("A", 0.0) > hits.get("C", 0.0)


def test_retriever_min_score_and_top_k():
    r = CosineRetriever(LexicalFallbackEmbedder()).index(_DOCS)
    assert len(r.query("oil", top_k=1)) <= 1
    # an impossibly high threshold filters everything
    assert r.query("oil", min_score=1.01) == []


def test_retriever_empty_corpus_is_safe():
    r = CosineRetriever(LexicalFallbackEmbedder()).index([])
    assert r.query("anything") == []


def test_sentence_transformer_backend_when_installed():
    pytest.importorskip("sentence_transformers")
    emb = SentenceTransformerEmbedder()
    v = emb.embed(["crude oil shipment", "quarterly payroll"])
    assert v.shape[0] == 2 and v.shape[1] == emb.dim
    norms = np.linalg.norm(v, axis=1)
    assert np.allclose(norms, 1.0, atol=1e-3)
