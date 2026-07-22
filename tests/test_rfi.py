"""RFI reader surfaces the subject's RFI, grounded and matching ground truth."""

from __future__ import annotations

from okojo.orchestrator import run_case
from okojo.rfi import load_rfi


def test_load_rfi_for_trust_subject(conn, trust_uid):
    rfi = load_rfi(conn, trust_uid)
    assert rfi is not None
    assert rfi.rfi_id and rfi.question and rfi.response_text
    assert len(rfi.claims) == 4
    assert rfi.provenance  # grounded


def test_false_claims_match_ground_truth(conn, trust_uid, ground_truth):
    rfi = load_rfi(conn, trust_uid)
    false_ids = {c.claim_id for c in rfi.claims if c.ground_truth == "false"}
    gt_lie_ids = {lie["claim_id"] for lie in ground_truth["rfi_lies"]}
    assert false_ids == gt_lie_ids
    # every declared lie carries at least one contradiction note
    for c in rfi.claims:
        if c.ground_truth == "false":
            assert c.contradicted_by


def test_account_without_rfi_returns_none(conn, ground_truth):
    priv_uid = ground_truth["privileged_redherring_uid"]
    assert load_rfi(conn, priv_uid) is None


def test_orchestrator_attaches_rfi(conn, trust_uid, ground_truth, tmp_path):
    res = run_case(trust_uid, conn=conn, out_dir=tmp_path, render_graph=False)
    assert res.rfi is not None and res.rfi.claims

    priv_uid = ground_truth["privileged_redherring_uid"]
    res2 = run_case(priv_uid, conn=conn, out_dir=tmp_path, render_graph=False)
    assert res2.rfi is None
