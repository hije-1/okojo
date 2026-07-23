"""Phase 2 evaluation harness — capability scorecard vs ground_truth.json.

Mirrors ``test_phase1_eval.py``. Slice 3 seeds it with the On-chain Risk Scorer;
later Phase 2 slices extend this scorecard (tell miner, SDN screening, ...).

Run at ``max_hops=3`` for depth headroom (the ring is already fully reached at
hop 2). Recall < 1.0 would only appear at ``max_hops=1`` and would be an
*expander-coverage* statement, not a scorer defect.
"""

from __future__ import annotations

from okojo.eval import score
from okojo.orchestrator import run_case


def test_phase2_capability_scorecard(conn, trust_uid, ground_truth, tmp_path, capsys):
    res = run_case(trust_uid, conn=conn, out_dir=tmp_path, max_hops=3)

    # --- On-chain Risk Scorer: graded sanctioned exposure --------------------- #
    # exposed_uids (money-flow, {transaction,controls} only) is scored against the
    # generator's independent reachability key — a genuine cross-check, not a tautology.
    gold_exposure = set(ground_truth["sanctioned_exposure_uids"])
    exposure = score(res.risk.exposed_uids, gold_exposure)

    scorecard = {
        "risk_scorer_exposure": str(exposure),
        "risk_bands": res.risk.band_counts(),
        "risk_gas_only": len(res.risk.gas_only_uids()),
        "audit_verified": res.audit_verified,
    }
    with capsys.disabled():
        print("\nPhase 2 capability scorecard (TRUST case):")
        for k, v in scorecard.items():
            print(f"  {k}: {v}")

    # --- assertions ----------------------------------------------------------- #
    # headline: full recall, zero false positives against the reachability key
    assert exposure.recall == 1.0
    assert exposure.fp == 0
    assert exposure.precision == 1.0
    # the risk_scorer step is recorded in the tamper-evident chain
    actions = {(r["actor"], r["action"]) for r in res.audit_records}
    assert ("risk_scorer", "tool_call") in actions
    assert ("risk_scorer", "scored") in actions
    assert res.audit_verified
