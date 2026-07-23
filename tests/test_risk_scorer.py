"""Unit tests for the On-chain Risk Scorer (Phase 2, Slice 3).

Invariants only — there is no gold *ranking*, so we assert structural properties
(membership parity with the reachability key, monotonicity, determinism, and that
gas-funding is never dropped) rather than exact scores.
"""

from __future__ import annotations

from okojo.network import expand
from okojo.scorer import score_risk

_A_REF = 1_000_000  # tainted USDT at/above which the amount factor saturates


def _scoring(conn, trust_uid, hops: int = 3):
    return score_risk(conn, expand(conn, trust_uid, max_hops=hops))


def test_exposed_uids_match_gold_exactly(conn, trust_uid, ground_truth):
    """The money-flow exposure set is exactly the reachability answer key."""
    r = _scoring(conn, trust_uid)
    assert set(r.exposed_uids) == set(ground_truth["sanctioned_exposure_uids"])


def test_negative_set_never_exposed(conn, trust_uid, ground_truth):
    r = _scoring(conn, trust_uid)
    # the privileged red-herring must never be flagged as exposed
    assert ground_truth["privileged_redherring_uid"] not in r.exposed_uids
    gold = set(ground_truth["sanctioned_exposure_uids"])
    non_exposed = {a["uid"] for a in conn.all_accounts()} - gold
    assert non_exposed.isdisjoint(r.exposed_uids)


def test_exposure_path_iff_in_exposed_uids(conn, trust_uid):
    r = _scoring(conn, trust_uid)
    exposed = set(r.exposed_uids)
    for s in r.scores:
        assert (s.uid in exposed) is s.exposure_path
        if s.exposure_path:
            assert s.score > 0.0
        else:  # the only exposure_path=False rows are gas-only echoes
            assert s.reasons == ["gas_only_link"]


def test_scores_sorted_and_bands_consistent(conn, trust_uid):
    r = _scoring(conn, trust_uid)
    scores = [s.score for s in r.scores]
    assert scores == sorted(scores, reverse=True)
    assert sum(r.band_counts().values()) == len(r.scores)
    # direct senders behind the sanctioned transfers land in the high band
    assert any(s.band == "high" for s in r.scores)


def test_hop_monotonicity_at_equal_saturation(conn, trust_uid):
    """With amount saturated, a closer account never scores below a deeper one."""
    r = _scoring(conn, trust_uid)
    saturated = [s for s in r.scores if s.exposure_path and s.tainted_amount_usdt >= _A_REF]
    assert saturated
    for a in saturated:
        for b in saturated:
            if a.hop_distance < b.hop_distance:
                assert a.score >= b.score


def test_gas_funding_never_dropped(conn, trust_uid):
    """Every gas controller surfaces in the scorer output — as a money-flow row
    carrying a gas reason, or as a gas-only echo. Gas is never silently dropped."""
    exp = expand(conn, trust_uid, max_hops=3)
    r = score_risk(conn, exp)
    gas_controllers = {link["controller_uid"] for link in exp.gas_funding_links}
    assert gas_controllers  # the dataset plants the gas-funding tell
    by_uid = {s.uid: s for s in r.scores}
    for c in gas_controllers:
        assert c in by_uid, f"gas controller {c} dropped from scorer output"
        s = by_uid[c]
        if s.exposure_path:
            assert "gas_funded_hop" in s.reasons
        else:
            assert "gas_only_link" in s.reasons


def test_every_exposed_row_is_grounded(conn, trust_uid):
    """Grounding contract: every surfaced exposure carries a provenance pointer."""
    r = _scoring(conn, trust_uid)
    for s in r.scores:
        if s.exposure_path:
            assert s.provenance, "exposed row must carry provenance"
            assert any(p.source == "addresses" for p in s.provenance)


def test_determinism(conn, trust_uid):
    exp = expand(conn, trust_uid, max_hops=3)
    a = score_risk(conn, exp)
    b = score_risk(conn, exp)
    key = lambda r: [
        (s.uid, s.score, s.band, s.exposure_path, s.hop_distance, s.tainted_amount_usdt)
        for s in r.scores
    ]
    assert key(a) == key(b)
