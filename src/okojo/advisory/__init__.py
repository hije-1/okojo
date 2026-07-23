"""Regulatory Advisory Matcher — hybrid retrieval + corroboration (Component 6)."""

from __future__ import annotations

from .matcher import (
    RETRIEVAL_VERSION,
    SEMANTIC_THRESHOLD,
    SEMANTIC_TOP_K,
    Advisory,
    AdvisoryMatch,
    Corroborator,
    JurisdictionSignal,
    RedFlag,
    SemanticIndicator,
    StructuredContext,
    build_advisory_retriever,
    build_structured_context,
    load_advisories,
    load_advisory,
    match_advisories,
    match_advisory,
    retrieval_config,
)
from .retrieval import CosineRetriever

__all__ = [
    "RETRIEVAL_VERSION",
    "SEMANTIC_THRESHOLD",
    "SEMANTIC_TOP_K",
    "Advisory",
    "AdvisoryMatch",
    "Corroborator",
    "JurisdictionSignal",
    "RedFlag",
    "SemanticIndicator",
    "StructuredContext",
    "CosineRetriever",
    "build_advisory_retriever",
    "build_structured_context",
    "load_advisories",
    "load_advisory",
    "match_advisories",
    "match_advisory",
    "retrieval_config",
]
