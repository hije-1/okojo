"""Remark Miner + SDN/alias screening — fuzzy tells, scored against ground truth."""

from __future__ import annotations

from okojo.eval import score
from okojo.remarks import mine_remarks, screen_aliases

# Pure-noise remark texts the generator plants on ordinary traffic.
_NOISE_REMARKS = {"savings", "payment", "trade"}


def test_recovers_all_betraying_remarks(conn, ground_truth):
    hits = mine_remarks(conn)
    found_tx = {h.tx_id for h in hits}
    betraying = {b["tx_id"] for b in ground_truth["betraying_remarks"]}
    assert betraying.issubset(found_tx), f"missed betraying remarks: {betraying - found_tx}"


def test_betraying_remark_recall_is_perfect(conn, ground_truth):
    hits = mine_remarks(conn)
    s = score({h.tx_id for h in hits}, {b["tx_id"] for b in ground_truth["betraying_remarks"]})
    assert s.recall == 1.0


def test_no_false_positives_on_noise_remarks(conn):
    hits = mine_remarks(conn)
    for h in hits:
        assert h.remark.strip().lower() not in _NOISE_REMARKS, (
            f"noise remark wrongly flagged: {h.remark!r}"
        )


def test_hits_carry_provenance_terms_and_score(conn):
    hits = mine_remarks(conn)
    assert hits
    for h in hits:
        assert h.provenance.source == "transactions"
        assert h.matched_terms
        assert 0 < h.score <= 100


def test_fuzzy_matches_transliteration_nickname(conn):
    # The "Old <firstname> wallet" nickname remark is caught as a control alias.
    hits = mine_remarks(conn)
    alias_hits = [h for h in hits if h.category == "control_alias"]
    assert alias_hits, "expected at least one control-alias tell"


# --- SDN / alias screening ------------------------------------------------- #

def test_alias_screening_precision_recall(conn, ground_truth):
    hits = screen_aliases(conn)
    predicted = {h.uid for h in hits}
    gold = {m["uid"] for m in ground_truth["sdn_alias_matches"]}
    s = score(predicted, gold)
    # transliteration variants are caught, decoys and unrelated names are not
    assert s.precision == 1.0 and s.recall == 1.0 and s.f1 == 1.0


def test_alias_hits_are_grounded(conn):
    hits = screen_aliases(conn)
    assert hits
    for h in hits:
        sources = {p.source for p in h.provenance}
        assert "sdn_list" in sources and "accounts" in sources
        assert h.score >= 85
