"""Beneficial-owner + officer walk scorecard (Phase 8 Part II T3b).

Calibrated framing (P8-B): the exact-set checks below are a consistency check
over the synthetic scenario, not a field-performance claim. The evidentiary
weight is in the named traps — a company owned at/above the control threshold
PROPAGATES while a below-threshold stake does NOT; a name-only officer with no
resolvable footprint is FICTITIOUS while a name-only officer whose name resolves
is NOT; an appointment dated after the designation is a CONTROL CHANGE while a
pre-designation one is not. Ownership/officer edges are a DISTINCT edge type and
add zero USDT exposure. The answer keys are definitional; walk_ownership (run
through the real sweep) recomputes them, so the check is real, never circular.
"""

from __future__ import annotations

import json

from okojo.eval.metrics import score
from okojo.sweep import designation_from_record, run_sweep

_DES = "DES-2026-0005"          # the resolved true-hit party seeding the T3 walk


def _run(conn, did, tmp_path):
    recs = {r["designation_id"]: r for r in conn.all_designations()}
    d = designation_from_record(recs[did])
    return run_sweep(d, out_dir=tmp_path / did, conn=conn)


def test_ownership_walk_scorecard(conn, ground_truth, tmp_path, capsys):
    res = _run(conn, _DES, tmp_path)
    ow = res.ownership

    # Exact-set over the three findings (each keyed by its definitional answer).
    pred = set()
    gold = set()
    for uid in ground_truth["ownership_propagated_uids"]:
        gold.add(("propagation", str(uid)))
    for aid in ground_truth["fictitious_executive_flags"]:
        gold.add(("fictitious", aid))
    for aid in ground_truth["post_designation_control_changes"]:
        gold.add(("control_change", aid))
    for p in ow.propagations:
        pred.add(("propagation", str(p.company_uid)))
    for f in ow.fictitious_executives:
        pred.add(("fictitious", f.appointment_id))
    for c in ow.control_changes:
        pred.add(("control_change", c.appointment_id))

    sc = score(pred, gold)

    # DISTINCT-EDGE: the ownership walk carries zero flow exposure.
    assert ow.exposure_usdt() == 0.0

    # The walk is stamped into the chain exactly once, and the chain verifies.
    stamped = [r for r in res.audit_records
               if r["actor"] == "remediation_sweep" and r["action"] == "ownership_walk"]
    assert len(stamped) == 1
    assert res.audit_verified

    # Grounded: every finding cites real evidence rows.
    from okojo.sar import GroundingResolver
    resolver = GroundingResolver(conn)
    for finding in (list(ow.propagations) + list(ow.fictitious_executives)
                    + list(ow.control_changes)):
        assert finding.provenance
        assert all(resolver.resolves(p) for p in finding.provenance)

    with capsys.disabled():
        print("\nPhase 8 ownership walk scorecard (beneficial-owner + officer "
              "-- exact-set consistency):")
        print(f"  propagations:     {[p.company_uid for p in ow.propagations]}")
        print(f"  fictitious execs: {[f.appointment_id for f in ow.fictitious_executives]}")
        print(f"  control changes:  {[c.appointment_id for c in ow.control_changes]}")
        print(f"  ownership_walk: {sc}")

    assert sc.precision == 1.0 and sc.recall == 1.0 and sc.f1 == 1.0
    assert pred == gold
    # All three finding types are exercised by the planted structure.
    assert {t for (t, _k) in gold} == {"propagation", "fictitious", "control_change"}


def test_below_threshold_company_not_propagated(conn, ground_truth, tmp_path):
    """Discrimination: the party also owns a company BELOW the control threshold;
    it is never propagated."""
    res = _run(conn, _DES, tmp_path)
    party = ground_truth["identity_variant_matches"][_DES][0]
    all_owned = {int(r["company_uid"]) for r in conn.beneficial_ownership()
                 if int(r["owner_uid"]) == party}
    propagated = {p.company_uid for p in res.ownership.propagations}
    assert propagated < all_owned, "expected an owned-but-below-threshold company"
    assert propagated == set(ground_truth["ownership_propagated_uids"])


def test_domestic_designation_runs_no_ownership_walk(conn, sweep_designations, tmp_path):
    """A designation with no resolved corporate footprint runs an empty walk and
    stamps NO ownership_walk record — its chain gains nothing from T3."""
    live, decoy = sweep_designations
    for d in (live, decoy):
        res = run_sweep(d, out_dir=tmp_path / d.designation_id, conn=conn)
        assert res.ownership.is_empty()
        assert not [r for r in res.audit_records if r["action"] == "ownership_walk"]
        assert res.audit_verified


def test_dismissed_collision_seeds_no_walk(conn, tmp_path):
    """The same-name collision (DES-0007, corroboration-dismissed) seeds no
    ownership walk — designation status never propagates from a dismissed party."""
    recs = {r["designation_id"]: r for r in conn.all_designations()}
    res = run_sweep(designation_from_record(recs["DES-2026-0007"]),
                    out_dir=tmp_path / "collision", conn=conn)
    assert res.ownership.is_empty()
    assert not [r for r in res.audit_records if r["action"] == "ownership_walk"]
