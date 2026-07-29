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


def test_designation_accessors(conn, ground_truth):
    des = conn.all_designations()
    assert [d["designation_id"] for d in des] == [
        g["designation_id"] for g in ground_truth["designations"]
    ]
    one = conn.get_designation(des[0]["designation_id"])
    assert one is not None
    assert one.provenance.cite() == f"designations[{des[0]['designation_id']}]"
    assert conn.get_designation("DES-9999-9999") is None


def test_hold_accessors_cover_every_account(conn):
    # The hold systems track every account with an on-chain/hold footprint. The
    # Part-II identity-review subjects are name-screen-only personas with no hold
    # rows by design (additive-only rule), so they are outside this set.
    uids = {a["uid"] for a in conn.all_accounts()
            if not str(a["role_in_ring"]).endswith("_review_subject")}
    for rows, source in ((conn.warehouse_holds(), "sanctions_hold_warehouse"),
                         (conn.admin_holds(), "sanctions_hold_admin")):
        assert {r["uid"] for r in rows} == uids
        assert len(rows) == len(uids)
        for r in rows:
            assert r.provenance.source == source
            assert r.provenance.row_key == f"uid:{r['uid']}"


def test_hold_for_accessors_agree_with_gap_key(conn, ground_truth):
    for gap in ground_truth["block_status_gaps"]:
        wh = conn.warehouse_hold_for(gap["uid"])
        adm = conn.admin_hold_for(gap["uid"])
        assert wh is not None and adm is not None
        assert wh["hold_status"] == gap["warehouse_status"]
        assert adm["hold_status"] == gap["admin_status"]
