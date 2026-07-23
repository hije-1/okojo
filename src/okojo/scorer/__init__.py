"""On-chain Risk Scorer (Component 3) — graded sanctioned-exposure scoring.

Synthetic address-tagging layer only; never conflated with Elliptic.
"""

from __future__ import annotations

from .scorer import (
    SCORING_VERSION,
    RiskScore,
    RiskScoring,
    ScoreDecomposition,
    score_risk,
    scoring_config,
)

__all__ = [
    "RiskScore",
    "RiskScoring",
    "ScoreDecomposition",
    "score_risk",
    "scoring_config",
    "SCORING_VERSION",
]
