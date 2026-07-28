"""Phase 8 Part I-B S2: the batch sweep — a whole list drop, one chain each.

A batch is a convenience over the unchanged per-designation pipeline: each
designation is swept into its own directory with its own fresh chain and
package over a shared read-only connector, then rolled up. The load-bearing
property is ISOLATION — no cross-designation state — proven by asserting that a
single-designation run and the same designation inside a batch produce
byte-identical output.
"""

from __future__ import annotations

from okojo.sweep import designation_from_record, run_sweep, run_sweep_batch

_CLOCK = lambda: "2026-01-01T00:00:00+00:00"  # noqa: E731


def _all_designations(conn):
    return [designation_from_record(r) for r in conn.all_designations()]


def test_batch_sweeps_every_designation_into_its_own_dir(conn, tmp_path):
    """Each designation gets its own data/sweeps/<id>/ with its own chain and
    package; nothing is shared between them but the read-only connector."""
    des = _all_designations(conn)
    batch = run_sweep_batch(des, out_root=tmp_path / "batch", conn=conn)

    assert batch.rollup["designation_count"] == len(des)
    assert batch.rollup["all_audit_verified"] is True
    # Deterministic order: results are sorted by designation_id.
    ids = [r.designation.designation_id for r in batch.results]
    assert ids == sorted(ids)
    # Per-designation isolation: distinct directories, distinct chains.
    dirs = {r.out_dir for r in batch.results}
    assert len(dirs) == len(batch.results)
    for r in batch.results:
        assert r.out_dir == tmp_path / "batch" / r.designation.designation_id
        assert (r.out_dir / "audit_log.jsonl").exists()
        assert (r.out_dir / "sweep_package.json").exists()
        assert r.audit_verified


def test_batch_rollup_totals_match_per_designation(conn, tmp_path):
    des = _all_designations(conn)
    batch = run_sweep_batch(des, out_root=tmp_path / "batch", conn=conn)
    roll = batch.rollup

    for key in ("exposed", "adjacent_review_only", "name_matches",
                "block_status_gaps", "worksheet_rows", "escalations_drafted",
                "escalations_suppressed"):
        assert roll["totals"][key] == sum(row[key] for row in roll["per_designation"])
    # The roll-up faithfully mirrors each result.
    by_id = {r.designation.designation_id: r for r in batch.results}
    for row in roll["per_designation"]:
        r = by_id[row["designation_id"]]
        assert row["exposed"] == len(r.exposure.exposed)
        assert row["name_matches"] == len(r.name_matches)
        assert row["worksheet_rows"] == len(r.worksheet)


def test_batch_single_designation_output_byte_identical_to_run_sweep(
    conn, sweep_designations, tmp_path
):
    """Semantics unchanged: a designation swept alone and the same designation
    inside a batch produce byte-identical packages and audit chains (under an
    injected clock) — the batch adds no cross-designation state."""
    live, _ = sweep_designations

    solo = run_sweep(live, out_dir=tmp_path / "solo", conn=conn, audit_clock=_CLOCK)
    batch = run_sweep_batch([live], out_root=tmp_path / "batch", conn=conn, audit_clock=_CLOCK)
    inside = batch.results[0]

    assert inside.package_sha256 == solo.package_sha256
    assert inside.package_path.read_bytes() == solo.package_path.read_bytes()
    assert inside.audit_log_path.read_bytes() == solo.audit_log_path.read_bytes()


def test_batch_accepts_raw_payloads_and_fails_closed(conn, tmp_path):
    """A batch parses each entry fail-closed, exactly like run_sweep."""
    import pytest

    from okojo.sweep import DesignationParseError

    good = _all_designations(conn)[0].model_dump()
    with pytest.raises(DesignationParseError):
        run_sweep_batch([{**good, "designation_id": "../escape"}],
                        out_root=tmp_path / "b", conn=conn)
