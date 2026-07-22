"""Network Expander recovers the ring and reaches sanctioned endpoints."""

from __future__ import annotations

from okojo.eval import score
from okojo.network import expand, render


def test_expansion_recovers_network_members(conn, trust_uid, ground_truth):
    exp = expand(conn, trust_uid, max_hops=2)
    members = set(ground_truth["network_member_uids"])
    reached = set(exp.reached_account_uids)
    recall = len(members & reached) / len(members)
    assert recall >= 0.8, f"network recall too low: {recall:.0%}"
    assert trust_uid in reached


def test_network_member_precision_recall_f1(conn, trust_uid, ground_truth):
    exp = expand(conn, trust_uid, max_hops=2)
    s = score(exp.reached_account_uids, ground_truth["network_member_uids"])
    # The ring is fully recovered without dragging in noise accounts.
    assert s.recall == 1.0
    assert s.precision >= 0.9
    assert s.f1 >= 0.95


def test_gas_funding_controller_collapse(conn, trust_uid, ground_truth):
    exp = expand(conn, trust_uid, max_hops=2)
    predicted = {(l["funder_address"], l["funded_address"]) for l in exp.gas_funding_links}
    gold = {(g["funder_address"], g["funded_address"]) for g in ground_truth["gas_funding_tells"]}
    s = score(predicted, gold)
    assert s.precision == 1.0 and s.recall == 1.0 and s.f1 == 1.0
    # every collapsed hop is attributed to the true controller (the KINGPIN)
    controller = ground_truth["ultimate_controller_uid"]
    assert all(l["controller_uid"] == controller for l in exp.gas_funding_links)


def test_sanctioned_exposure_recall(conn, trust_uid, ground_truth):
    exp = expand(conn, trust_uid, max_hops=2)
    s = score(exp.sanctioned_exposed_uids, ground_truth["sanctioned_exposure_uids"])
    # Flow-reachability recovers exactly the exposed accounts, no more.
    assert s.recall == 1.0 and s.precision == 1.0


def test_multidigraph_preserves_parallel_relationships(conn, ground_truth):
    # Find a pair of accounts that share BOTH a device and a KYC document.
    # A MultiDiGraph keeps both edges where a DiGraph would let one overwrite it.
    device_pairs = {
        frozenset((u, v))
        for uids in ground_truth["shared_devices"].values()
        for u in uids for v in uids if u != v
    }
    pair = next(
        frozenset((uids[i], uids[j]))
        for uids in ground_truth["reused_kyc_docs"].values()
        for i in range(len(uids)) for j in range(i + 1, len(uids))
        if frozenset((uids[i], uids[j])) in device_pairs
    )
    a, b = tuple(pair)
    g = expand(conn, a, max_hops=2).graph
    na, nb = f"acct:{a}", f"acct:{b}"
    # both relationship edges survive (in whichever direction they were added)
    assert g.has_edge(na, nb, key="reused_kyc") or g.has_edge(nb, na, key="reused_kyc")
    assert g.has_edge(na, nb, key="shared_device") or g.has_edge(nb, na, key="shared_device")


def test_max_hops_is_clamped(conn, trust_uid):
    # Out-of-range hop counts are clamped to the 1-7 supported window.
    assert expand(conn, trust_uid, max_hops=99).max_hops == 7
    assert expand(conn, trust_uid, max_hops=0).max_hops == 1


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
