"""Connectors return provenance-carrying records over the synthetic data."""

from __future__ import annotations


def test_accounts_load_with_provenance(conn):
    accts = conn.all_accounts()
    assert len(accts) >= 12
    sample = accts[0]
    assert sample.provenance.source == "accounts"
    assert sample.provenance.row_key.startswith("uid:")


def test_get_account_roundtrip(conn, trust_uid):
    acct = conn.get_account(trust_uid)
    assert acct is not None
    assert acct["uid"] == trust_uid
    assert acct.provenance.cite() == f"accounts[uid:{trust_uid}]"


def test_reused_kyc_accessor(conn, ground_truth):
    # Every reused-KYC group in ground truth is recoverable via the accessor.
    for doc_id, uids in ground_truth["reused_kyc_docs"].items():
        sharers = {r["uid"] for r in conn.accounts_with_kyc(doc_id)}
        assert set(uids).issubset(sharers)


def test_shared_device_accessor(conn, ground_truth):
    for fp, uids in ground_truth["shared_devices"].items():
        on_device = {r["uid"] for r in conn.accounts_on_device(fp)}
        assert set(uids).issubset(on_device)


def test_sanctioned_addresses(conn, ground_truth):
    got = {r["address"] for r in conn.sanctioned_addresses()}
    assert got == set(ground_truth["sanctioned_addresses_synthetic"])


def test_remarks_are_nonempty(conn):
    for r in conn.remarks():
        assert r["remark"] and str(r["remark"]).strip()
