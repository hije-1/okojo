"""Internal escalation drafts — drafted, validated, NEVER sent.

For every worksheet account with a reconciliation gap, and for every exposed
account with no hold anywhere, the sweep prepares an internal-to-compliance
escalation draft modeled on the follow-up-RFI discipline: the material is a
worklist for the human remediation owner, who owns assembly, judgment, and any
sending — no send path exists in this codebase.

Fail-closed validation before a draft is emitted: it must be grounded, every
pointer must resolve, and the text must pass the SAR calibration term check
(``BANNED_TERMS``). A draft that fails any check is SUPPRESSED — surfaced with
its reason, flagged for human authoring, never silently dropped and never
emitted. ``assert_no_tipping_off`` deliberately does not apply: it guards
subject-facing text (per its contract), and Phase 8 produces none — these
drafts are internal routing material.
"""

from __future__ import annotations

from pydantic import BaseModel

from ..connectors import Connectors
from ..provenance import Provenance
from ..sar import BANNED_TERMS, GroundingResolver
from . import calibrated_language_violations
from .designation import Designation
from .worksheet import WorksheetRow

DRAFT_STATUS = "drafted_pending_human_review"


class EscalationDraft(BaseModel):
    """One internal escalation, prepared for the human remediation owner."""

    escalation_id: str
    kind: str                  # "reconciliation_gap" | "exposed_unblocked"
    uid: int
    subject: str               # internal routing subject line
    body: str
    status: str = DRAFT_STATUS  # the only status this codebase can produce
    citations: list[str]       # analyst-facing pointers, never part of the body
    provenance: list[Provenance]


class SuppressedEscalation(BaseModel):
    """A draft the fail-closed validator refused to emit — surfaced, with why."""

    kind: str
    uid: int
    reason: str


def _gap_body(row: WorksheetRow, designation: Designation) -> str:
    return (
        f"Hold-status reconciliation gap on account {row.uid} ({row.entity_name}): "
        f"warehouse={row.warehouse_status}, admin={row.admin_status} "
        f"({row.gap_type}). The account is surfaced by the sweep for designation "
        f"{designation.designation_id}. This draft flags the discrepancy for the "
        "reconciliation owner; a human verifies the true status and actions any "
        "correction. Prepared by an automated sweep; not sent."
    )


def _unblocked_body(row: WorksheetRow, designation: Designation) -> str:
    kind = "direct" if row.direct else "indirect"
    return (
        f"Account {row.uid} ({row.entity_name}) shows {kind} flow exposure to "
        f"designation {designation.designation_id} at hop distance {row.hops} "
        f"(tainted amount {row.exposure_usdt:,.2f} USDT from the cited "
        f"transactions) and carries no hold in either system "
        f"(warehouse={row.warehouse_status}, admin={row.admin_status}). "
        "This draft proposes a designation hold review; a human decides and "
        "actions any hold. Prepared by an automated sweep; not sent."
    )


def _signal_exposure_body(row: WorksheetRow, designation: Designation) -> str:
    """SIGNAL-type variant: a foreign national-list entry is a timestamped risk
    signal, not an obligation, so this draft proposes REVIEW — never a hold. It
    carries no legal-effect language (enforced by the calibrated-language ban)."""
    kind = "direct" if row.direct else "indirect"
    return (
        f"Account {row.uid} ({row.entity_name}) shows {kind} flow exposure to "
        f"{designation.source_regime} national-list entry {designation.designation_id} "
        f"(a risk signal listed since {designation.listed_since}, not a designation "
        f"obligation) at hop distance {row.hops} (tainted amount "
        f"{row.exposure_usdt:,.2f} USDT from the cited transactions), and carries no "
        f"hold in either system (warehouse={row.warehouse_status}, "
        f"admin={row.admin_status}). This draft surfaces the foreign-list signal for "
        "analyst review; a human assesses it. Prepared by an automated sweep; not sent."
    )


def draft_escalations(
    conn: Connectors,
    designation: Designation,
    worksheet: list[WorksheetRow],
) -> tuple[list[EscalationDraft], list[SuppressedEscalation]]:
    """Draft per-gap and per-exposed-unblocked escalations from the worksheet.

    Escalations are worksheet-scoped (the designation's surfaced accounts);
    the full-ledger gap list rides separately on the sweep result. Returns
    ``(drafts, suppressed)`` — suppressed entries are the drafts the validator
    refused, surfaced with reasons for human authoring.
    """
    resolver = GroundingResolver(conn)
    is_signal = designation.obligation_vs_signal == "signal"
    drafts: list[EscalationDraft] = []
    suppressed: list[SuppressedEscalation] = []
    counter = 0

    def _emit(kind: str, row: WorksheetRow, subject: str, body: str) -> None:
        nonlocal counter
        text = f"{subject} {body}"
        low = text.lower()
        # SAR calibration terms always; for a SIGNAL-type designation, ALSO the
        # legal-effect ban — a foreign listing must never be written as an
        # obligation. Both are suppress-and-surface (never silently dropped).
        hits = [t for t in BANNED_TERMS if t in low]
        if is_signal:
            hits = hits + calibrated_language_violations(text)
        if hits:
            suppressed.append(SuppressedEscalation(
                kind=kind, uid=row.uid,
                reason=f"calibration violation ({', '.join(hits)}); flagged for human authoring",
            ))
            return
        if not row.provenance:
            suppressed.append(SuppressedEscalation(
                kind=kind, uid=row.uid,
                reason="no provenance to carry; flagged for human authoring",
            ))
            return
        bad = [p for p in row.provenance if not resolver.resolves(p)]
        if bad:
            suppressed.append(SuppressedEscalation(
                kind=kind, uid=row.uid,
                reason="cites unresolvable evidence: "
                       + "; ".join(p.cite() for p in bad),
            ))
            return
        counter += 1
        drafts.append(EscalationDraft(
            escalation_id=f"ESC-{designation.designation_id}-{counter:04d}",
            kind=kind, uid=row.uid, subject=subject, body=body,
            citations=[p.cite() for p in row.provenance],
            provenance=list(row.provenance),
        ))

    # Worksheet order is already the published triage order, so escalation ids
    # are deterministic and severity-aligned.
    for row in worksheet:
        if row.gap_type is not None:
            _emit(
                "reconciliation_gap", row,
                f"[{designation.designation_id}] hold-status gap: account {row.uid} ({row.gap_type})",
                _gap_body(row, designation),
            )
    for row in worksheet:
        if (row.hops is not None and row.gap_type is None
                and row.warehouse_status == "no_hold" and row.admin_status == "no_hold"):
            if is_signal:
                _emit(
                    "foreign_signal_exposure", row,
                    f"[{designation.designation_id}] foreign-list signal exposure (review): account {row.uid}",
                    _signal_exposure_body(row, designation),
                )
            else:
                _emit(
                    "exposed_unblocked", row,
                    f"[{designation.designation_id}] designation exposure with no hold: account {row.uid}",
                    _unblocked_body(row, designation),
                )
    return drafts, suppressed
