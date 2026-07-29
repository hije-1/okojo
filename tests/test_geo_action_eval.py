"""Geo-action proposal scorecard — the TERRITORY sweep's 7th decision (P8-III U2b).

Calibrated framing (P8-B): the P/R/F1 below is an EXACT-SET consistency check
over the synthetic scenario, not a field-performance claim. The evidentiary
weight is in the discrimination — the totality rule proposes THREE DIFFERENT
actions across the surfaced personas (an EDD RFI for the ambiguous ones, a
withdrawal-only restriction for the lone strong carrier signal, a full block for
the multi-signal resident), and the ambiguous traveller FALLS OUT of the rule:
flipping his residency card from expired to valid moves his proposal off the EDD
RFI by arithmetic alone.

The expected proposal per persona is POLICY-DERIVED (the published geo-action
bands over each persona's planted totality), authored here rather than in the
generator — the generator emits facts; the eval owns policy expectations (the
same split as decision_trace_gold / sar_rubric_gold). ``run_sweep`` recomputes
each proposal from the dossier, so the check is real, never circular.

P8-G demonstrated falsification: test_ambiguous_traveller_valid_expiry_moves_off_
edd_rfi perturbs the traveller's input end-to-end and asserts the proposal moves
off EDD RFI (run red against the un-perturbed expired baseline, then green — see
the slice report).
"""

from __future__ import annotations

import csv
import json
import shutil

from okojo.eval.metrics import score
from okojo.sweep import designation_from_record, run_sweep

# Policy-derived expected proposal per planted persona (by stable entity_name),
# each from the published geo-action bands over the persona's planted totality:
#   Omar Feldt   (single ordinary IP, N=2)                 -> EDD RFI
#   Yusuf Halden (6 signals incl. carrier+residence, N=12) -> full block
#   Priya Vantol (declared residence only, N=2)            -> EDD RFI
#   Tomas Redlin (region-exclusive carrier only, N=3)      -> withdrawal-only
#   Emil Navarrete (VPN-slip minus EXPIRED counter, N=2)   -> EDD RFI
_EXPECTED_PROPOSAL = {
    "Omar Feldt": "propose_edd_rfi",
    "Yusuf Halden": "propose_full_block_and_escalate",
    "Priya Vantol": "propose_edd_rfi",
    "Tomas Redlin": "propose_withdrawal_only_restriction",
    "Emil Navarrete": "propose_edd_rfi",
}


def _territory_designation(conn):
    recs = {r["designation_id"]: r for r in conn.all_designations()}
    tid = next(i for i in recs if str(recs[i]["list_type"]) == "territory")
    return designation_from_record(recs[tid])


def test_geo_action_scorecard(conn, tmp_path, capsys):
    d = _territory_designation(conn)
    res = run_sweep(d, out_dir=tmp_path / "geo", conn=conn)

    predicted = {(p.uid, p.outcome) for p in res.geo_proposals}
    gold = {(p.uid, _EXPECTED_PROPOSAL[p.entity_name]) for p in res.geo_proposals}
    sc = score(predicted, gold)

    with capsys.disabled():
        print("\nPhase 8 geo-action proposal scorecard (TERRITORY sweep -- exact-set):")
        for p in sorted(res.geo_proposals, key=lambda x: x.uid):
            print(f"  uid={p.uid} {p.entity_name:16} N={p.net_presence_score:>3} "
                  f"{p.outcome}  ({p.status})")
        print(f"  geo_action: {sc}")

    assert sc.precision == 1.0 and sc.recall == 1.0 and sc.f1 == 1.0
    # Three cases -> three DIFFERENT proposals (the P8-A discrimination).
    distinct = {p.outcome for p in res.geo_proposals}
    assert distinct == {
        "propose_edd_rfi",
        "propose_withdrawal_only_restriction",
        "propose_full_block_and_escalate",
    }
    # Every proposal is REVIEW-tier: drafted for a human, never executed.
    assert all(p.status == "drafted_pending_human_review" for p in res.geo_proposals)
    assert res.audit_verified


def test_geo_action_discrimination_subcases(conn, ground_truth, tmp_path):
    """The carrier-only, VPN-slip, and multi-signal-resident cases each earn a
    distinct proposal from the totality -- the evidentiary weight behind the
    scorecard."""
    d = _territory_designation(conn)
    res = run_sweep(d, out_dir=tmp_path / "geo", conn=conn)
    by_uid = {p.uid: p for p in res.geo_proposals}

    # Carrier-only (a lone high-value signal, N=3) -> a withdrawal-only proposal,
    # NOT the ambiguous RFI: a region-exclusive carrier is a full locator.
    (carrier_uid,) = ground_truth["geo_carrier_only_uids"]
    assert by_uid[carrier_uid].outcome == "propose_withdrawal_only_restriction"

    # VPN-slip traveller (high-value slip minus an EXPIRED counter, N=2) -> EDD
    # RFI, with the subject-facing ask drafted and anti-tipping-off-cleared.
    (slip_uid,) = ground_truth["geo_vpn_slip_uids"]
    assert by_uid[slip_uid].outcome == "propose_edd_rfi"
    assert by_uid[slip_uid].rfi_text is not None
    assert by_uid[slip_uid].rfi_suppressed_reason is None

    # Exactly one persona reaches the full-block band -- the multi-signal
    # resident; the outcome multiset is the discrimination.
    outcomes = sorted(p.outcome for p in res.geo_proposals)
    assert outcomes == [
        "propose_edd_rfi", "propose_edd_rfi", "propose_edd_rfi",
        "propose_full_block_and_escalate", "propose_withdrawal_only_restriction",
    ]


def test_edd_rfi_text_is_anti_tipping_off_clean(conn, tmp_path):
    """Every drafted subject-facing EDD RFI passes the same guard the case
    pipeline uses -- it names no territory, no match, no method, no list."""
    from okojo.agency import assert_no_tipping_off

    d = _territory_designation(conn)
    res = run_sweep(d, out_dir=tmp_path / "geo", conn=conn)
    drafted = [p for p in res.geo_proposals if p.rfi_text is not None]
    assert drafted, "the EDD-RFI personas should have drafted subject-facing text"
    for p in drafted:
        assert_no_tipping_off(p.rfi_text)  # raises if it could tip off
        assert p.entity_name in p.rfi_text  # addressed to the subject


def test_ambiguous_traveller_valid_expiry_moves_off_edd_rfi(
        conn, ground_truth, data_dir, tmp_path):
    """P8-G demonstrated falsification (end-to-end). The traveller lands on EDD
    RFI because his foreign residency card is EXPIRED (it cannot rebut the
    VPN-slip). Flip that ONE input to a VALID expiry and the SAME rule moves his
    proposal OFF the EDD RFI (to no_action) -- he is not special-cased. Perturbs
    the input at the CSV, then runs the full sweep.

    (Run red first against the un-perturbed expired baseline -- where the proposal
    IS EDD RFI, so the `!= propose_edd_rfi` assertion fails -- then green; the red
    output is quoted in the slice report.)"""
    (traveller_uid,) = ground_truth["geo_vpn_slip_uids"]

    # Baseline (expired): the traveller proposes an EDD RFI.
    d = _territory_designation(conn)
    base = run_sweep(d, out_dir=tmp_path / "base", conn=conn)
    base_by_uid = {p.uid: p for p in base.geo_proposals}
    assert base_by_uid[traveller_uid].outcome == "propose_edd_rfi"

    # Perturb ONE input: copy the scenario and flip the traveller's residency
    # card expiry from expired (2024) to valid (2030).
    pert_dir = tmp_path / "perturbed"
    shutil.copytree(data_dir, pert_dir)
    vpath = pert_dir / "kyc_artifact_validity.csv"
    rows = list(csv.DictReader(vpath.open(encoding="utf-8")))
    for r in rows:
        if int(r["uid"]) == traveller_uid:
            r["expiry_date"] = "2030-01-01"
    with vpath.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["uid", "artifact_type",
                                          "issuing_geography", "expiry_date"])
        w.writeheader()
        w.writerows(rows)

    from okojo.connectors import Connectors
    pconn = Connectors(data_dir=pert_dir)
    try:
        pres = run_sweep(_territory_designation(pconn),
                         out_dir=tmp_path / "pert_sweep", conn=pconn)
    finally:
        pconn.close()
    pert_by_uid = {p.uid: p for p in pres.geo_proposals}

    # The valid card fully rebuts the lone slip -> the proposal moves OFF EDD RFI.
    assert pert_by_uid[traveller_uid].outcome != "propose_edd_rfi"
    assert pert_by_uid[traveller_uid].outcome == "no_action_totality_resolves"
    # ...and no subject-facing RFI is drafted for a resolved no_action review.
    assert pert_by_uid[traveller_uid].rfi_text is None


def test_no_action_stays_surfaced_with_full_dossier(conn, ground_truth, tmp_path):
    """PM Rider A: a no_action_totality_resolves proposal is a RESOLVED review,
    never a silent dismissal -- the account stays surfaced in both the dossier
    set and the proposal set, carrying its full dossier. (Reached here by the
    perturbation path; asserted directly on a constructed dossier so the property
    holds independently of which persona triggers it.)"""
    from okojo.geo import GeoDossier, GeoSignal, GeoCounterEvidence
    from okojo.provenance import Provenance
    from okojo.sweep import build_geo_proposals

    prov = next(iter(conn.all_accounts())).provenance
    rebutted = GeoDossier(
        uid=999001, entity_name="Constructed Rebutted",
        signals=[GeoSignal(signal_id="vpn_slip", value="X", detail="possible presence",
                           weight_class="high_value", provenance=prov)],
        counter_evidence=[GeoCounterEvidence(
            artifact_type="residency_card", issuing_geography="AE",
            staleness="valid", counterweight="full",
            detail="argues against presence", provenance=prov)],
    )
    d = _territory_designation(conn)
    proposals = build_geo_proposals(conn, d, [rebutted])
    assert len(proposals) == 1
    p = proposals[0]
    assert p.outcome == "no_action_totality_resolves"
    assert not p.is_action              # proposes nothing...
    assert p.uid == 999001              # ...but is still surfaced (Rider A)
    assert p.provenance                 # ...with its full dossier provenance
    assert p.rfi_text is None and p.rfi_suppressed_reason is None


def test_geo_proposal_stamp_conditional_on_territory(conn, tmp_path):
    """The geo_proposal record lands once in a territory chain and the chain
    verifies; a DOMESTIC sweep carries no geo_proposal stamp (the stage is
    conditional, so non-territory chains are byte-unchanged)."""
    d = _territory_designation(conn)
    res = run_sweep(d, out_dir=tmp_path / "geo", conn=conn)
    stamps = [r for r in res.audit_records
              if r["actor"] == "remediation_sweep" and r["action"] == "geo_proposal"]
    assert len(stamps) == 1
    detail = json.loads(stamps[0]["detail"])
    assert {x["uid"] for x in detail["proposals"]} == {p.uid for p in res.geo_proposals}
    assert res.audit_verified

    recs = {r["designation_id"]: r for r in conn.all_designations()}
    dom_id = next(i for i in recs if str(recs[i]["list_type"]) == "sdn_style"
                  and str(recs[i]["designated_addresses"]))
    dom = run_sweep(designation_from_record(recs[dom_id]),
                    out_dir=tmp_path / "dom", conn=conn)
    assert not [r for r in dom.audit_records if r["action"] == "geo_proposal"]
    assert dom.geo_proposals == []
