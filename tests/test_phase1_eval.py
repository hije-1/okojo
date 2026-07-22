"""Phase 1 evaluation harness — scores each capability against ground_truth.json.

This is the "every capability ships with an eval" deliverable, kept light for a
walking skeleton. It scores, on the TRUST case:
  * Profile Aggregator — did it surface the subject's shared-device group?
  * Network Expander    — recall of network members; sanctioned endpoints reached.
  * Remark Miner        — recall of the betraying remarks.
  * Advisory Matcher    — did it trigger on the RFI key terms?
"""

from __future__ import annotations

from okojo.orchestrator import run_case


def test_phase1_capability_scorecard(conn, trust_uid, ground_truth, tmp_path, capsys):
    res = run_case(trust_uid, conn=conn, out_dir=tmp_path, max_hops=2)

    # --- Profile Aggregator: subject's shared-device group is surfaced -------- #
    gt_shared_uids = {
        uid for uids in ground_truth["shared_devices"].values()
        if trust_uid in uids for uid in uids if uid != trust_uid
    }
    # derive the co-users the aggregator named from its shared-device statements
    flagged_uids: set[int] = set()
    for a in res.profile.anomalies:
        if a.code == "shared_device_fingerprint":
            for tok in a.statement.replace(",", " ").split():
                if tok.startswith("uid:"):
                    digits = tok[4:].strip(".")
                    if digits.isdigit():
                        flagged_uids.add(int(digits))
    shared_recall = (
        len(gt_shared_uids & flagged_uids) / len(gt_shared_uids) if gt_shared_uids else 1.0
    )

    # --- Network Expander: member recall + sanctioned reach ------------------- #
    members = set(ground_truth["network_member_uids"])
    reached = set(res.expansion.reached_account_uids)
    net_recall = len(members & reached) / len(members)
    sanctioned_reached = len(res.expansion.sanctioned_addresses_reached)
    sanctioned_total = len(ground_truth["sanctioned_addresses_synthetic"])

    # --- Remark Miner: betraying-remark recall -------------------------------- #
    betraying = {b["tx_id"] for b in ground_truth["betraying_remarks"]}
    found = {h.tx_id for h in res.tells}
    remark_recall = len(betraying & found) / len(betraying)

    # --- Advisory Matcher: triggered on RFI ----------------------------------- #
    advisory_hit = res.advisory is not None and "petroleum" in res.advisory.matched_terms

    scorecard = {
        "profile_shared_device_recall": round(shared_recall, 3),
        "network_member_recall": round(net_recall, 3),
        "sanctioned_reached": f"{sanctioned_reached}/{sanctioned_total}",
        "remark_recall": round(remark_recall, 3),
        "advisory_triggered": advisory_hit,
        "sar_grounded": res.sar.ungrounded() == [],
        "audit_verified": res.audit_verified,
    }
    with capsys.disabled():
        print("\nPhase 1 capability scorecard (TRUST case):")
        for k, v in scorecard.items():
            print(f"  {k}: {v}")

    # --- assertions (skeleton-level thresholds) ------------------------------- #
    assert shared_recall >= 0.5
    assert net_recall >= 0.8
    assert sanctioned_reached >= 1
    assert remark_recall == 1.0
    assert advisory_hit
    assert res.sar.ungrounded() == []
    assert res.audit_verified
