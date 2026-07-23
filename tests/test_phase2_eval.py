"""Phase 2 evaluation harness — capability scorecard vs ground_truth.json.

Mirrors ``test_phase1_eval.py``, one row per Phase-2 capability, each scored with
``okojo.eval.score`` against its gold key. This consolidates (does not replace)
the standalone unit tests in ``test_network.py`` / ``test_remarks.py`` /
``test_risk_scorer.py`` into one printed scorecard.

Run at ``max_hops=3`` for depth headroom (the ring is already fully reached at
hop 2). Recall < 1.0 would only appear at ``max_hops=1`` and would be an
*expander-coverage* statement, not a capability defect.
"""

from __future__ import annotations

from okojo.eval import score
from okojo.orchestrator import run_case


def test_phase2_capability_scorecard(conn, trust_uid, ground_truth, tmp_path, capsys):
    res = run_case(trust_uid, conn=conn, out_dir=tmp_path, max_hops=3)

    # --- On-chain Risk Scorer: graded sanctioned exposure --------------------- #
    # exposed_uids (money-flow, {transaction,controls} only) is scored against the
    # generator's independent reachability key — a genuine cross-check, not a tautology.
    exposure = score(res.risk.exposed_uids, ground_truth["sanctioned_exposure_uids"])

    # --- Network Expander: member recall -------------------------------------- #
    # precision reflects noise accounts reached at hop 3 (not a defect) — recall is
    # the headline (every true ring member is found).
    network = score(res.expansion.reached_account_uids, ground_truth["network_member_uids"])

    # --- Remark / Tell Miner: betraying-remark recall ------------------------- #
    # the miner also emits control_alias tells, so fp can be > 0 vs the betraying
    # set — recall is the honest headline.
    remark = score(
        {h.tx_id for h in res.tells},
        {b["tx_id"] for b in ground_truth["betraying_remarks"]},
    )

    # --- SDN / alias screening ------------------------------------------------ #
    alias = score(
        {h.uid for h in res.alias_hits},
        {m["uid"] for m in ground_truth["sdn_alias_matches"]},
    )

    # --- Gas-funding controller-collapse -------------------------------------- #
    gas = score(
        {(l["funder_address"], l["funded_address"]) for l in res.expansion.gas_funding_links},
        {(g["funder_address"], g["funded_address"]) for g in ground_truth["gas_funding_tells"]},
    )

    scorecard = {
        "risk_scorer_exposure": str(exposure),
        "risk_bands": res.risk.band_counts(),
        "risk_gas_only": len(res.risk.gas_only_uids()),
        "network_member": str(network),
        "remark_miner": str(remark),
        "sdn_alias_screening": str(alias),
        "gas_funding_linkage": str(gas),
        "audit_verified": res.audit_verified,
    }
    with capsys.disabled():
        print("\nPhase 2 capability scorecard (TRUST case):")
        for k, v in scorecard.items():
            print(f"  {k}: {v}")

    # --- assertions ----------------------------------------------------------- #
    # On-chain Risk Scorer: full recall, zero false positives against the reachability key.
    assert exposure.recall == 1.0
    assert exposure.fp == 0
    assert exposure.precision == 1.0
    # Network Expander: every true ring member reached.
    assert network.recall == 1.0
    # Remark Miner: every betraying remark caught.
    assert remark.recall == 1.0
    # SDN/alias screening: transliteration variants caught, decoys rejected — perfect.
    assert alias.precision == 1.0 and alias.recall == 1.0
    # Gas-funding linkage: every funder->funded hop recovered, no spurious links.
    assert gas.precision == 1.0 and gas.recall == 1.0
    # the risk_scorer step is recorded in the tamper-evident chain
    actions = {(r["actor"], r["action"]) for r in res.audit_records}
    assert ("risk_scorer", "tool_call") in actions
    assert ("risk_scorer", "scored") in actions
    assert res.audit_verified
