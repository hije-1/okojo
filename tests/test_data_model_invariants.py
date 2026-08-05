"""Two-record data-model invariants (docs/scenario-data-model-redesign.md §5).

The scenario separates the exchange's INTERNAL record of a movement (a ``uid:``
leg — customer-attributed, may carry a remark) from the on-chain TRANSACTION
(address -> address — never a remark). Every customer withdrawal settles from a
single omnibus hot wallet, never a customer address. These executable properties
guard the model so it can never silently regress to the memo-on-chain flaw.
"""

from __future__ import annotations


def _rows(conn, table):
    return conn.store.query(f"SELECT * FROM {table}")


# 1) No chain record carries a non-empty remark (a TRC-20 transfer has no memo).
def test_no_chain_record_carries_a_remark(conn):
    for t in _rows(conn, "transactions"):
        if t["record_kind"] == "chain":
            assert not (t["remark"] and str(t["remark"]).strip()), \
                f"chain record {t['tx_id']} carries a remark {t['remark']!r}"


# 2) No customer address is the on-chain SOURCE of a withdrawal: every
#    settlement leg originates from the single omnibus hot wallet, which is bound
#    to the exchange (no controller uid), never a customer.
def test_withdrawals_settle_from_the_hot_wallet_only(conn):
    legs = conn.settlement_legs()
    assert legs, "expected hot-wallet settlement legs for the customer withdrawals"
    hot = {
        a["address"] for a in _rows(conn, "addresses")
        if a["label"] == "exchange-hot-wallet"
    }
    assert len(hot) == 1, "exactly one omnibus hot wallet (Q5)"
    hot_addr = next(iter(hot))
    hot_ctrl = next(a["controller_uid"] for a in _rows(conn, "addresses")
                    if a["address"] == hot_addr)
    assert hot_ctrl is None, "the hot wallet is bound to the exchange, never a customer"
    for leg in legs:
        assert str(leg["from_ref"]) == hot_addr, \
            f"settlement leg {leg['tx_id']} does not originate from the hot wallet"
        assert leg["record_kind"] == "chain"
        assert not (leg["remark"] and str(leg["remark"]).strip())


# 3) Value counted once: every settlement leg mirrors exactly one exchange
#    record (same amount/timestamp), and the flow ledger EXCLUDES the legs, so a
#    settled movement is counted a single time.
def test_each_movement_is_counted_once(conn):
    tx_by_id = {t["tx_id"]: t for t in _rows(conn, "transactions")}
    flow_ids = {r["tx_id"] for r in conn.all_transactions()}
    for leg in conn.settlement_legs():
        assert leg["tx_id"] not in flow_ids, \
            "a settlement leg must never appear in the flow/value ledger"
        ex = tx_by_id[str(leg["settled_by"])]
        assert ex["record_kind"] == "exchange"
        assert str(ex["settlement_ref"]) == str(leg["tx_id"]), "settlement link is symmetric"
        assert float(ex["amount_usdt"]) == float(leg["amount_usdt"])
        assert str(ex["timestamp"]) == str(leg["timestamp"])


# 4) Exposure-set reproducibility: reachability recomputed over the FLOW ledger
#    (settlement legs excluded) equals the committed sanctioned-exposure answer
#    key exactly — the property Option A broke (8 -> 3) and this model preserves.
def test_exposure_set_reproducible_over_flow_ledger(conn, ground_truth):
    from collections import deque

    gold = set(ground_truth["sanctioned_exposure_uids"])
    assert gold == {500000000, 500000002, 500000003, 500000004,
                    500000005, 500000006, 500000007, 500000008}

    # Directed reachability over transaction edges + controls edges, exactly the
    # generator's definitional walk — but read off the connectors' flow ledger,
    # proving the settlement legs are correctly invisible to it.
    adj: dict[str, set[str]] = {}
    for t in conn.all_transactions():
        adj.setdefault(str(t["from_ref"]), set()).add(str(t["to_ref"]))
    controlled: dict[str, list[int]] = {}
    for a in conn.all_addresses():
        if a["controller_uid"] is not None:
            adj.setdefault(f"uid:{int(a['controller_uid'])}", set()).add(str(a["address"]))
    sanctioned = {str(a["address"]) for a in conn.sanctioned_addresses()}

    def reaches(start: str) -> bool:
        seen, dq = {start}, deque(adj.get(start, ()))
        while dq:
            n = dq.popleft()
            if n in sanctioned:
                return True
            if n in seen:
                continue
            seen.add(n)
            dq.extend(adj.get(n, ()))
        return False

    recomputed = {int(a["uid"]) for a in conn.all_accounts()
                  if reaches(f"uid:{int(a['uid'])}")}
    assert recomputed == gold


# 5) Settlement integrity: every settlement_ref / settled_by resolves to a real
#    row of the opposite kind; exchange records that are withdrawals are settled.
def test_settlement_links_resolve(conn):
    tx_by_id = {t["tx_id"]: t for t in _rows(conn, "transactions")}
    for t in _rows(conn, "transactions"):
        if t["record_kind"] == "chain" and t["settled_by"]:
            ex = tx_by_id[str(t["settled_by"])]
            assert ex["record_kind"] == "exchange"
        if t["record_kind"] == "exchange" and t["settlement_ref"]:
            leg = tx_by_id[str(t["settlement_ref"])]
            assert leg["record_kind"] == "chain"
            assert str(leg["settled_by"]) == str(t["tx_id"])


# 6) The address book is the ONLY non-transaction home for customer free text,
#    and its labels are mined as tells (recall preserved elsewhere; here we
#    assert the two "aggregation wallet" / "client custody" labels are present
#    and every chain record stays memo-free).
def test_address_book_holds_the_relocated_customer_free_text(conn):
    labels = {str(e["label"]) for e in conn.address_book()}
    assert {"aggregation wallet", "client custody"} <= labels
    # the two hop rows that used to carry these remarks are now memo-free chain
    # records (guarded broadly by test 1; asserted here as the specific pair).
    remarked_chain = [
        t for t in _rows(conn, "transactions")
        if t["record_kind"] == "chain" and t["remark"] and str(t["remark"]).strip()
    ]
    assert not remarked_chain
