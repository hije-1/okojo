"""Adjudication — weigh what the checkers found (Phase 5, Slice C).

The checkers gather evidence; this module decides what that evidence supports,
and says so in calibrated language. Four verdicts, deliberately more than two:

* ``contradicted`` — the evidence rebuts the claim. Either one rebuttal at or
  above :data:`STRONG_REBUTTAL`, or corroboration across at least
  :data:`MIN_CORROBORATING_SOURCES` independent evidence surfaces. This mirrors
  the advisory matcher's corroboration gate: a lone weak signal is not enough.
* ``qualified`` — evidence cuts against part of the claim without refuting it.
  A claim that is true as far as it goes but omits material control is not a
  lie, and calling it one would be an over-claim.
* ``uncontested`` — a probe could test the claim and found nothing against it.
* ``unverifiable`` — no probe can test it at all (nothing in the evidence speaks
  to the assertion either way). Distinct from ``uncontested``: silence because
  there is no applicable evidence is not silence because the evidence agrees.

Only ``contradicted`` is a *flag*. Keeping ``qualified`` and ``unverifiable``
separate is what stops the checker inflating its own hit rate.

Confidence is a noisy-OR over the rebuttal strengths: independent evidence
accumulates, but no finite amount of weak evidence reaches certainty. Every
parameter here is versioned via :data:`CONTRADICTION_VERSION`, stamped into the
audit trail, and mirrored (regression-tested) by
``docs/rfi-contradiction-methodology.md``.
"""

from __future__ import annotations

from typing import Optional

from pydantic import BaseModel

from ..connectors import Connectors
from ..entity import EntityBackbone
from .checkers import (
    EXCLUSIVE_CONTROL_TERMS,
    RELATIONSHIP_AFFIRMATION_TERMS,
    RELATIONSHIP_DENIAL_TERMS,
    SOURCE_KEYS,
    SOURCE_OF_FUNDS_TERMS,
    W_DEVICE_SHARED_FINGERPRINT,
    W_ONCHAIN_COUNTERPARTY_FLOW,
    W_ONCHAIN_GAS_FUNDED_HOP,
    W_ONCHAIN_SANCTIONED_EXPOSURE,
    W_ONCHAIN_STRUCTURED,
    W_PRIOR_RFI_SELF_CONTRADICTION,
    W_REGISTRY_COMMON_OFFICER,
    Rebuttal,
    run_checkers,
)
from .claims import RfiDecomposition, decompose

# A single rebuttal at or above this strength carries a claim on its own.
STRONG_REBUTTAL = 0.8

# Otherwise, this many *distinct* evidence surfaces must corroborate.
MIN_CORROBORATING_SOURCES = 2

# Bump on any change to a weight, threshold, lexicon, or verdict rule. Stamped
# into the audit trail and mirrored by the published methodology doc.
CONTRADICTION_VERSION = "1.0.0"

VERDICTS = ("contradicted", "qualified", "uncontested", "unverifiable")


def contradiction_config() -> dict:
    """The full, versioned adjudication policy — the tunable parameters behind
    every verdict. Single source of truth: stamped into the audit trail and
    regression-tested against the published methodology doc."""
    return {
        "version": CONTRADICTION_VERSION,
        "strong_rebuttal": STRONG_REBUTTAL,
        "min_corroborating_sources": MIN_CORROBORATING_SOURCES,
        "sources": list(SOURCE_KEYS),
        "verdicts": list(VERDICTS),
        "weights": {
            "registry_common_officer": W_REGISTRY_COMMON_OFFICER,
            "prior_rfi_self_contradiction": W_PRIOR_RFI_SELF_CONTRADICTION,
            "onchain_sanctioned_exposure": W_ONCHAIN_SANCTIONED_EXPOSURE,
            "onchain_gas_funded_hop": W_ONCHAIN_GAS_FUNDED_HOP,
            "onchain_structured": W_ONCHAIN_STRUCTURED,
            "onchain_counterparty_flow": W_ONCHAIN_COUNTERPARTY_FLOW,
            "device_shared_fingerprint": W_DEVICE_SHARED_FINGERPRINT,
        },
        "lexicon_sizes": {
            "relationship_denial": len(RELATIONSHIP_DENIAL_TERMS),
            "source_of_funds": len(SOURCE_OF_FUNDS_TERMS),
            "exclusive_control": len(EXCLUSIVE_CONTROL_TERMS),
            "relationship_affirmation": len(RELATIONSHIP_AFFIRMATION_TERMS),
        },
    }


def _testable(claim_text: str) -> bool:
    """True iff some probe's lexicon recognises this kind of assertion."""
    low = claim_text.lower()
    return any(
        term in low
        for terms in (
            RELATIONSHIP_DENIAL_TERMS, SOURCE_OF_FUNDS_TERMS, EXCLUSIVE_CONTROL_TERMS,
        )
        for term in terms
    )


def _confidence(rebuttals: list[Rebuttal]) -> float:
    """Noisy-OR over rebuttal strengths — independent evidence accumulates."""
    residual = 1.0
    for r in rebuttals:
        residual *= (1.0 - float(r.strength))
    return round(1.0 - residual, 3)


class ClaimAdjudication(BaseModel):
    """One claim, its verdict, and every piece of evidence behind it."""

    claim_id: str
    claim_text: str
    verdict: str
    confidence: float
    rebuttals: list[Rebuttal] = []

    @property
    def sources(self) -> list[str]:
        """Distinct evidence surfaces that fired, sorted."""
        return sorted({r.source for r in self.rebuttals})

    @property
    def is_contradiction(self) -> bool:
        return self.verdict == "contradicted"

    def summary(self) -> dict:
        return {
            "claim_id": self.claim_id,
            "verdict": self.verdict,
            "confidence": self.confidence,
            "sources": self.sources,
            "rebuttals": len(self.rebuttals),
        }


class ContradictionTable(BaseModel):
    """The claim-by-claim contradiction table for one RFI."""

    rfi_id: str
    uid: int
    adjudications: list[ClaimAdjudication] = []

    @property
    def contradictions(self) -> list[ClaimAdjudication]:
        return [a for a in self.adjudications if a.is_contradiction]

    def get(self, claim_id: str) -> Optional[ClaimAdjudication]:
        return next((a for a in self.adjudications if a.claim_id == claim_id), None)

    def summary(self) -> dict:
        """Compact, ASCII, audit-loggable summary."""
        return {
            "rfi_id": self.rfi_id,
            "claims": len(self.adjudications),
            "contradicted": len(self.contradictions),
            "verdicts": {v: sum(1 for a in self.adjudications if a.verdict == v)
                         for v in VERDICTS},
        }


def adjudicate_claim(rebuttals: list[Rebuttal], claim_text: str) -> str:
    """Apply the corroboration gate to one claim's evidence."""
    if not rebuttals:
        return "uncontested" if _testable(claim_text) else "unverifiable"
    if any(r.strength >= STRONG_REBUTTAL for r in rebuttals):
        return "contradicted"
    if len({r.source for r in rebuttals}) >= MIN_CORROBORATING_SOURCES:
        return "contradicted"
    return "qualified"


def check_contradictions(
    conn: Connectors,
    subject_uid: int,
    backbone: EntityBackbone,
    decomposition: Optional[RfiDecomposition] = None,
) -> Optional[ContradictionTable]:
    """Adjudicate every claim in the subject's RFI under review.

    Returns ``None`` when the subject has no RFI. A *prior* RFI is consumed only
    as a rebuttal source inside the checkers — it is never decomposed or
    adjudicated here.
    """
    decomposition = decomposition or decompose(conn, subject_uid)
    if decomposition is None:
        return None

    rows: list[ClaimAdjudication] = []
    for claim in decomposition.claims:
        rebuttals = run_checkers(conn, backbone, claim, subject_uid)
        rows.append(ClaimAdjudication(
            claim_id=claim.claim_id,
            claim_text=claim.text,
            verdict=adjudicate_claim(rebuttals, claim.text),
            confidence=_confidence(rebuttals),
            rebuttals=rebuttals,
        ))

    return ContradictionTable(
        rfi_id=decomposition.rfi_id, uid=decomposition.uid, adjudications=rows,
    )
