"""SAR Drafter — grounded, template-first narrative assembly (Component 7, Phase 1 slice)."""

from __future__ import annotations

from .critic import (
    CRITIC_THRESHOLD,
    CRITIC_VERSION,
    FINCEN_RUBRIC,
    Critique,
    ElementGrade,
    RubricElement,
    critic_config,
    critique,
)
from .drafter import build_sar, gap_fill_claims
from .loop import MAX_REVISION_ITERATIONS, CritiqueHistory, draft_with_critic
from .schema import (
    BANNED_TERMS,
    SarClaim,
    SarDraft,
    UngroundedClaimError,
    assert_grounded,
    calibration_violations,
)
from .validate import (
    GroundingReport,
    GroundingResolver,
    UnresolvableCitationError,
    assert_resolvable,
    validate_grounding,
)

__all__ = [
    "build_sar", "SarClaim", "SarDraft", "UngroundedClaimError",
    "assert_grounded", "calibration_violations", "BANNED_TERMS",
    "GroundingResolver", "GroundingReport", "UnresolvableCitationError",
    "assert_resolvable", "validate_grounding",
    "FINCEN_RUBRIC", "RubricElement", "ElementGrade", "Critique",
    "critique", "critic_config", "CRITIC_VERSION", "CRITIC_THRESHOLD",
    "draft_with_critic", "CritiqueHistory", "MAX_REVISION_ITERATIONS",
    "gap_fill_claims",
]
