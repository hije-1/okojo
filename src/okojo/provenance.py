"""Provenance — the grounding primitive.

Every fact Okojo surfaces must trace to a specific record in the (synthetic)
evidence. A :class:`Provenance` pointer names the *source* it came from, the
*row* within that source, and optionally the *field*. This is the primitive
that makes the **grounding contract** (see ``CLAUDE.md``) enforceable: an
asserted claim carries one or more provenance pointers, and a claim that
carries none is rejected as uncitable.

Kept intentionally tiny. It is a frozen pydantic model so it composes cleanly
into the SAR schema and serialises straight into the audit log.
"""

from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, ConfigDict


class Provenance(BaseModel):
    """An immutable pointer to the evidence a fact was drawn from."""

    model_config = ConfigDict(frozen=True)

    source: str
    """Logical source / table, e.g. ``"accounts"``, ``"transactions"``."""

    row_key: str
    """Identifier of the row, e.g. ``"uid:500000003"`` or ``"SIMTX000012"``."""

    field: Optional[str] = None
    """Optional column the value came from, e.g. ``"internal_tag"``."""

    detail: Optional[str] = None
    """Optional human-readable note, e.g. ``"declared residence country"``."""

    def cite(self) -> str:
        """Compact, human-readable citation, e.g. ``accounts[uid:500000003].internal_tag``."""
        ref = f"{self.source}[{self.row_key}]"
        if self.field:
            ref = f"{ref}.{self.field}"
        return ref


class GroundedFact(BaseModel):
    """A statement bound to at least one :class:`Provenance` pointer.

    The building block for anomalies and SAR claims. Use :meth:`is_grounded`
    (or the stricter validation in ``sar.drafter``) to reject uncitable text
    before it ever reaches an output.
    """

    statement: str
    provenance: list[Provenance]

    def is_grounded(self) -> bool:
        return len(self.provenance) > 0

    def citations(self) -> str:
        return "; ".join(p.cite() for p in self.provenance)
