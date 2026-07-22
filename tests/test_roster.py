"""Network roster surfaces per-account triage data, risk-sorted."""

from __future__ import annotations

from okojo.network import build_roster, expand


def test_roster_pins_subject_and_excludes_addresses(conn, trust_uid, tmp_path):
    expansion = expand(conn, trust_uid, max_hops=2)
    roster = build_roster(conn, expansion, cases_dir=tmp_path)

    # Subject is pinned first.
    assert roster[0].is_subject
    assert roster[0].uid == trust_uid

    # One roster row per account node — address nodes are excluded.
    account_nodes = [
        d for _, d in expansion.graph.nodes(data=True) if d.get("kind") == "account"
    ]
    assert len(roster) == len(account_nodes)
    assert {r.uid for r in roster} == {d["uid"] for d in account_nodes}


def test_roster_is_risk_sorted_after_subject(conn, trust_uid, tmp_path):
    roster = build_roster(conn, expand(conn, trust_uid, max_hops=2), cases_dir=tmp_path)
    rank = {"high": 3, "medium": 2, "low": 1, None: 0}
    severities = [rank[r.worst_severity] for r in roster[1:]]  # skip pinned subject
    assert severities == sorted(severities, reverse=True)


def test_roster_flags_internal_account_when_reached(conn, ground_truth, tmp_path):
    # Expanding from the red-herring account itself guarantees it is in the graph.
    priv_uid = ground_truth["privileged_redherring_uid"]
    roster = build_roster(conn, expand(conn, priv_uid, max_hops=1), cases_dir=tmp_path)

    priv = next(r for r in roster if r.uid == priv_uid)
    assert priv.internal_flagged is True
    # The internal tag is surfaced as its own signal, not as a generic chip.
    assert "internal_account_tag" not in priv.anomaly_codes


def test_roster_reports_case_file_presence(conn, trust_uid, tmp_path):
    roster = build_roster(conn, expand(conn, trust_uid, max_hops=2), cases_dir=tmp_path)
    # No case folders in the temp dir → nothing is on record yet.
    assert all(r.has_case_file is False for r in roster)

    # Create one and confirm it is detected.
    (tmp_path / f"case_{trust_uid}").mkdir()
    roster2 = build_roster(conn, expand(conn, trust_uid, max_hops=2), cases_dir=tmp_path)
    subject = next(r for r in roster2 if r.uid == trust_uid)
    assert subject.has_case_file is True
