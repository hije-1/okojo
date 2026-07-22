"""The orchestrator runs one case end-to-end with a verified audit trail."""

from __future__ import annotations

from okojo.orchestrator import run_case


def test_run_case_end_to_end(conn, trust_uid, tmp_path):
    res = run_case(trust_uid, conn=conn, out_dir=tmp_path, max_hops=2)

    # every stage produced something
    assert res.profile.events
    assert res.profile.anomalies
    assert res.expansion.reached_account_uids
    assert res.tells
    assert res.advisory is not None
    assert res.sar.claims

    # grounding + audit guarantees
    assert res.sar.ungrounded() == []
    assert res.audit_verified is True
    assert res.audit_records[0]["action"] == "case_open"

    # artefacts on disk
    assert res.graph_html_path and res.graph_html_path.exists()
    assert res.audit_log_path.exists()


def test_run_case_without_rfi_has_no_advisory(conn, ground_truth, tmp_path):
    # The privileged red-herring account has no RFI, so no advisory should match,
    # and the pipeline must still complete and stay grounded.
    priv_uid = ground_truth["privileged_redherring_uid"]
    res = run_case(priv_uid, conn=conn, out_dir=tmp_path, render_graph=False)
    assert res.advisory is None
    assert res.sar.ungrounded() == []
    assert "internal_account_tag" in res.profile.anomaly_codes()
