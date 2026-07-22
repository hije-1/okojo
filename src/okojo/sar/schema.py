"""SAR draft schema + the grounding contract.

Every :class:`SarClaim` must carry at least one provenance pointer. A draft that
contains an uncitable claim fails :func:`assert_grounded` — this is the
enforcement point for the grounding contract: the drafter may only assert facts
that trace to a retrieved record.

A light calibration check also flags over-claiming language (the outputs
*propose / surface / draft / flag*; they never say "instantly" or
"autonomously determines").
"""

from __future__ import annotations

from typing import Optional

from pydantic import BaseModel

from ..provenance import Provenance

# Over-claiming language that must not appear in a calibrated SAR draft.
BANNED_TERMS = ("instantly", "autonomously", "guaranteed", "proven fact", "definitely", "certainly")


class UngroundedClaimError(ValueError):
    """Raised when a SAR draft contains a claim with no provenance."""


class SarClaim(BaseModel):
    element: str          # who | what | network | tell | advisory | rfi
    statement: str
    provenance: list[Provenance]

    def is_grounded(self) -> bool:
        return len(self.provenance) > 0

    def citations(self) -> str:
        return "; ".join(p.cite() for p in self.provenance)


class SarDraft(BaseModel):
    subject_uid: int
    subject_name: str
    advisory_id: Optional[str] = None
    sar_key_term: Optional[str] = None
    filing_note: str
    disclaimer: str
    claims: list[SarClaim]

    def ungrounded(self) -> list[SarClaim]:
        return [c for c in self.claims if not c.is_grounded()]

    def narrative(self) -> str:
        """Render claims as numbered sentences, each with its citation(s)."""
        lines = []
        for i, c in enumerate(self.claims, start=1):
            lines.append(f"[{i}] {c.statement}  (source: {c.citations()})")
        return "\n".join(lines)


def assert_grounded(draft: SarDraft) -> None:
    """Fail closed if any claim is uncitable."""
    bad = draft.ungrounded()
    if bad:
        raise UngroundedClaimError(
            f"{len(bad)} uncitable claim(s) in SAR draft: "
            + " | ".join(c.statement for c in bad)
        )


def calibration_violations(draft: SarDraft) -> list[str]:
    """Return any statements that use over-claiming language."""
    hits: list[str] = []
    for c in draft.claims:
        low = c.statement.lower()
        if any(term in low for term in BANNED_TERMS):
            hits.append(c.statement)
    return hits
