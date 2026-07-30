"""Audit Narrator — a grounded, read-only summarizer over the hash chain.

Makes the tamper-evident audit trail *reviewable*, not just provable: it reads a
chain, verifies it, and renders a plain-language, citation-backed narrative of
what the agent did, in order, and why. Read-only — it writes nothing to any
chain. See :mod:`okojo.narrator.narrator` for the disciplines it inherits
(grounding contract, calibrated language, verify-first).
"""

from __future__ import annotations

from .narrator import (
    NARRATOR_VERSION,
    AuditChainNarrative,
    NarrativeGroundingError,
    NarrativeGroundingResolver,
    NarrativeSentence,
    RecordRef,
    assert_calibrated,
    assert_narrative_grounded,
    narrate_chain,
    narrator_config,
)

__all__ = [
    "NARRATOR_VERSION",
    "AuditChainNarrative",
    "NarrativeGroundingError",
    "NarrativeGroundingResolver",
    "NarrativeSentence",
    "RecordRef",
    "assert_calibrated",
    "assert_narrative_grounded",
    "narrate_chain",
    "narrator_config",
]
