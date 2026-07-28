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


# --------------------------------------------------------------------------- #
# Part I-B S2 — cross-list early warning (the announced sweep_eval foreign
# sections; the domestic scorecards above are unchanged)
# --------------------------------------------------------------------------- #
def test_sweep_eval_foreign_lead_time_scorecard(
    conn, ground_truth, sweep_designations, foreign_designations, tmp_path, capsys
):
    """Lead-time (time axis): a foreign national-list entry over an existing
    network wallet, listed ~2 years before the domestic designation — so the
    sweep measures the money that moved while ONLY the foreign list knew. The
    domestic designation, listed the day it was designated, has zero window."""
    lead, _ = foreign_designations
    domestic_live, _ = sweep_designations
    res = run_sweep(lead, out_dir=tmp_path / "lead", conn=conn)

    window = ground_truth["designation_lead_time_window"][lead.designation_id]
    gold_inwin = ground_truth["designation_exposure_in_window"][lead.designation_id]

    # Recompute the in-window FLOW set from the SWEEP: exposed counterparties
    # (hops >= 1) whose driving transactions fall inside the lead-time window.
    tx_date = {str(t["tx_id"]): str(t["timestamp"])[:10] for t in conn.all_transactions()}
    tx_amt = {str(t["tx_id"]): float(t["amount_usdt"]) for t in conn.all_transactions()}
    lo, hi = window["listed_since"], window["designation_date"]
    sweep_flow = sorted(
        e.uid for e in res.exposure.exposed
        if e.hops and e.hops >= 1
        and any(p.source == "transactions" and lo <= tx_date[p.row_key] <= hi
                for p in e.provenance)
    )
    # In-window direct inflow onto the designated wallet, from the SWEEP's addr.
    designated = set(lead.designated_addresses)
    sweep_inflow = round(sum(
        tx_amt[str(t["tx_id"])] for t in conn.all_transactions()
        if str(t["to_ref"]) in designated and lo <= str(t["timestamp"])[:10] <= hi
    ), 2)

    domestic_window = ground_truth["designation_lead_time_window"][domestic_live.designation_id]

    scorecard = {
        "regime": lead.source_regime,
        "standing": lead.obligation_vs_signal,
        "lead_days (foreign)": window["lead_days"],
        "lead_days (domestic)": domestic_window["lead_days"],
        "in_window_flow_uids": sweep_flow,
        "in_window_flow_matches_gold": sweep_flow == gold_inwin["flow_uids"],
        "in_window_direct_inflow_usdt": sweep_inflow,
        "inflow_matches_gold": sweep_inflow == gold_inwin["direct_inflow_usdt"],
        "audit_verified": res.audit_verified,
    }
    with capsys.disabled():
        print("\nPhase 8 sweep scorecard (cross-list lead-time / foreign national list):")
        for k, v in scorecard.items():
            print(f"  {k}: {v}")

    # A real lead time exists for the foreign plant, none for the domestic.
    assert window["lead_days"] > 700 and domestic_window["lead_days"] == 0
    # The in-window flow set and inflow are exactly the gold (money that moved
    # while only the foreign list knew) and the sweep reproduces them.
    assert sweep_flow == gold_inwin["flow_uids"] and len(sweep_flow) > 0
    assert sweep_inflow == gold_inwin["direct_inflow_usdt"] > 0
    assert res.audit_verified


def test_sweep_eval_foreign_granularity_scorecard(
    conn, ground_truth, ring, foreign_designations, tmp_path, capsys
):
    """Granularity (depth axis): a name-only foreign listing (no wallet, no
    domestic designation) is surfaced by the name screen as a review-tier
    identity row — proving foreign-list coverage is ADDITIVE, not duplicative:
    the matched account appears in NO domestic exposure set."""
    _, name_only = foreign_designations
    res = run_sweep(name_only, out_dir=tmp_path / "name_only", conn=conn)

    matched = [m.uid for m in res.name_matches]
    gold_match = ground_truth["foreign_name_match_uids"][name_only.designation_id]
    # The matched account is absent from EVERY domestic (sdn_style) exposure set.
    domestic_ids = [d["designation_id"] for d in ground_truth["designations"]
                    if d["list_type"] == "sdn_style"]
    in_any_domestic_exposure = any(
        ring["SIBLING"] in ground_truth["designation_exposed_uids"][did]
        for did in domestic_ids
    )
    name_rows = [r for r in res.worksheet
                 if r.recommended_action == "flags_name_match_for_identity_review"]

    scorecard = {
        "regime": name_only.source_regime,
        "designated_addresses": len(name_only.designated_addresses),
        "name_matches": matched,
        "matches_gold": matched == gold_match,
        "flow_exposure": len(res.exposure.exposed),
        "adjacency": len(res.exposure.adjacent),
        "name_match_worksheet_rows": len(name_rows),
        "matched_absent_from_domestic_exposure": not in_any_domestic_exposure,
        "audit_verified": res.audit_verified,
    }
    with capsys.disabled():
        print("\nPhase 8 sweep scorecard (cross-list granularity / name-only foreign match):")
        for k, v in scorecard.items():
            print(f"  {k}: {v}")

    # The conditional empty-address path, end to end: a name-only listing.
    assert name_only.designated_addresses == []
    # Surfaced ONLY by the name screen: matched, no flow, no adjacency.
    assert matched == gold_match == [ring["SIBLING"]]
    assert res.exposure.exposed == [] and res.exposure.adjacent == []
    assert len(name_rows) == 1 and name_rows[0].uid == ring["SIBLING"]
    # Additive, not duplicative — absent from every domestic exposure set.
    assert not in_any_domestic_exposure
    assert res.audit_verified
