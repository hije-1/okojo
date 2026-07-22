"""Remark Miner surfaces the ground-truth betraying remark tells."""

from __future__ import annotations

from okojo.remarks import mine_remarks


def test_recovers_all_betraying_remarks(conn, ground_truth):
    hits = mine_remarks(conn)
    found_tx = {h.tx_id for h in hits}
    betraying = {b["tx_id"] for b in ground_truth["betraying_remarks"]}
    assert betraying.issubset(found_tx), (
        f"missed betraying remarks: {betraying - found_tx}"
    )


def test_hits_carry_provenance_and_terms(conn):
    hits = mine_remarks(conn)
    assert hits
    for h in hits:
        assert h.provenance.source == "transactions"
        assert h.matched_terms
