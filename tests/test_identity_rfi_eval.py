"""Identity-review RFI scorecard — the first subject-facing surface (Part II T5a).

Calibrated framing (P8-B): the P/R/F1 below is an EXACT-SET consistency check
over the synthetic scenario, not a field-performance claim. The evidentiary
weight is in the discrimination — only the candidate corroboration could neither
confirm nor dismiss (``possible_match_needs_human``) earns a subject-facing
identity-verification request; the corroborated true hit and the cleared
same-name collision earn NONE (asking either would be pointless or tipping-off).
The answer key is derived from the same definitional corroboration classification;
``draft_identity_review_rfis`` recomputes the RFI set, so the check is real.
"""

from __future__ import annotations

import json

from okojo.agency import assert_no_tipping_off
from okojo.eval.metrics import score
from okojo.sweep import designation_from_record, run_sweep
from okojo.sweep.identity_rfi import DRAFT_STATUS


def test_identity_review_rfi_scorecard(conn, ground_truth, tmp_path, capsys):
    gold_map = ground_truth["identity_review_rfi_uids"]
    recs = {r["designation_id"]: r for r in conn.all_designations()}

    predicted: set[tuple] = set()
    gold: set[tuple] = set()
    lines = []
    # Every identity designation is swept; the RFI must appear for exactly the
    # gold uids and NOWHERE else (both halves of the exact-set check).
    for did in sorted(recs):
        d = designation_from_record(recs[did])
        res = run_sweep(d, out_dir=tmp_path / did, conn=conn)

        for r in res.identity_rfis:
            predicted.add((did, r.uid))

            # drafted-pending-human-review is the only representable status.
            assert r.status == DRAFT_STATUS

            # Grounded + resolvable: the request cites the candidate's own KYC
            # identity-attributes row, and that pointer resolves to a real row.
            kyc = conn.kyc_identity_attributes_for(r.uid)
            assert kyc is not None
            assert r.citations == [kyc.provenance.cite()]
            assert r.provenance == [kyc.provenance]

            # Subject-facing text clears the anti-tipping-off guard (defense in
            # depth — the drafter already enforced it fail-closed).
            assert_no_tipping_off(r.text)
            low = r.text.lower()
            assert "designation" not in low and "sanction" not in low
            assert "match" not in low and "screen" not in low

            # The RFI is stamped once into the sweep's own chain.
            stamped = [rec for rec in res.audit_records
                       if rec["actor"] == "remediation_sweep"
                       and rec["action"] == "identity_review_rfi"]
            assert len(stamped) == 1
            drafted_ids = {x["id"] for x in json.loads(stamped[0]["detail"])["drafted"]}
            assert r.rfi_id in drafted_ids

            lines.append(f"  {did} uid={r.uid}: {r.rfi_id} ({r.status})")
        assert res.audit_verified

    for did, uids in gold_map.items():
        for uid_str in uids:
            gold.add((did, int(uid_str)))

    sc = score(predicted, gold)
    with capsys.disabled():
        print("\nPhase 8 identity-review RFI scorecard (subject-facing, drafted "
              "never sent -- exact-set consistency):")
        for ln in lines:
            print(ln)
        print(f"  identity_review_rfi: {sc}")
        print(f"  gold: {json.dumps(gold_map)}")

    assert sc.precision == 1.0 and sc.recall == 1.0 and sc.f1 == 1.0
    assert predicted == gold
    assert predicted, "the scenario must exercise at least one identity-review RFI"


def test_true_hit_and_dismissal_earn_no_rfi(conn, tmp_path):
    """Discrimination: the corroborated true hit (DES-0005) and the cleared
    same-name collision (DES-0007) produce NO identity-review RFI — only the
    unresolved possible-match candidate is contacted."""
    recs = {r["designation_id"]: r for r in conn.all_designations()}
    for did in ("DES-2026-0005", "DES-2026-0007"):
        d = designation_from_record(recs[did])
        res = run_sweep(d, out_dir=tmp_path / did, conn=conn)
        assert res.identity_rfis == []
        assert res.suppressed_identity_rfis == []
        # No RFI stamp lands, so these chains are byte-unchanged wrt the RFI stage.
        assert not [r for r in res.audit_records
                    if r["action"] == "identity_review_rfi"]
        assert res.audit_verified
