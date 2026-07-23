"""On-chain Risk Scorer (Component 3) — graded sanctioned-exposure scoring.

Synthetic address-tagging layer only; never conflated with Elliptic.
"""

from __future__ import annotations

from .scorer import RiskScore, RiskScoring, score_risk

__all__ = ["RiskScore", "RiskScoring", "score_risk"]
