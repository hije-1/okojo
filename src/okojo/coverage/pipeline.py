"""The coverage assessment's own hash-chained audit trail.

``run_coverage_audit`` computes the read-only :func:`run_coverage_assessment`
finding and stamps it into a fresh tamper-evident chain under
``data/coverage/`` — a NEW chain family, entirely separate from the case and
sweep families, so no existing chain moves a byte. It mirrors ``run_sweep``'s
own-chain discipline: a versioned policy stamp once per run, provenance on every
consequential record, a terminal completion record, and a re-read + verify. It
proposes nothing and changes nothing: the finding is institution-level and
read-only.

The assessment is a whole-book, single-designation-independent artifact, so
there is exactly one chain (not one per designation) and no per-designation
package — the finding is the deliverable.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Optional

from ..audit import AuditLog
from ..config import REPO_ROOT
from ..connectors import Connectors
from ..provenance import Provenance
from . import coverage_config
from .assessment import CoverageAssessment, run_coverage_assessment


@dataclass
class CoverageAuditResult:
    """One coverage assessment plus its own verified chain."""

    assessment: CoverageAssessment
    out_dir: Path
    audit_log_path: Path
    audit_records: list[dict] = field(default_factory=list)
    audit_verified: bool = False


def default_coverage_dir() -> Path:
    """``data/coverage/`` — the single institution-level assessment chain."""
    return REPO_ROOT / "data" / "coverage"


def _leg_provenance(assessment: CoverageAssessment) -> list[Provenance]:
    """One field-level pointer per footprint leg (aggregate over all rows)."""
    out: list[Provenance] = []
    for leg in assessment.footprint_legs:
        for cite in leg.provenance:
            # cite is "source[*].field"; split back to a Provenance pointer.
            src, rest = cite.split("[", 1)
            field_name = rest.split("].", 1)[1] if "]." in rest else None
            out.append(Provenance(source=src, row_key="*", field=field_name,
                                   detail=f"footprint leg: {leg.leg}"))
    return out


def run_coverage_audit(
    conn: Optional[Connectors] = None, *,
    out_dir: Optional[Path] = None,
    audit_clock: Optional[Callable[[], str]] = None,
    coverage_map: Optional[dict] = None,
    list_source_registry: Optional[dict] = None,
) -> CoverageAuditResult:
    """Compute the coverage assessment and stamp it into its own chain."""
    owns_conn = conn is None
    conn = conn or Connectors()
    out_dir = Path(out_dir) if out_dir else default_coverage_dir()
    out_dir.mkdir(parents=True, exist_ok=True)
    audit_path = out_dir / "audit_log.jsonl"
    if audit_path.exists():
        audit_path.unlink()  # fresh chain per run, mirroring run_sweep / run_case
    audit = AuditLog(audit_path, clock=audit_clock) if audit_clock else AuditLog(audit_path)

    try:
        assessment = run_coverage_assessment(
            conn, coverage_map=coverage_map, list_source_registry=list_source_registry)

        audit.append(
            "coverage_assessment", "assessment_open",
            detail=json.dumps({
                "config_version": assessment.config_version,
                "footprint_legs": [leg.leg for leg in assessment.footprint_legs],
                "note": "institution-level screening coverage-gap assessment; "
                        "read-only, proposes nothing",
            }),
        )
        # The versioned coverage policy, once per run — mirroring the sweep /
        # scoring / retrieval config stamps.
        audit.append("coverage_assessment", "coverage_config",
                     detail=json.dumps(coverage_config()))

        # The footprint — three legs, each counted and cited to its field.
        audit.append(
            "coverage_assessment", "footprint",
            detail=json.dumps({
                "legs": [
                    {"leg": leg.leg, "label": leg.label, "count_unit": leg.count_unit,
                     "total": leg.total, "jurisdictions": sorted(leg.counts)}
                    for leg in assessment.footprint_legs],
                "footprint_jurisdictions": assessment.footprint_jurisdictions,
            }),
            provenance=_leg_provenance(assessment),
        )

        # The coverage finding — covered / gap sets + the declared-not-ingested
        # regimes elevated to a finding. Cited to the policy and the registry.
        audit.append(
            "coverage_assessment", "coverage_finding",
            detail=json.dumps({
                "covered": assessment.covered_jurisdictions,
                "ingestion_gaps": assessment.ingestion_gaps,
                "no_coverage_gaps": assessment.no_coverage_gaps,
                "declared_not_ingested_regimes": assessment.declared_not_ingested_regimes,
                "note": "a footprint jurisdiction with no enabled list coverage is a "
                        "screening-scope observation, not a legal claim",
            }),
            provenance=[
                Provenance(source="coverage_config",
                           row_key="regime_jurisdiction_coverage",
                           detail=f"v{assessment.config_version}"),
                Provenance(source="list_source_registry", row_key="ingested",
                           detail="enabled-coverage status, read from the frozen sweep registry"),
            ],
        )

        audit.append(
            "coverage_assessment", "assessment_complete",
            detail=json.dumps({
                "footprint_jurisdictions": len(assessment.footprint_jurisdictions),
                "covered": len(assessment.covered_jurisdictions),
                "ingestion_gaps": len(assessment.ingestion_gaps),
                "no_coverage_gaps": len(assessment.no_coverage_gaps),
                "declared_not_ingested_regimes": len(assessment.declared_not_ingested_regimes),
                "note": "finding surfaced for human review; nothing was changed",
            }),
        )

        return CoverageAuditResult(
            assessment=assessment,
            out_dir=out_dir,
            audit_log_path=audit_path,
            audit_records=audit.read_all(),
            audit_verified=audit.verify(),
        )
    finally:
        if owns_conn:
            conn.close()
