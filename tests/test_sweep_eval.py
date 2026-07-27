"""Phase 8 eval — the sweep scorecard (the 11th scorecard in the ritual).

Calibration (PM amendment): the recall/FP numbers against the gold key are a
DUAL-IMPLEMENTATION CONSISTENCY CHECK — the sweep engine and the generator's
answer-key helper are two independent implementations of the same published
exposure semantics, so agreement is a consistency property of this synthetic
world, not a field-performance claim. The evidentiary weight is carried by the
named traps: decoy -> empty set, the legacy-exposure anti-replay account, the
recidivist dead-end, and the internally-tagged account staying review-only.
"""

from __future__ import annotations

from okojo.eval import score
from okojo.sweep import run_sweep, verify_block_status, worksheet_grounding_report


def test_sweep_eval_exposure_scorecard(
    conn, ground_truth, ring, sweep_designations, tmp_path, capsys
):
    live, decoy = sweep_designations
    res = run_sweep(live, out_dir=tmp_path / "live", conn=conn)
    res_decoy = run_sweep(decoy, out_dir=tmp_path / "decoy", conn=conn)

    gold = ground_truth["designation_exposed_uids"][live.designation_id]
    exposure = score(res.exposure.exposed_uids(), gold)
    direct = score(res.exposure.direct_uids(),
                   ground_truth["designation_direct_uids"][live.designation_id])
    adjacent = score(res.exposure.adjacent_uids(),
                     ground_truth["designation_adjacent_uids"][live.designation_id])

    scorecard = {
        "exposure_vs_gold (consistency check)": str(exposure),
        "direct_vs_gold": str(direct),
        "adjacency_review_only_vs_gold": str(adjacent),
        "hop_distances_exact": {str(u): h for u, h in res.exposure.hops_by_uid().items()}
        == ground_truth["designation_exposure_hops"][live.designation_id],
        "decoy_hits (FP probe)": len(res_decoy.exposure.exposed) + len(res_decoy.name_matches),
        "trap_legacy_replay_excluded": ring["EMPLOYEE"] not in set(res.exposure.exposed_uids()),
        "trap_recidivist_dead_end_excluded": ring["RECIDIVIST"] not in set(res.exposure.exposed_uids()),
        "trap_internal_tag_review_only": ring["PRIVILEGED"] in set(res.exposure.adjacent_uids())
        and ring["PRIVILEGED"] not in set(res.exposure.exposed_uids()),
        "audit_verified": res.audit_verified and res_decoy.audit_verified,
    }
    with capsys.disabled():
        print("\nPhase 8 sweep scorecard (designation exposure -- dual-implementation consistency):")
        for k, v in scorecard.items():
            print(f"  {k}: {v}")

    # Consistency with the independently computed answer key.
    assert exposure.recall == 1.0 and exposure.fp == 0 and exposure.precision == 1.0
    assert direct.recall == 1.0 and direct.fp == 0
    assert adjacent.recall == 1.0 and adjacent.fp == 0
    assert scorecard["hop_distances_exact"]
    # The named traps — where a wrong implementation fails loudly.
    assert scorecard["decoy_hits (FP probe)"] == 0
    assert scorecard["trap_legacy_replay_excluded"]
    assert scorecard["trap_recidivist_dead_end_excluded"]
    assert scorecard["trap_internal_tag_review_only"]
    # Review-only means review-only: adjacency and exposure never overlap.
    assert not set(res.exposure.adjacent_uids()) & set(res.exposure.exposed_uids())
    assert scorecard["audit_verified"]


def test_sweep_eval_gap_detection_scorecard(conn, ground_truth, capsys):
    gaps = verify_block_status(conn)
    predicted = {(g.uid, g.gap_type) for g in gaps}
    gold = {(g["uid"], g["gap_type"]) for g in ground_truth["block_status_gaps"]}
    s = score(predicted, gold)

    with capsys.disabled():
        print("\nPhase 8 sweep scorecard (hold-status reconciliation):")
        print(f"  gap_detection: {s}")
        for g in gaps:
            print(f"    uid={g.uid} {g.gap_type} "
                  f"(warehouse={g.warehouse_status} admin={g.admin_status})")

    assert s.precision == 1.0 and s.recall == 1.0 and s.f1 == 1.0
    # Direction fields exact, per planted gap, both rows cited.
    by_uid = {g.uid: g for g in gaps}
    for want in ground_truth["block_status_gaps"]:
        got = by_uid[want["uid"]]
        assert got.warehouse_status == want["warehouse_status"]
        assert got.admin_status == want["admin_status"]
        assert len(got.provenance) == 2


def test_sweep_eval_worksheet_grounding_scorecard(
    conn, sweep_designations, tmp_path, capsys
):
    """Grounding coverage over the remediation deliverables: every worksheet
    row and every escalation draft cites only evidence that resolves. The
    fail-closed negative control (a fabricated pointer raising) lives in
    test_sweep_worksheet.py."""
    live, _ = sweep_designations
    res = run_sweep(live, out_dir=tmp_path / "live", conn=conn)

    report = worksheet_grounding_report(conn, res.worksheet)
    esc_grounded = sum(1 for e in res.escalations if e.provenance)

    scorecard = {
        "worksheet_rows": report.total_claims,
        "rows_grounded": report.grounded_claims,
        "rows_resolved": report.resolved_claims,
        "rows_unresolved": len(report.unresolved),
        "escalations_drafted": len(res.escalations),
        "escalations_grounded": esc_grounded,
        "escalations_suppressed": len(res.suppressed_escalations),
    }
    with capsys.disabled():
        print("\nPhase 8 sweep scorecard (worksheet grounding):")
        for k, v in scorecard.items():
            print(f"  {k}: {v}")

    assert report.total_claims > 0
    assert report.fully_grounded and report.fully_resolved
    assert esc_grounded == len(res.escalations) > 0
    assert res.suppressed_escalations == []
