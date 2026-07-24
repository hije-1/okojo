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
from .checkers import CHECKERS, SOURCE_KEYS, Rebuttal, run_checkers
from .contradiction import (
    CONTRADICTION_VERSION,
    MIN_CORROBORATING_SOURCES,
    STRONG_REBUTTAL,
    VERDICTS,
    ClaimAdjudication,
    ContradictionTable,
    adjudicate_claim,
    check_contradictions,
    contradiction_config,
)
from .reader import RfiClaim, RfiView, load_rfi

__all__ = [
    "RfiClaim", "RfiView", "load_rfi",
    "ExtractedClaim", "RfiDecomposition", "decompose", "split_sentences",
    "MIN_ALIGNMENT",
    "Rebuttal", "run_checkers", "CHECKERS", "SOURCE_KEYS",
    "ClaimAdjudication", "ContradictionTable", "check_contradictions",
    "adjudicate_claim", "contradiction_config", "CONTRADICTION_VERSION",
    "STRONG_REBUTTAL", "MIN_CORROBORATING_SOURCES", "VERDICTS",
]
