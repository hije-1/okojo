"""Sweep packager — the decision-ready remediation package, built ON the chain.

The sweep's analogue of the Case Packager: one deterministic JSON document per
designation holding everything a human remediation owner needs — the
designation, the exposed and adjacency-review accounts with their evidence,
the hold-status reconciliation gaps, the triaged worksheet, the drafted (never
sent) escalations and any suppressed ones — plus an **audit reference block**
that pins the package to the sweep's own tamper-evident chain.

It reuses the Case Packager's two structural rules verbatim, deliberately with
NO second version constant: the packaging policy already published in
``packager_config()`` (``docs/packager-methodology.md``) governs here too, and
the sweep methodology doc documents the sweep package's shape rather than
minting a new versioned config.

* **References, never re-derivations.** The audit block lists each chain
  record as ``(seq, actor, action, hash)`` plus the tip hash and verification
  result, captured *before* the ``packaged`` stamp — the chain then stamps the
  package file's SHA-256.
* **Deterministic bytes.** Serialized sorted-keys / ASCII-only, no wall-clock
  values of its own, ``newline="\n"`` so on-disk bytes equal the hashed
  payload on every platform. Reproducible exactly under an injected audit
  clock (regression-tested).

Calibrated language: the package is *assembled for human remediation*. Nothing
in it blocks, unblocks, files, or determines anything.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from ..config import REPO_ROOT
from ..packager import PACKAGE_VERSION
from .pipeline import SweepResult


def _rel(path: Path) -> str:
    """Repo-relative path for audit logging — never leak an absolute/home path."""
    try:
        return path.relative_to(REPO_ROOT).as_posix()
    except ValueError:
        return path.name


def build_sweep_package(result: SweepResult) -> dict:
    """Assemble the decision-ready remediation package from a sweep result.

    The audit records on ``result`` were captured at sweep completion, BEFORE
    this package (and its ``packaged`` stamp) exists — a record cannot contain
    its own hash.
    """
    d = result.designation
    exposure = result.exposure
    records = result.audit_records

    package: dict = {
        "package_version": PACKAGE_VERSION,
        "readme": (
            "Decision-ready remediation package assembled by Okojo "
            "(synthetic-data research prototype) for HUMAN review and "
            "remediation. Nothing here blocks, unblocks, files, or is final. "
            "Every audit reference below resolves into the tamper-evident hash "
            "chain in audit_log.jsonl."
        ),
        "designation": {
            "designation_id": d.designation_id,
            "designated_name": d.designated_name,
            "program": d.program,
            "entity_type": d.entity_type,
            "designated_addresses": list(d.designated_addresses),
            "designation_date": d.designation_date,
            "addresses_in_ledger": list(exposure.addresses_in_ledger),
            "addresses_not_in_ledger": list(exposure.addresses_not_in_ledger),
        },
        "name_matches": [
            {"uid": m.uid, "entity_name": m.entity_name, "score": m.score,
             "citations": [p.cite() for p in m.provenance]}
            for m in result.name_matches
        ],
        "exposure": {
            "exposed_uids": exposure.exposed_uids(),
            "direct_uids": exposure.direct_uids(),
            "adjacent_review_only_uids": exposure.adjacent_uids(),
            "exposed": [
                {"uid": e.uid, "entity_name": e.entity_name, "hops": e.hops,
                 "direct": e.direct, "tainted_amount_usdt": e.tainted_amount_usdt,
                 "citations": [p.cite() for p in e.provenance]}
                for e in exposure.exposed
            ],
            "adjacent": [
                {"uid": a.uid, "entity_name": a.entity_name,
                 "link_types": a.link_types,
                 "linked_exposed_uids": a.linked_exposed_uids,
                 "citations": [p.cite() for p in a.provenance]}
                for a in exposure.adjacent
            ],
        },
        "block_status_gaps": [
            {"uid": g.uid, "warehouse_status": g.warehouse_status,
             "admin_status": g.admin_status, "gap_type": g.gap_type,
             "citations": [p.cite() for p in g.provenance]}
            for g in result.gaps
        ],
        "worksheet": [
            {"uid": r.uid, "entity_name": r.entity_name,
             "exposure_usdt": r.exposure_usdt, "hops": r.hops,
             "direct": r.direct, "warehouse_status": r.warehouse_status,
             "admin_status": r.admin_status, "gap_type": r.gap_type,
             "internal_tag_flag": r.internal_tag_flag,
             "recommended_action": r.recommended_action,
             "statement": r.statement,
             "citations": [p.cite() for p in r.provenance]}
            for r in result.worksheet
        ],
        "escalations": {
            "note": "drafts prepared for the human remediation owner, who owns "
                    "assembly, judgment, and any sending; no send path exists "
                    "and nothing is sent",
            "drafted": [
                {"escalation_id": e.escalation_id, "kind": e.kind, "uid": e.uid,
                 "subject": e.subject, "body": e.body, "status": e.status,
                 "citations": e.citations}
                for e in result.escalations
            ],
            "suppressed": [
                {"kind": s.kind, "uid": s.uid, "reason": s.reason}
                for s in result.suppressed_escalations
            ],
        },
        "audit": {
            "log": "audit_log.jsonl",
            "verified": result.audit_verified,
            "tip_hash": records[-1]["hash"],
            "record_count": len(records),
            "records": [
                {"seq": r["seq"], "actor": r["actor"], "action": r["action"],
                 "hash": r["hash"]}
                for r in records
            ],
        },
    }
    return package


def write_sweep_package(result: SweepResult) -> tuple[Path, str]:
    """Serialize the package to ``<out_dir>/sweep_package.json`` and return its
    ``(path, sha256)`` — the caller (``run_sweep``) stamps the SHA into the
    chain, so this stays a pure build+write with no audit dependency.

    Mirrors the Case Packager write-path exactly: built on the records
    captured at sweep completion (BEFORE the ``packaged`` stamp — a record
    cannot contain its own hash), serialized sorted-keys / ASCII-only, written
    with ``newline="\\n"`` so on-disk bytes equal the hashed payload on every
    platform.
    """
    package = build_sweep_package(result)
    payload = json.dumps(package, indent=2, sort_keys=True, ensure_ascii=True) + "\n"
    package_path = result.out_dir / "sweep_package.json"
    package_path.write_text(payload, encoding="utf-8", newline="\n")
    sha = hashlib.sha256(payload.encode("utf-8")).hexdigest()
    return package_path, sha
