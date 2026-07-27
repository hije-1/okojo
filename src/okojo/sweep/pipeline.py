"""``run_sweep`` — the sweep's plain sequential pipeline.

Not a second LangGraph, on purpose: agentic machinery belongs only where
genuine decisions exist, and the sweep has none that branch — parse, screen,
walk, reconcile, in the same order every time. What it shares with the case
pipeline is the discipline, not the orchestrator: a fresh tamper-evident audit
chain per run (its OWN chain, under ``data/sweeps/<designation_id>/`` — the
case chains under ``data/cases/`` are never touched), the versioned
``sweep_config`` stamped once per run, provenance on every surfaced fact, and
calibrated language throughout (the sweep *surfaces* and *flags*; a human
remediates).
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Optional, Union

from ..audit import AuditLog
from ..config import REPO_ROOT
from ..connectors import Connectors
from . import NAME_MATCH_THRESHOLD, sweep_config
from .designation import (
    DESIGNATION_ID_PATTERN,
    Designation,
    DesignationNameMatch,
    match_designated_name,
    parse_designation,
)
from .escalations import EscalationDraft, SuppressedEscalation, draft_escalations
from .exposure import ExposureResult, sweep_exposure
from .verify import StatusGap, verify_block_status
from .worksheet import WorksheetRow, build_worksheet, worksheet_grounding_report


@dataclass
class SweepResult:
    designation: Designation
    name_matches: list[DesignationNameMatch]
    exposure: ExposureResult
    gaps: list[StatusGap]              # full-ledger reconciliation, uid order
    worksheet: list[WorksheetRow]      # triaged; grounded fail-closed
    escalations: list[EscalationDraft]         # drafted, never sent
    suppressed_escalations: list[SuppressedEscalation]
    out_dir: Path
    audit_log_path: Path
    audit_records: list[dict] = field(default_factory=list)
    audit_verified: bool = False

    def exposed_uids(self) -> list[int]:
        return self.exposure.exposed_uids()


def default_sweep_dir(designation_id: str) -> Path:
    """``data/sweeps/<designation_id>/`` — the id is validated by the caller
    before this is ever derived."""
    return REPO_ROOT / "data" / "sweeps" / designation_id


def run_sweep(
    designation: Union[Designation, str, dict],
    out_dir: Optional[Path] = None,
    conn: Optional[Connectors] = None,
    audit_clock: Optional[Callable[[], str]] = None,
) -> SweepResult:
    """Execute the remediation sweep for one designation.

    Accepts a validated :class:`Designation` or a raw payload (JSON text /
    mapping), which is parsed fail-closed FIRST: nothing is written — no
    directory, no audit record — until the designation has fully validated,
    and ``designation_id`` is re-checked against its published shape before
    any filesystem path is derived from it.
    """
    if not isinstance(designation, Designation):
        designation = parse_designation(designation)
    # Defense in depth: the model already enforces this pattern, but the id is
    # about to name a directory, so the property is re-asserted at the boundary
    # where it matters (and survives even if the model's constraint drifts).
    if not re.fullmatch(DESIGNATION_ID_PATTERN, designation.designation_id):
        raise ValueError(f"designation_id failed shape check: {designation.designation_id!r}")

    owns_conn = conn is None
    conn = conn or Connectors()
    out_dir = Path(out_dir) if out_dir else default_sweep_dir(designation.designation_id)
    out_dir.mkdir(parents=True, exist_ok=True)
    audit_path = out_dir / "audit_log.jsonl"
    if audit_path.exists():
        audit_path.unlink()  # fresh chain per run, mirroring run_case
    audit = AuditLog(audit_path, clock=audit_clock) if audit_clock else AuditLog(audit_path)

    try:
        audit.append(
            "remediation_sweep", "sweep_open",
            target=designation.designation_id,
            detail=json.dumps({
                "designated_name": designation.designated_name,
                "program": designation.program,
                "designated_addresses": len(designation.designated_addresses),
                "designation_date": designation.designation_date,
            }),
        )
        # The versioned sweep policy, once per run — mirroring the scoring /
        # retrieval / critic / contradiction / agency / casegraph stamps.
        audit.append("remediation_sweep", "sweep_config", detail=json.dumps(sweep_config()))

        # 1. Designated-name screen over registered account names.
        name_matches = match_designated_name(conn, designation)
        audit.append(
            "remediation_sweep", "name_screen",
            target=designation.designation_id,
            detail=json.dumps({
                "threshold": NAME_MATCH_THRESHOLD,
                "matches": [{"uid": m.uid, "score": m.score} for m in name_matches],
            }),
            provenance=[p for m in name_matches for p in m.provenance],
        )

        # 2. Full-ledger exposure walk from the designated address set.
        exposure = sweep_exposure(conn, list(designation.designated_addresses))
        audit.append(
            "remediation_sweep", "exposure_sweep",
            target=designation.designation_id,
            detail=json.dumps({
                "addresses_in_ledger": len(exposure.addresses_in_ledger),
                "addresses_not_in_ledger": len(exposure.addresses_not_in_ledger),
                "exposed_hops_by_uid": {str(u): h for u, h in sorted(exposure.hops_by_uid().items())},
                "direct_uids": exposure.direct_uids(),
                "adjacent_review_only_uids": exposure.adjacent_uids(),
            }),
        )

        # 3. Two-system hold reconciliation over the full ledger.
        gaps = verify_block_status(conn)
        audit.append(
            "remediation_sweep", "block_verify",
            detail=json.dumps({
                "accounts_reconciled": len(conn.all_accounts()),
                "gaps": [{"uid": g.uid, "gap_type": g.gap_type} for g in gaps],
            }),
            provenance=[p for g in gaps for p in g.provenance],
        )

        # 4. Triage worksheet — grounded fail-closed (build raises rather than
        # emit a row that cannot cite real evidence).
        worksheet = build_worksheet(conn, designation, exposure, gaps)
        actions: dict[str, int] = {}
        for row in worksheet:
            actions[row.recommended_action] = actions.get(row.recommended_action, 0) + 1
        audit.append(
            "remediation_sweep", "worksheet_build",
            target=designation.designation_id,
            detail=json.dumps({
                "rows": len(worksheet),
                "actions": dict(sorted(actions.items())),
                "grounding": worksheet_grounding_report(conn, worksheet).summary(),
            }),
        )

        # 5. Internal escalation drafts — drafted, validated, never sent;
        # anything the validator refuses is surfaced as suppressed.
        escalations, suppressed = draft_escalations(conn, designation, worksheet)
        audit.append(
            "remediation_sweep", "escalations_draft",
            target=designation.designation_id,
            detail=json.dumps({
                "drafted": [{"id": e.escalation_id, "kind": e.kind, "uid": e.uid}
                            for e in escalations],
                "suppressed": [{"kind": s.kind, "uid": s.uid, "reason": s.reason}
                               for s in suppressed],
                "note": "drafts prepared for the human remediation owner; nothing is sent",
            }),
        )

        audit.append(
            "remediation_sweep", "sweep_complete",
            target=designation.designation_id,
            detail=json.dumps({
                "exposed_accounts": len(exposure.exposed),
                "adjacent_review_only": len(exposure.adjacent),
                "name_matches": len(name_matches),
                "block_status_gaps": len(gaps),
                "worksheet_rows": len(worksheet),
                "escalations_drafted": len(escalations),
                "escalations_suppressed": len(suppressed),
                "note": "results surfaced for human remediation; no status was changed",
            }),
        )

        return SweepResult(
            designation=designation,
            name_matches=name_matches,
            exposure=exposure,
            gaps=gaps,
            worksheet=worksheet,
            escalations=escalations,
            suppressed_escalations=suppressed,
            out_dir=out_dir,
            audit_log_path=audit_path,
            audit_records=audit.read_all(),
            audit_verified=audit.verify(),
        )
    finally:
        if owns_conn:
            conn.close()
