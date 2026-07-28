"""Corroboration scorecard — identity match vs published identifiers (Part II T2).

Calibrated framing (P8-B): the P/R/F1 below is an EXACT-SET consistency check
over the synthetic scenario, not a field-performance claim. The evidentiary
weight is in the named traps — a cross-script true hit whose document number
matches CORROBORATES; a name-only foreign listing with no disqualifying
identifier is routed to a HUMAN; a same-name collision whose date of birth,
nationality, and document number all differ is DISMISSED, with the mismatched
fields recorded. The answer key is definitional (the disposition each match
should resolve to); decide_corroboration recomputes it from the two identity
tables, so the check is real, never circular.
"""

from __future__ import annotations

import json

from okojo.eval.metrics import score
from okojo.sweep import designation_from_record, run_sweep


def test_corroboration_scorecard(conn, ground_truth, tmp_path, capsys):
    outcomes = ground_truth["corroboration_outcomes"]
    reasons = ground_truth["corroboration_dismissal_reasons"]
    recs = {r["designation_id"]: r for r in conn.all_designations()}

    predicted: set[tuple] = set()
    gold: set[tuple] = set()
    lines = []
    for did, uid_map in sorted(outcomes.items()):
        d = designation_from_record(recs[did])
        res = run_sweep(d, out_dir=tmp_path / did, conn=conn)
        by_uid = {rec.evidence["candidate_uid"]: rec for rec in res.corroboration}

        for uid_str, exp in uid_map.items():
            uid = int(uid_str)
            gold.add((did, uid, exp))
            rec = by_uid.get(uid)
            assert rec is not None, f"no corroboration decision for {did}:{uid}"
            predicted.add((did, uid, rec.outcome))

            # Grounded: the decision cites the KYC row and the identifier row it
            # compared, and both resolve to real evidence rows.
            kyc = conn.kyc_identity_attributes_for(uid)
            idr = conn.designation_identifier_for(did)
            assert kyc is not None and idr is not None
            assert rec.provenance == [kyc.provenance.cite(), idr.provenance.cite()]

            # Dismissals carry their reason (the mismatched identifier fields).
            if rec.outcome == "name_only_dismissed":
                assert rec.evidence["mismatched_fields"] == reasons[did]
                assert rec.rationale and rec.plain_language

            # Each decision is stamped once and round-trips to the record.
            stamped = [r for r in res.audit_records
                       if r["actor"] == "remediation_sweep"
                       and r["action"] == "corroboration_decision"
                       and r["target"] == f"{did}:uid:{uid}"]
            assert len(stamped) == 1
            assert json.loads(stamped[0]["detail"]) == rec.summary()

            lines.append(f"  {did} uid={uid}: {rec.outcome:26s} "
                         f"(expect {exp}) "
                         f"{'OK' if rec.outcome == exp else 'MISMATCH'}")
        assert res.audit_verified

    sc = score(predicted, gold)
    with capsys.disabled():
        print("\nPhase 8 corroboration scorecard (identity match vs published "
              "identifiers -- exact-set consistency):")
        for ln in lines:
            print(ln)
        print(f"  corroboration: {sc}")
        print(f"  dismissal_reasons: {json.dumps(reasons)}")

    assert sc.precision == 1.0 and sc.recall == 1.0 and sc.f1 == 1.0
    assert predicted == gold

    # Coverage: all three dispositions are exercised by the planted cases.
    assert {o for (_did, _uid, o) in gold} == {
        "corroborated_true_hit", "possible_match_needs_human", "name_only_dismissed"}


def test_domestic_designation_records_no_corroboration(conn, sweep_designations, tmp_path):
    """A designation with no published identifiers to corroborate against runs
    no corroboration and stamps no corroboration record — so its chain is
    byte-unchanged from Part I (corroboration is purely additive for it)."""
    live, decoy = sweep_designations
    for d in (live, decoy):
        res = run_sweep(d, out_dir=tmp_path / d.designation_id, conn=conn)
        assert res.corroboration == []
        assert not [r for r in res.audit_records
                    if r["action"] == "corroboration_decision"]
        assert res.audit_verified


def test_collision_is_distinct_from_true_hit(conn, ground_truth, tmp_path):
    """Discrimination: the same-name collision (DES-0007) and the true hit
    (DES-0005) share a Cyrillic name family yet resolve to OPPOSITE dispositions
    — the whole point of corroborating on identity attributes, not names."""
    recs = {r["designation_id"]: r for r in conn.all_designations()}

    def _outcome(did):
        d = designation_from_record(recs[did])
        res = run_sweep(d, out_dir=tmp_path / did, conn=conn)
        return {c.evidence["candidate_uid"]: c.outcome for c in res.corroboration}

    hit = _outcome("DES-2026-0005")
    collision = _outcome("DES-2026-0007")
    assert set(hit.values()) == {"corroborated_true_hit"}
    assert set(collision.values()) == {"name_only_dismissed"}
