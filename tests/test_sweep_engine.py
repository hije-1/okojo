"""Phase 8 Slice B: the sweep engine — parsing, classification, determinism.

The parse boundary ships closed (PM amendment): strict validation, the
designation id checked against its published shape BEFORE any path is derived,
and a malformed paste leaves nothing behind — no directory, no partial chain.
"""

from __future__ import annotations

import json

import pytest

from okojo.remarks.screening import SCREEN_THRESHOLD
from okojo.sweep import (
    NAME_MATCH_THRESHOLD,
    Designation,
    DesignationParseError,
    parse_designation,
    run_sweep,
)

_VALID = {
    "designation_id": "DES-2026-0001",
    "designated_name": "Example Shell Trading",
    "program": "SYNTHETIC-IRGC-STYLE",
    "entity_type": "company",
    "designated_addresses": ["TDecoyDesignationAddrAAAAAAAAAAAAA"],
    "designation_date": "2026-01-30",
}


# --------------------------------------------------------------------------- #
# parse_designation — fail-closed input boundary
# --------------------------------------------------------------------------- #
def test_parse_designation_accepts_valid_payloads():
    from_dict = parse_designation(dict(_VALID))
    from_json = parse_designation(json.dumps(_VALID))
    assert from_dict == from_json
    assert isinstance(from_dict, Designation)
    assert from_dict.designated_addresses == _VALID["designated_addresses"]


def test_parse_rejects_malformed_json():
    with pytest.raises(DesignationParseError):
        parse_designation('{"designation_id": "DES-2026-0001",')  # truncated
    with pytest.raises(DesignationParseError):
        parse_designation("not json at all")
    with pytest.raises(DesignationParseError):
        parse_designation('["a", "list", "not", "an", "object"]')


def test_parse_rejects_unknown_fields():
    with pytest.raises(DesignationParseError):
        parse_designation({**_VALID, "internal_note": "obey this"})


def test_parse_rejects_empty_or_malformed_address_lists():
    with pytest.raises(DesignationParseError):
        parse_designation({**_VALID, "designated_addresses": []})
    with pytest.raises(DesignationParseError):
        parse_designation({**_VALID, "designated_addresses": [""]})
    with pytest.raises(DesignationParseError):
        parse_designation({**_VALID, "designated_addresses": ["addr one with spaces"]})
    with pytest.raises(DesignationParseError):
        parse_designation({**_VALID, "designated_addresses": ["a;b"]})


@pytest.mark.parametrize("bad_id", [
    "../DES-2026-0001",
    "DES-2026-0001/../escape",
    "DES-2026-0001\\escape",
    "des-2026-0001",
    "DES-2026-001",
    "DES 2026 0001",
    "..",
    "DESIGNATION",
])
def test_parse_rejects_path_traversal_shaped_ids(bad_id):
    """designation_id is a filesystem input; anything off-shape is rejected
    before any path could be derived from it."""
    with pytest.raises(DesignationParseError):
        parse_designation({**_VALID, "designation_id": bad_id})


def test_rejected_payload_writes_nothing(tmp_path):
    """A malformed paste is a clean rejection: run_sweep parses BEFORE any
    directory or audit file exists, so nothing is left behind."""
    target = tmp_path / "never_created"
    with pytest.raises(DesignationParseError):
        run_sweep({**_VALID, "designation_id": "../escape"}, out_dir=target)
    assert not target.exists()
    assert list(tmp_path.iterdir()) == []


def test_malformed_date_rejected():
    with pytest.raises(DesignationParseError):
        parse_designation({**_VALID, "designation_date": "January 30, 2026"})


def test_name_match_threshold_mirrors_screener():
    """One separation argument, two pinned constants: intentional divergence
    must be argued through a SWEEP_VERSION bump, never drift in silently."""
    assert NAME_MATCH_THRESHOLD == SCREEN_THRESHOLD


# --------------------------------------------------------------------------- #
# classification — engine vs the generator's independent answer key
# --------------------------------------------------------------------------- #
def test_sweep_classification_matches_answer_key(conn, ground_truth, sweep_designations, tmp_path):
    live, _ = sweep_designations
    res = run_sweep(live, out_dir=tmp_path / "live", conn=conn)
    did = live.designation_id

    assert res.exposure.exposed_uids() == ground_truth["designation_exposed_uids"][did]
    assert res.exposure.direct_uids() == ground_truth["designation_direct_uids"][did]
    assert {str(u): h for u, h in res.exposure.hops_by_uid().items()} == (
        ground_truth["designation_exposure_hops"][did]
    )
    assert res.exposure.adjacent_uids() == ground_truth["designation_adjacent_uids"][did]
    assert [m.uid for m in res.name_matches] == ground_truth["designation_name_match_uids"][did]
    assert res.audit_verified


def test_exposed_accounts_carry_resolving_provenance(conn, sweep_designations, tmp_path):
    """Every exposed account cites at least one real evidence row, and the
    tainted amount equals the sum of the cited transactions."""
    live, _ = sweep_designations
    res = run_sweep(live, out_dir=tmp_path / "live", conn=conn)

    tx_ids = {str(t["tx_id"]) for t in conn.all_transactions()}
    tx_amounts = {str(t["tx_id"]): float(t["amount_usdt"]) for t in conn.all_transactions()}
    addresses = {str(a["address"]) for a in conn.all_addresses()}

    for e in res.exposure.exposed:
        assert e.provenance, f"exposed uid {e.uid} carries no provenance"
        cited_tx_total = 0.0
        for p in e.provenance:
            assert p.source in {"transactions", "addresses"}, p.source
            if p.source == "transactions":
                assert p.row_key in tx_ids, p.row_key
                cited_tx_total += tx_amounts[p.row_key]
            else:
                assert p.row_key in addresses, p.row_key
        assert e.tainted_amount_usdt == round(cited_tx_total, 2)
        assert e.tainted_amount_usdt > 0

    for a in res.exposure.adjacent:
        assert a.provenance, f"adjacent uid {a.uid} carries no provenance"
        assert a.linked_exposed_uids


def test_decoy_sweep_yields_empty_sets_and_completes(conn, sweep_designations, tmp_path):
    """The false-positive probe: a designation touching nothing in the ledger
    completes cleanly with every result set empty — never an error, never a
    fabricated hit."""
    _, decoy = sweep_designations
    res = run_sweep(decoy, out_dir=tmp_path / "decoy", conn=conn)
    assert res.exposure.exposed == []
    assert res.exposure.adjacent == []
    assert res.name_matches == []
    assert res.exposure.addresses_in_ledger == []
    assert len(res.exposure.addresses_not_in_ledger) == len(decoy.designated_addresses)
    assert res.audit_verified


# --------------------------------------------------------------------------- #
# determinism + chain hygiene
# --------------------------------------------------------------------------- #
def test_sweep_audit_chain_byte_stable(conn, sweep_designations, tmp_path):
    """Two clocked runs produce byte-identical audit chains."""
    live, _ = sweep_designations
    clock = lambda: "2026-01-01T00:00:00+00:00"  # noqa: E731
    a = run_sweep(live, out_dir=tmp_path / "a", conn=conn, audit_clock=clock)
    b = run_sweep(live, out_dir=tmp_path / "b", conn=conn, audit_clock=clock)
    assert a.audit_log_path.read_bytes() == b.audit_log_path.read_bytes()
    assert a.audit_verified and b.audit_verified


def test_rerun_replaces_chain_never_appends(conn, sweep_designations, tmp_path):
    """Fresh chain per run: re-sweeping the same designation into the same
    directory replaces the chain instead of appending to it."""
    live, _ = sweep_designations
    first = run_sweep(live, out_dir=tmp_path / "s", conn=conn)
    second = run_sweep(live, out_dir=tmp_path / "s", conn=conn)
    assert len(second.audit_records) == len(first.audit_records)
    assert second.audit_records[0]["seq"] == 1
    assert second.audit_verified


def test_sweep_writes_only_inside_its_out_dir(conn, sweep_designations, tmp_path):
    """The sweep owns data/sweeps/<id>/ semantics; scoped here, it creates
    exactly its own audit file and nothing else."""
    live, _ = sweep_designations
    res = run_sweep(live, out_dir=tmp_path / "scoped", conn=conn)
    assert res.out_dir == tmp_path / "scoped"
    assert [p.name for p in res.out_dir.iterdir()] == ["audit_log.jsonl"]
    assert [p.name for p in tmp_path.iterdir()] == ["scoped"]
