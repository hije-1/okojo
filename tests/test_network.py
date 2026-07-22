"""Network Expander recovers the ring and reaches sanctioned endpoints."""

from __future__ import annotations

from okojo.network import expand, render


def test_expansion_recovers_network_members(conn, trust_uid, ground_truth):
    exp = expand(conn, trust_uid, max_hops=2)
    members = set(ground_truth["network_member_uids"])
    reached = set(exp.reached_account_uids)
    recall = len(members & reached) / len(members)
    assert recall >= 0.8, f"network recall too low: {recall:.0%}"
    assert trust_uid in reached


def test_expansion_reaches_sanctioned_addresses(conn, trust_uid):
    exp = expand(conn, trust_uid, max_hops=2)
    assert len(exp.sanctioned_addresses_reached) >= 1
    assert exp.graph.number_of_nodes() > 0
    assert exp.graph.number_of_edges() > 0


def test_render_writes_utf8_html(conn, trust_uid, tmp_path):
    exp = expand(conn, trust_uid, max_hops=2)
    out = render(exp, tmp_path / "network.html")
    assert out.exists()
    text = out.read_text(encoding="utf-8")
    assert "<html" in text.lower()
