"""RFI Contradiction-Checker (Component 5).

``reader`` surfaces the subject's RFI read-only (Phase 1); ``claims`` decomposes
the response under review into discrete, testable assertions (Phase 5).
"""

from __future__ import annotations

from .claims import (
    MIN_ALIGNMENT,
    ExtractedClaim,
    RfiDecomposition,
    decompose,
    split_sentences,
)
from .reader import RfiClaim, RfiView, load_rfi

__all__ = [
    "RfiClaim", "RfiView", "load_rfi",
    "ExtractedClaim", "RfiDecomposition", "decompose", "split_sentences",
    "MIN_ALIGNMENT",
]
