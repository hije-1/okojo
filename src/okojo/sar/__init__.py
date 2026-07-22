"""SAR Drafter — grounded, template-first narrative assembly (Component 7, Phase 1 slice)."""

from __future__ import annotations

from .drafter import build_sar
from .schema import (
    BANNED_TERMS,
    SarClaim,
    SarDraft,
    UngroundedClaimError,
    assert_grounded,
    calibration_violations,
)

__all__ = [
    "build_sar", "SarClaim", "SarDraft", "UngroundedClaimError",
    "assert_grounded", "calibration_violations", "BANNED_TERMS",
]
