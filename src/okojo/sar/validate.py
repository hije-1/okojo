"""Grounding validation — resolve every SAR claim citation to a real evidence row.

:func:`~okojo.sar.schema.assert_grounded` rejects a claim that carries *no*
provenance. This module adds the second half of the fail-closed grounding
contract: it rejects a claim whose provenance points at a row that **does not
exist**. "No receipt, no claim" — and the receipt must be a real one.

A citation *resolves* iff its ``(source, row_key)`` names an actual row in the
mock evidence stores. The optional ``.field`` sub-pointer identifies a column
*within* that row, so resolution deliberately ignores it (if the row exists, the
column citation is grounded in it).

Deterministic and read-only: the resolver enumerates the same
provenance-carrying accessors the rest of Okojo consumes, so a claim built from a
real record always resolves and a fabricated pointer never does.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from ..connectors import Connectors
from ..provenance import Provenance
from .schema import SarClaim, SarDraft, UngroundedClaimError


class UnresolvableCitationError(UngroundedClaimError):
    """Raised when a SAR claim cites a row that does not exist in the evidence.

    Subclasses :class:`UngroundedClaimError` so a caller that fails closed on the
    grounding contract catches both the empty-provenance and the dangling-pointer
    failure modes with one ``except``.
    """


class GroundingResolver:
    """Resolves provenance pointers against the (synthetic) evidence stores.

    Builds one ``(source, row_key)`` membership set over every table a claim can
    cite. Construction does a single read pass; :meth:`resolves` is then O(1).
    """

    def __init__(self, conn: Connectors):
        valid: set[tuple[str, str]] = set()

        def add(records) -> None:
            for rec in records:
                p = rec.provenance
                valid.add((p.source, p.row_key))

        # Every evidence table a SAR claim could cite. Reuses the connectors'
        # provenance construction (single source of the row-key format).
        add(conn.all_accounts())
        add(conn.all_kyc())
        add(conn.all_devices())
        add(conn.all_ip_logs())
        add(conn.all_addresses())
        add(conn.all_transactions())
        add(conn.gas_funds())
        add(conn.all_rfis())
        add(conn.all_prior_rfis())
        add(conn.all_registry())
        add(conn.sdn_list())
        self._valid = valid

    def resolves(self, prov: Provenance) -> bool:
        """True iff this pointer names a real evidence row (field ignored)."""
        return (prov.source, prov.row_key) in self._valid


@dataclass
class GroundingReport:
    """Outcome of validating a draft: coverage counts + any dangling pointers."""

    total_claims: int
    grounded_claims: int
    resolved_claims: int
    unresolved: list[tuple[SarClaim, list[Provenance]]] = field(default_factory=list)

    @property
    def fully_grounded(self) -> bool:
        return self.grounded_claims == self.total_claims

    @property
    def fully_resolved(self) -> bool:
        return self.resolved_claims == self.total_claims and not self.unresolved

    def summary(self) -> dict:
        """Compact, ASCII, audit-loggable summary."""
        return {
            "total": self.total_claims,
            "grounded": self.grounded_claims,
            "resolved": self.resolved_claims,
            "unresolved": len(self.unresolved),
        }


def validate_grounding(conn: Connectors, draft: SarDraft) -> GroundingReport:
    """Report per-claim grounding + resolvability without raising.

    A claim counts as *resolved* iff it is grounded (>=1 pointer) and **every**
    one of its pointers resolves — a single dangling pointer taints the claim.
    """
    resolver = GroundingResolver(conn)
    grounded = 0
    resolved = 0
    unresolved: list[tuple[SarClaim, list[Provenance]]] = []
    for c in draft.claims:
        is_grounded = c.is_grounded()
        if is_grounded:
            grounded += 1
        bad = [p for p in c.provenance if not resolver.resolves(p)]
        if is_grounded and not bad:
            resolved += 1
        if bad:
            unresolved.append((c, bad))
    return GroundingReport(
        total_claims=len(draft.claims),
        grounded_claims=grounded,
        resolved_claims=resolved,
        unresolved=unresolved,
    )


def assert_resolvable(conn: Connectors, draft: SarDraft) -> None:
    """Fail closed if any claim cites evidence that does not exist."""
    report = validate_grounding(conn, draft)
    if report.unresolved:
        cites = "; ".join(
            f"{c.element}:{p.cite()}" for c, ps in report.unresolved for p in ps
        )
        raise UnresolvableCitationError(
            f"{len(report.unresolved)} claim(s) cite unresolvable evidence: {cites}"
        )
