"""Counterparty-lifecycle scorecard — the COUNTERPARTY_SERVICE sweep's 8th
decision (Phase 8 Part IV V1b).

Calibrated framing (P8-B): the P/R/F1 below is an EXACT-SET consistency check
over the synthetic scenario, not a field-performance claim. The evidentiary
weight is in the discrimination — the same rule proposes THREE DIFFERENT
dispositions across the exposed personas (unblock for the acknowledged-and-
stopped customer, hold_pending for the one who never acknowledged, offboard for
the repeat offender) and the clean control is absent — and in the two demonstrated
falsifications (remove the acknowledgment and the unblock proposal vanishes;
flip the recidivism flag and offboard becomes unblock).

The expected disposition per persona is POLICY-DERIVED (the published
counterparty_lifecycle rule over each persona's planted facts), authored here
rather than in the generator — the generator emits facts; the eval owns policy
expectations (the same split as decision_trace_gold / geo_action_eval).
``run_sweep`` recomputes each disposition from the evidence, so the check is real,
never circular.

THE HARD RULE — no auto-unblock: test_no_auto_unblock_* proves the pipeline
cannot write to either sanctions-hold table (a byte-snapshot across a full run
plus a static check that no sweep/lifecycle symbol writes them). Unblock exists
only as a proposal record.
"""

from __future__ import annotations

import csv
import hashlib
import json
import shutil
from pathlib import Path

from okojo.connectors import Connectors
from okojo.eval.metrics import score
from okojo.sweep import designation_from_record, run_sweep

# Policy-derived expected disposition per exposed persona (by ground-truth key):
#   Marta Kovanen  (post dealing, acknowledged, stopped)     -> propose_unblock
#   Denis Rojek    (post dealing, NO acknowledgment)         -> hold_pending
#   Aron Velitz    (post dealing + a PRIOR acknowledged cp)  -> propose_offboard
#   Hana Sorven    (no dealing with the counterparty)        -> ABSENT
_EXPECTED = {
    "UNBLOCK": "propose_unblock",
    "HOLD": "hold_pending",
    "OFFBOARD": "propose_offboard",
}


def _cp_designation(conn):
    recs = {r["designation_id"]: r for r in conn.all_designations()}
    cid = next(i for i in recs
               if str(recs[i]["list_type"]) == "counterparty_service")
    return designation_from_record(recs[cid])


def test_counterparty_lifecycle_scorecard(conn, ground_truth, tmp_path, capsys):
    d = _cp_designation(conn)
    res = run_sweep(d, out_dir=tmp_path / "cp", conn=conn)
    personas = ground_truth["counterparty_personas"]

    by_uid = {x.uid: x for x in res.lifecycle_dispositions}
    predicted = {(x.uid, x.outcome) for x in res.lifecycle_dispositions}
    gold = {(personas[k], _EXPECTED[k]) for k in _EXPECTED}
    sc = score(predicted, gold)

    with capsys.disabled():
        print("\nPhase 8 counterparty-lifecycle scorecard (COUNTERPARTY_SERVICE sweep -- exact-set):")
        for x in sorted(res.lifecycle_dispositions, key=lambda y: y.uid):
            print(f"  uid={x.uid} {x.state:22} {x.outcome:18} "
                  f"(ack={x.acknowledged} stop={x.stop_verified} repeat={x.repeat_offender})")
        print(f"  counterparty_lifecycle: {sc}")

    assert sc.precision == 1.0 and sc.recall == 1.0 and sc.f1 == 1.0
    # Three exposed customers -> three DIFFERENT dispositions (the discrimination).
    assert {x.outcome for x in res.lifecycle_dispositions} == {
        "propose_unblock", "propose_offboard", "hold_pending",
    }
    # The clean control never deals with the counterparty, so it is ABSENT from
    # both the notification set and the disposition set.
    clean = ground_truth["counterparty_clean_uid"]
    assert clean not in by_uid
    assert clean not in {n.uid for n in res.counterparty_notifications}
    assert res.audit_verified


def test_notifications_only_for_post_designation_dealers_and_guard_clean(
        conn, ground_truth, tmp_path):
    """Every post-designation dealer is drafted a notification; the clean control
    is not; and every drafted notification passes the anti-tipping-off guard and
    is drafted-pending-human-review (no send path)."""
    from okojo.agency import assert_no_tipping_off

    d = _cp_designation(conn)
    res = run_sweep(d, out_dir=tmp_path / "cp", conn=conn)

    drafted_uids = {n.uid for n in res.counterparty_notifications}
    assert drafted_uids == set(ground_truth["counterparty_exposed_uids"])
    assert not res.suppressed_counterparty_notifications
    for n in res.counterparty_notifications:
        assert_no_tipping_off(n.text)         # raises if it could tip off
        assert n.subject_name in n.text        # addressed to the subject
        assert d.designated_name in n.text     # names the public designation (sayable)
        assert n.status == "drafted_pending_human_review"


def test_lifecycle_stamp_conditional_on_counterparty_service(conn, tmp_path):
    """The counterparty_lifecycle + counterparty_notification records land once in
    a counterparty_service chain (and it verifies); a DOMESTIC sweep carries
    neither stamp and no dispositions (the stage is conditional, so non-
    counterparty chains are byte-unchanged)."""
    d = _cp_designation(conn)
    res = run_sweep(d, out_dir=tmp_path / "cp", conn=conn)
    kinds = [r["action"] for r in res.audit_records
             if r["actor"] == "remediation_sweep"]
    assert kinds.count("counterparty_lifecycle") == 1
    assert kinds.count("counterparty_notification") == 1
    assert res.audit_verified

    recs = {r["designation_id"]: r for r in conn.all_designations()}
    dom_id = next(i for i in recs if str(recs[i]["list_type"]) == "sdn_style"
                  and str(recs[i]["designated_addresses"]))
    dom = run_sweep(designation_from_record(recs[dom_id]),
                    out_dir=tmp_path / "dom", conn=conn)
    dom_kinds = [r["action"] for r in dom.audit_records]
    assert "counterparty_lifecycle" not in dom_kinds
    assert "counterparty_notification" not in dom_kinds
    assert dom.lifecycle_dispositions == []
    assert dom.counterparty_notifications == []


# --- THE HARD RULE: no auto-unblock -----------------------------------------

def test_no_auto_unblock_pipeline_never_writes_hold_tables(conn, data_dir, tmp_path):
    """A byte-snapshot of both sanctions-hold tables across a full run — over the
    counterparty_service designation AND a domestic one — proves the sweep never
    writes either table. The real-world precedent is an auto-unblock function
    investigators had to override per case; Okojo builds the opposite: unblock
    exists ONLY as a proposal record."""
    wh = data_dir / "sanctions_hold_warehouse.csv"
    adm = data_dir / "sanctions_hold_admin.csv"

    def _h(p: Path) -> str:
        return hashlib.sha256(p.read_bytes()).hexdigest()

    before = (_h(wh), _h(adm))
    recs = {r["designation_id"]: r for r in conn.all_designations()}
    run_sweep(_cp_designation(conn), out_dir=tmp_path / "cp", conn=conn)
    dom_id = next(i for i in recs if str(recs[i]["list_type"]) == "sdn_style"
                  and str(recs[i]["designated_addresses"]))
    run_sweep(designation_from_record(recs[dom_id]),
              out_dir=tmp_path / "dom", conn=conn)
    after = (_h(wh), _h(adm))
    assert before == after, "the sweep must never write the sanctions-hold tables"


def test_no_hold_write_symbol_in_sweep_or_lifecycle():
    """Static backstop: no module in the sweep package emits a CSV, the lifecycle
    module references no hold table at all, and the read-only connector exposes no
    hold-mutation method — so there is no code path that could unblock an account,
    only a proposal record."""
    import okojo.sweep as sweep_pkg
    import okojo.sweep.lifecycle as life

    pkg_dir = Path(sweep_pkg.__file__).parent
    for f in pkg_dir.glob("*.py"):
        src = f.read_text(encoding="utf-8")
        assert ".to_csv(" not in src, f"{f.name} writes a CSV"
    life_src = Path(life.__file__).read_text(encoding="utf-8")
    assert "sanctions_hold" not in life_src
    assert ".to_csv(" not in life_src and "open(" not in life_src

    mutators = [n for n in dir(Connectors)
                if any(v in n for v in ("set_hold", "write_hold", "update_hold",
                                        "block_account", "unblock"))]
    assert mutators == [], f"connector exposes a hold-mutation method: {mutators}"


# --- P8-G demonstrated falsifications (run red then green; outputs quoted) ----

def test_removing_marta_acknowledgment_vanishes_the_unblock_proposal(
        conn, ground_truth, data_dir, tmp_path):
    """P8-G #1 (end-to-end). Marta earns propose_unblock because she acknowledged
    the counterparty and stopped dealing. Remove her acknowledgment row and the
    SAME rule can no longer propose lifting the hold — her disposition falls to
    hold_pending (no acknowledgment on file).

    (Run red first against the un-perturbed ledger, where she IS propose_unblock,
    so the `!= propose_unblock` assertion fails; then green. The red output is
    quoted in the slice report.)"""
    marta = ground_truth["counterparty_personas"]["UNBLOCK"]

    base = run_sweep(_cp_designation(conn), out_dir=tmp_path / "base", conn=conn)
    base_by_uid = {x.uid: x for x in base.lifecycle_dispositions}
    assert base_by_uid[marta].outcome == "propose_unblock"

    # Perturb ONE input: copy the scenario and drop Marta's acknowledgment row.
    pert = tmp_path / "perturbed"
    shutil.copytree(data_dir, pert)
    apath = pert / "acknowledgments.csv"
    rows = [r for r in csv.DictReader(apath.open(encoding="utf-8"))
            if not (int(r["uid"]) == marta
                    and r["counterparty_designation_id"] == "DES-2026-0009")]
    with apath.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["uid", "counterparty_designation_id",
                                          "acknowledged_date"])
        w.writeheader()
        w.writerows(rows)

    pconn = Connectors(data_dir=pert)
    try:
        pres = run_sweep(_cp_designation(pconn),
                         out_dir=tmp_path / "pert_sweep", conn=pconn)
    finally:
        pconn.close()
    pert_by_uid = {x.uid: x for x in pres.lifecycle_dispositions}

    # The unblock proposal VANISHES: no acknowledgment -> hold_pending.
    assert pert_by_uid[marta].outcome != "propose_unblock"
    assert pert_by_uid[marta].outcome == "hold_pending"


def test_recidivism_flag_flip_moves_offboard_to_unblock(conn):
    """P8-G #2 (decision-level, Q5 precedence). A repeat offender who ALSO
    acknowledged and stopped still gets propose_offboard (recidivism dominates).
    Flip the recidivism flag off and the SAME rule proposes unblock instead —
    proving the precedence is load-bearing, not incidental.

    (Run red against repeat_offender=True, where the outcome is propose_offboard
    so the `== propose_unblock` assertion fails; then green. Quoted in the report.)"""
    from okojo.agency import decide_counterparty_lifecycle

    repeat = decide_counterparty_lifecycle(
        1, acknowledged=True, stop_verified=True, repeat_offender=True)
    assert repeat.outcome == "propose_offboard"

    flipped = decide_counterparty_lifecycle(
        1, acknowledged=True, stop_verified=True, repeat_offender=False)
    assert flipped.outcome == "propose_unblock"
