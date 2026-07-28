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
from ..identity import (
    VARIANT_MATCH_THRESHOLD,
    VariantNameMatch,
    identity_config,
    screen_name_variants,
)
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
    variant_name_matches: list[VariantNameMatch]  # Part II: transliteration-variant hits
    exposure: ExposureResult
    gaps: list[StatusGap]              # full-ledger reconciliation, uid order
    worksheet: list[WorksheetRow]      # triaged; grounded fail-closed
    escalations: list[EscalationDraft]         # drafted, never sent
    suppressed_escalations: list[SuppressedEscalation]
    out_dir: Path
    audit_log_path: Path
    audit_records: list[dict] = field(default_factory=list)
    audit_verified: bool = False
    # The decision-ready remediation package, built ON the sweep's chain.
    package_path: Optional[Path] = None
    package_sha256: Optional[str] = None

    def exposed_uids(self) -> list[int]:
        return self.exposure.exposed_uids()


@dataclass
class BatchResult:
    """A whole list-drop swept: one independent SweepResult per designation,
    plus a deterministic roll-up. No cross-designation state — each sweep owns
    its chain, its ``data/sweeps/<id>/`` directory, and its package."""

    results: list[SweepResult]         # per designation, sorted by designation_id
    rollup: dict


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
                # Part I-B provenance: which list this came from and when — so
                # the chain records the entry's standing (obligation vs signal)
                # and its lead time, not just its name.
                "source_regime": designation.source_regime,
                "list_type": designation.list_type,
                "obligation_vs_signal": designation.obligation_vs_signal,
                "listed_since": designation.listed_since,
            }),
        )
        # The versioned sweep policy, once per run — mirroring the scoring /
        # retrieval / critic / contradiction / agency / casegraph stamps.
        audit.append("remediation_sweep", "sweep_config", detail=json.dumps(sweep_config()))
        # Part II: the versioned identity-resolution policy (the ninth anti-drift
        # pair) — stamped once per run too, so every sweep's provenance records
        # the exact transliteration tables and variant threshold in force.
        audit.append("remediation_sweep", "identity_config", detail=json.dumps(identity_config()))

        # 1. Designated-name screen over registered account names. The DIRECT
        # screen (unchanged) plus a Part-II variant layer that expands the
        # designated name into its published-romanization variant space and
        # recovers customers a direct/single-script screen misses — each hit
        # citing which rule path fired. Variant hits are surfaced here (and in
        # SweepResult) for identity review; they do not feed the exposure/hold
        # worksheet, so they add no exposure and change no legacy scorecard.
        name_matches = match_designated_name(conn, designation)
        direct_uids = {m.uid for m in name_matches}
        variant_matches = screen_name_variants(
            conn, designation.designated_name, exclude_uids=direct_uids,
        )
        audit.append(
            "remediation_sweep", "name_screen",
            target=designation.designation_id,
            detail=json.dumps({
                "threshold": NAME_MATCH_THRESHOLD,
                "matches": [{"uid": m.uid, "score": m.score} for m in name_matches],
                "variant_threshold": VARIANT_MATCH_THRESHOLD,
                "variant_matches": [
                    {"uid": m.uid, "score": m.score, "rule_path": m.rule_path}
                    for m in variant_matches
                ],
            }),
            provenance=([p for m in name_matches for p in m.provenance]
                        + [p for m in variant_matches for p in m.provenance]),
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
        # emit a row that cannot cite real evidence). Name-screen hits feed the
        # review-tier identity rows (additive foreign-list coverage).
        worksheet = build_worksheet(conn, designation, exposure, gaps, name_matches)
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
                "variant_name_matches": len(variant_matches),
                "block_status_gaps": len(gaps),
                "worksheet_rows": len(worksheet),
                "escalations_drafted": len(escalations),
                "escalations_suppressed": len(suppressed),
                "note": "results surfaced for human remediation; no status was changed",
            }),
        )

        # 6. Decision-ready package, built ON the chain: the records captured
        # here precede the packaged stamp (a record cannot contain its own
        # hash), then the stamp carries the package file's SHA-256 — the log
        # covers the package and the package pins the log. Mirrors the Case
        # Packager exactly, with NO second version constant (packager_config
        # governs both; the sweep doc documents this package's shape).
        # Imported function-locally: packager.py references SweepResult, so a
        # module-level import here would be circular.
        from .packager import _rel, write_sweep_package

        result = SweepResult(
            designation=designation,
            name_matches=name_matches,
            variant_name_matches=variant_matches,
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
        package_path, sha = write_sweep_package(result)
        audit.append(
            "sweep_packager", "packaged", target=_rel(package_path),
            detail=json.dumps({
                "package": "sweep_package.json",
                "sha256": sha,
                "designation_id": designation.designation_id,
                "exposed_accounts": len(exposure.exposed),
                "note": "decision-ready remediation package assembled (human review required)",
            }),
        )
        # Re-read so the returned records include the packaged stamp; the
        # package's own embedded audit block deliberately stops one record
        # short (it was built before this stamp existed).
        result.audit_records = audit.read_all()
        result.audit_verified = audit.verify()
        result.package_path = package_path
        result.package_sha256 = sha
        return result
    finally:
        if owns_conn:
            conn.close()


def run_sweep_batch(
    designations: list[Union[Designation, str, dict]],
    out_root: Optional[Path] = None,
    conn: Optional[Connectors] = None,
    audit_clock: Optional[Callable[[], str]] = None,
) -> BatchResult:
    """Sweep a whole list drop — one independent ``run_sweep`` per designation.

    A batch is a convenience over the unchanged per-designation pipeline: each
    designation is parsed fail-closed, swept into its OWN ``data/sweeps/<id>/``
    directory (or ``out_root/<id>/``) with its OWN fresh chain and package over
    a SHARED read-only connector, and the results are rolled up. There is no
    cross-designation state, so a single-designation ``run_sweep`` and the same
    designation inside a batch produce byte-identical output. Deterministic:
    designations are processed in ``designation_id`` order.
    """
    owns_conn = conn is None
    conn = conn or Connectors()
    try:
        parsed = [d if isinstance(d, Designation) else parse_designation(d)
                  for d in designations]
        parsed.sort(key=lambda d: d.designation_id)
        results: list[SweepResult] = []
        for d in parsed:
            out_dir = (Path(out_root) / d.designation_id) if out_root else None
            results.append(run_sweep(d, out_dir=out_dir, conn=conn, audit_clock=audit_clock))

        per_designation = [
            {
                "designation_id": r.designation.designation_id,
                "source_regime": r.designation.source_regime,
                "list_type": r.designation.list_type,
                "obligation_vs_signal": r.designation.obligation_vs_signal,
                "exposed": len(r.exposure.exposed),
                "adjacent_review_only": len(r.exposure.adjacent),
                "name_matches": len(r.name_matches),
                "block_status_gaps": len(r.gaps),
                "worksheet_rows": len(r.worksheet),
                "escalations_drafted": len(r.escalations),
                "escalations_suppressed": len(r.suppressed_escalations),
                "audit_verified": r.audit_verified,
            }
            for r in results
        ]
        totals = {
            key: sum(row[key] for row in per_designation)
            for key in ("exposed", "adjacent_review_only", "name_matches",
                        "block_status_gaps", "worksheet_rows",
                        "escalations_drafted", "escalations_suppressed")
        }
        rollup = {
            "designation_count": len(results),
            "all_audit_verified": all(r.audit_verified for r in results),
            "per_designation": per_designation,
            "totals": totals,
            "note": "each designation swept independently for human remediation; "
                    "nothing is blocked, unblocked, or sent",
        }
        return BatchResult(results=results, rollup=rollup)
    finally:
        if owns_conn:
            conn.close()
