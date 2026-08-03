"""Subject-as-seed designation check (v1.1) — case-side mirror of the sweep.

Read-only composition of existing sweep/geo/identity/agency machinery; writes to
no chain and introduces no new versioned policy. See ``check.py`` and
``docs/designation-check-methodology.md``.
"""

from __future__ import annotations

from .check import (
    BADGE_CORROBORATED,
    BADGE_NO_MATCH,
    BADGE_POSSIBLE,
    CORROBORATED,
    DISMISSED,
    POSSIBLE,
    CounterpartyStateLine,
    CoverageStatement,
    DesignationCheckResult,
    DesignationMeta,
    DismissalLine,
    FlowExposureLine,
    NetworkNotice,
    PartyHit,
    TerritoryLine,
    compute_badge,
    run_designation_check,
)

__all__ = [
    "run_designation_check",
    "compute_badge",
    "DesignationCheckResult",
    "DesignationMeta",
    "PartyHit",
    "DismissalLine",
    "FlowExposureLine",
    "CounterpartyStateLine",
    "TerritoryLine",
    "NetworkNotice",
    "CoverageStatement",
    "BADGE_NO_MATCH",
    "BADGE_POSSIBLE",
    "BADGE_CORROBORATED",
    "CORROBORATED",
    "POSSIBLE",
    "DISMISSED",
]
