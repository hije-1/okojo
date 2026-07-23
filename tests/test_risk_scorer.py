"""Unit tests for the On-chain Risk Scorer (Phase 2, Slice 3).

Invariants only — there is no gold *ranking*, so we assert structural properties
(membership parity with the reachability key, monotonicity, determinism, and that
gas-funding is never dropped) rather than exact scores.
"""

from __future__ import annotations

import networkx as nx
import pytest

from okojo.network import NetworkExpansion, expand
from okojo.scorer import SCORING_VERSION, score_risk, scoring_config

_A_REF = 1_000_000  # tainted USDT at/above which the amount factor saturates
_DECAY = 0.6        # per-hop decay (mirrors scorer._DECAY)


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


# -- Slice 4b: decomposition & reproducibility -------------------------------- #

def test_decomposition_reproduces_score(conn, trust_uid):
    """Every score is exactly its own decomposition — recomputing from the two
    factors yields the same number (the 'show the math' contract)."""
    r = _scoring(conn, trust_uid)
    assert r.scores
    for s in r.scores:
        d = s.decomposition
        assert d is not None
        assert round(min(1.0, d.base_factor * d.proximity_factor), 3) == s.score
        assert d.product == d.base_factor * d.proximity_factor
        assert d.score == s.score


def test_decomposition_kind_and_labels(conn, trust_uid):
    """Decomposition kind tracks money-flow vs gas-only, and the proximity factor
    is pure hop decay."""
    r = _scoring(conn, trust_uid)
    for s in r.scores:
        d = s.decomposition
        assert (d.kind == "money_flow") is s.exposure_path
        assert d.proximity_factor == pytest.approx(_DECAY ** (s.hop_distance - 1))
        if s.exposure_path:
            assert d.base_label == "amount"
            assert 0.0 < d.base_factor <= 1.0
        else:
            assert d.base_label == "gas_base"


def test_scoring_config_and_version(conn, trust_uid):
    """The result carries the version + config it was computed under."""
    r = _scoring(conn, trust_uid)
    assert r.version == SCORING_VERSION
    assert r.config == scoring_config()
    cfg = scoring_config()
    assert cfg["version"] == SCORING_VERSION
    assert set(cfg) == {
        "version", "membership_edge_types", "decay", "floor",
        "amount_ref_usdt", "gas_base", "band_high", "band_medium",
    }
    # membership is exactly the money-flow edge set — the gold-key semantics
    assert cfg["membership_edge_types"] == ["controls", "transaction"]


def test_gas_only_decomposition_uses_gas_base():
    """A gas-only controller (no money-flow path) is scored gas_base × proximity
    and kept OUT of the exposure metric. Exercised with a minimal synthetic graph,
    since the TRUST scenario's gas controllers also move money (0 gas-only rows)."""
    g = nx.MultiDiGraph()
    g.add_node("addr:SANC", kind="address", address="SANC", sanctioned=True)
    g.add_node("acct:2", kind="account", uid=2)
    g.add_node("addr:FUNDED", kind="address", address="FUNDED", sanctioned=False)
    # gas link only — no transaction/controls path to the sanctioned endpoint
    g.add_edge("acct:2", "addr:FUNDED", key="gas_control", etype="gas_control")
    exp = NetworkExpansion(
        graph=g, subject_uid=2, max_hops=2,
        gas_funding_links=[{"controller_uid": 2, "funder_address": "F", "funded_address": "FUNDED"}],
    )

    class _FakeConn:
        def gas_funds(self):
            return []

    r = score_risk(_FakeConn(), exp)
    by_uid = {s.uid: s for s in r.scores}
    assert 2 in by_uid, "gas-only controller must still surface"
    gas_row = by_uid[2]
    assert gas_row.exposure_path is False
    assert gas_row.reasons == ["gas_only_link"]
    assert 2 not in r.exposed_uids  # kept out of the money-flow metric
    d = gas_row.decomposition
    assert d.kind == "gas_only"
    assert d.base_label == "gas_base"
    assert d.base_factor == pytest.approx(0.5)
    assert round(min(1.0, d.base_factor * d.proximity_factor), 3) == gas_row.score
