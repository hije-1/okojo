"""Phase 8 Slice D: the sweep package — deterministic, chain-pinned.

Mirrors the Case Packager's guarantees: clocked byte-stable bytes, the audit
reference block covers every pre-stamp record, the chain's packaged stamp
carries the file's SHA-256, and the chain still verifies. NO second version
constant — the package embeds PACKAGE_VERSION from the shared packager_config.
"""

from __future__ import annotations

import hashlib
import json

from okojo.packager import PACKAGE_VERSION
from okojo.sweep import build_sweep_package, run_sweep

_CLOCK = lambda: "2026-01-01T00:00:00+00:00"  # noqa: E731


def test_sweep_package_written_and_sha_stamped(conn, sweep_designations, tmp_path):
    live, _ = sweep_designations
    res = run_sweep(live, out_dir=tmp_path / "s", conn=conn)

    assert res.package_path is not None and res.package_path.exists()
    assert res.package_path.name == "sweep_package.json"

    payload = res.package_path.read_bytes()
    assert hashlib.sha256(payload).hexdigest() == res.package_sha256

    stamp = [r for r in res.audit_records
             if r["actor"] == "sweep_packager" and r["action"] == "packaged"]
    assert len(stamp) == 1, "exactly one packaged stamp"
    assert json.loads(stamp[0]["detail"])["sha256"] == res.package_sha256
    assert res.audit_verified


def test_sweep_package_uses_shared_version_no_second_constant(conn, sweep_designations, tmp_path):
    live, _ = sweep_designations
    res = run_sweep(live, out_dir=tmp_path / "s", conn=conn)
    doc = json.loads(res.package_path.read_text())
    assert doc["package_version"] == PACKAGE_VERSION


def test_sweep_package_bytes_are_clock_stable(conn, sweep_designations, tmp_path):
    """Two clocked runs produce byte-identical package files and shas."""
    live, _ = sweep_designations
    a = run_sweep(live, out_dir=tmp_path / "a", conn=conn, audit_clock=_CLOCK)
    b = run_sweep(live, out_dir=tmp_path / "b", conn=conn, audit_clock=_CLOCK)
    assert a.package_path.read_bytes() == b.package_path.read_bytes()
    assert a.package_sha256 == b.package_sha256


def test_sweep_package_audit_block_covers_prestamp_records(conn, sweep_designations, tmp_path):
    """The embedded audit block references every record BEFORE the packaged
    stamp — a record cannot contain its own hash — and its tip is the last
    pre-stamp record. The full chain (incl. the stamp) is one longer."""
    live, _ = sweep_designations
    res = run_sweep(live, out_dir=tmp_path / "s", conn=conn)
    doc = json.loads(res.package_path.read_text())

    block = doc["audit"]
    assert block["record_count"] == len(res.audit_records) - 1
    assert block["tip_hash"] == res.audit_records[-2]["hash"]
    assert [r["seq"] for r in block["records"]] == list(range(1, block["record_count"] + 1))
    # Every referenced (seq, hash) matches the real chain record.
    by_seq = {r["seq"]: r for r in res.audit_records}
    for ref in block["records"]:
        assert ref["hash"] == by_seq[ref["seq"]]["hash"]
        assert ref["actor"] == by_seq[ref["seq"]]["actor"]
        assert ref["action"] == by_seq[ref["seq"]]["action"]
    assert block["verified"] is True


def test_sweep_package_content_faithful_to_result(conn, sweep_designations, tmp_path):
    live, _ = sweep_designations
    res = run_sweep(live, out_dir=tmp_path / "s", conn=conn)
    doc = json.loads(res.package_path.read_text())

    assert doc["designation"]["designation_id"] == live.designation_id
    assert doc["exposure"]["exposed_uids"] == res.exposure.exposed_uids()
    assert doc["exposure"]["adjacent_review_only_uids"] == res.exposure.adjacent_uids()
    assert len(doc["worksheet"]) == len(res.worksheet)
    assert len(doc["escalations"]["drafted"]) == len(res.escalations)
    assert "nothing is sent" in doc["escalations"]["note"].lower()
    # Every worksheet row in the package carries at least one citation.
    for row in doc["worksheet"]:
        assert row["citations"], row["uid"]


def test_decoy_package_is_well_formed_and_empty(conn, sweep_designations, tmp_path):
    _, decoy = sweep_designations
    res = run_sweep(decoy, out_dir=tmp_path / "decoy", conn=conn)
    doc = json.loads(res.package_path.read_text())
    assert doc["exposure"]["exposed_uids"] == []
    assert doc["worksheet"] == []
    assert doc["escalations"]["drafted"] == []
    assert doc["designation"]["addresses_in_ledger"] == []
    assert res.audit_verified


def test_build_sweep_package_is_pure(conn, sweep_designations, tmp_path):
    """build_sweep_package is a pure function of a completed result (usable by
    the UI without re-running): calling it twice yields equal dicts."""
    live, _ = sweep_designations
    res = run_sweep(live, out_dir=tmp_path / "s", conn=conn)
    assert build_sweep_package(res) == build_sweep_package(res)
