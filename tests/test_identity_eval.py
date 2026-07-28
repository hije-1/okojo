"""Identity-resolution scorecard — variant name screen (Phase 8 Part II T1).

Calibrated framing (P8-B): the P/R/F1 below is a RECOVERY-CONSISTENCY CHECK over
the synthetic scenario, not a field-performance claim. The evidentiary weight is
in the named traps — the direct screen MISSES every planted customer (raw WRatio
< threshold) while the variant layer recovers exactly the definitional answer
key, and same-surname decoys are never matched (discrimination). Exact-set
assertions (P8-A); the answer key is definitional (which customer each designated
name refers to), never the screen's own output, so the recovery test is real.
"""

from __future__ import annotations

from okojo.eval.metrics import score
from okojo.sweep import designation_from_record, match_designated_name, run_sweep


def _identity_recs(conn, ground_truth):
    recs = {r["designation_id"]: r for r in conn.all_designations()}
    return {did: recs[did] for did in ground_truth["identity_variant_matches"]}


def test_identity_variant_screen_scorecard(conn, ground_truth, tmp_path, capsys):
    ivm = ground_truth["identity_variant_matches"]
    decoys = set(ground_truth["identity_variant_decoy_uids"])
    recs = _identity_recs(conn, ground_truth)

    predicted_all: set[int] = set()
    gold_all: set[int] = set()
    per_designation = {}
    for did, rec in recs.items():
        d = designation_from_record(rec)
        # Direct screen MUST miss (the whole point): a different romanization.
        direct = match_designated_name(conn, d)
        res = run_sweep(d, out_dir=tmp_path / did, conn=conn)
        var_uids = sorted(m.uid for m in res.variant_name_matches)
        gold = sorted(ivm[did])

        predicted_all.update(var_uids)
        gold_all.update(gold)
        # Every hit carries a fired rule path + a family + a score, and grounds
        # in a real account row.
        for m in res.variant_name_matches:
            assert m.rule_path and m.rule_families and m.score >= 85.0
            assert m.provenance and all(p.source == "accounts" for p in m.provenance)
        per_designation[did] = {
            "designated_name": d.designated_name,
            "direct_hits": [x.uid for x in direct],
            "variant_hits": var_uids,
            "gold": gold,
            "rule_path": res.variant_name_matches[0].rule_path if res.variant_name_matches else [],
        }
        # P8-A exact set per designation + direct-screen-miss trap.
        assert var_uids == gold
        assert direct == []

    sc = score(predicted_all, gold_all)
    # Discrimination: no decoy is ever matched by the variant layer.
    decoy_leak = predicted_all & decoys

    with capsys.disabled():
        print("\nIdentity-resolution scorecard (variant name screen):")
        print(f"  variant_recovery: {sc}")
        print(f"  decoy_leak (must be empty): {sorted(decoy_leak)}")
        for did, row in per_designation.items():
            print(f"  {did} {row['designated_name']!r}: direct={row['direct_hits']} "
                  f"variant={row['variant_hits']} gold={row['gold']} path={row['rule_path']}")

    assert sc.recall == 1.0 and sc.precision == 1.0 and sc.fp == 0
    assert not decoy_leak
    assert predicted_all == gold_all
