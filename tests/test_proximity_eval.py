"""Proximity-ring scorecard (Phase 8 Part II T4b).

Calibrated framing (P8-B): an exact-set consistency check over the synthetic
scenario, not a field-performance claim. The evidentiary weight is in the traps —
a DORMANT relative surfaces exactly as loudly as an active one, an ACTIVE
unrelated stranger does not surface at all, and the ring is REVIEW-tier (zero
flow exposure). The answer key is definitional; build_proximity_ring (run through
the real sweep) recomputes it, so the check is real, never circular.
"""

from __future__ import annotations

from okojo.eval.metrics import score
from okojo.sweep import designation_from_record, run_sweep

_DES = "DES-2026-0005"


def _run(conn, did, tmp_path):
    recs = {r["designation_id"]: r for r in conn.all_designations()}
    return run_sweep(designation_from_record(recs[did]), out_dir=tmp_path / did, conn=conn)


def test_proximity_ring_scorecard(conn, ground_truth, tmp_path, capsys):
    res = _run(conn, _DES, tmp_path)
    ring = res.proximity

    gold = set(ground_truth["proximity_ring_uids"][_DES])
    pred = set(ring.member_uids())
    sc = score(pred, gold)

    # REVIEW-tier, never exposure.
    assert ring.exposure_usdt() == 0.0
    assert not (pred & set(res.exposure.exposed_uids()))

    # Dormancy trap: a dormant (non-active) member is present and surfaces on the
    # same footing as active members.
    statuses = {m.uid: m.account_status for m in ring.members}
    assert any(s != "active" for s in statuses.values()), "expected a dormant member"

    # Stamped once; the chain verifies; findings grounded.
    stamped = [r for r in res.audit_records
               if r["actor"] == "remediation_sweep" and r["action"] == "proximity_ring"]
    assert len(stamped) == 1
    assert res.audit_verified
    from okojo.sar import GroundingResolver
    resolver = GroundingResolver(conn)
    for m in ring.members:
        assert all(resolver.resolves(p) for p in m.provenance)

    with capsys.disabled():
        print("\nPhase 8 proximity ring scorecard (relatives/associates -- "
              "exact-set consistency):")
        for m in ring.members:
            print(f"  uid={m.uid} status={m.account_status:9s} "
                  f"signals={[s.signal_id for s in m.primary_signals]}")
        print(f"  proximity_ring: {sc}")

    assert sc.precision == 1.0 and sc.recall == 1.0 and sc.f1 == 1.0
    assert pred == gold


def test_active_stranger_excluded(conn, ground_truth, tmp_path):
    """The active unrelated stranger persona never enters the ring."""
    res = _run(conn, _DES, tmp_path)
    ring_uids = set(res.proximity.member_uids())
    strangers = [int(a["uid"]) for a in conn.all_accounts()
                 if str(a["role_in_ring"]) == "proximity_review_subject"
                 and str(a["account_status"]) == "active"
                 and int(a["uid"]) not in ring_uids]
    assert strangers, "expected an active stranger excluded from the ring"


def test_domestic_designation_runs_no_proximity(conn, sweep_designations, tmp_path):
    """A designation with no resolved individual party runs an empty ring and
    stamps NO proximity_ring record."""
    live, decoy = sweep_designations
    for d in (live, decoy):
        res = run_sweep(d, out_dir=tmp_path / d.designation_id, conn=conn)
        assert res.proximity.is_empty()
        assert not [r for r in res.audit_records if r["action"] == "proximity_ring"]


def test_dismissed_collision_seeds_no_ring(conn, tmp_path):
    """The corroboration-dismissed collision (DES-0007) seeds no proximity ring."""
    res = _run(conn, "DES-2026-0007", tmp_path)
    assert res.proximity.is_empty()
    assert not [r for r in res.audit_records if r["action"] == "proximity_ring"]
