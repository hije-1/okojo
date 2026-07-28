"""Phase 8 Slice A: the designation + hold-table scenario extension.

Equality discipline (PM ruling): the expected exposure set, adjacency set, and
hop distances are asserted as FULL EQUALITY against sets derived from persona
roles in ``accounts.csv`` — never hardcoded uids, never subset checks. A subset
check would let the exposed set silently grow past the designed pattern; an
equality check is a tripwire on both sides.
"""

from __future__ import annotations

import re

import pandas as pd
import pytest

# The designation-id shape the Slice-B parser will enforce fail-closed
# (designation_id is a filesystem input). The generated ids must already
# conform, or the generator's own output would be rejected by its own sweep.
_DESIGNATION_ID_RE = re.compile(r"^[A-Z]{3}-\d{4}-\d{4}$")

_HOLD_STATUSES = {"blocked", "no_hold"}


@pytest.fixture(scope="module")
def accounts(data_dir) -> pd.DataFrame:
    return pd.read_csv(data_dir / "accounts.csv")


@pytest.fixture(scope="module")
def designations(ground_truth) -> tuple[dict, dict]:
    """(live, decoy) DOMESTIC designation entries, identified structurally.

    The live domestic designation is the ``sdn_style`` one with a non-empty
    expected exposure; the decoy is the other domestic one. Part I-B adds
    foreign ``national_ct`` plants (also carrying exposure) — those are covered
    separately, so this stays pinned to the domestic pair the Part-I tests use.
    """
    domestic = [d for d in ground_truth["designations"] if d["list_type"] == "sdn_style"]
    live = [d for d in domestic
            if ground_truth["designation_exposed_uids"][d["designation_id"]]]
    decoy = [d for d in domestic
             if not ground_truth["designation_exposed_uids"][d["designation_id"]]]
    assert len(live) == 1 and len(decoy) == 1
    return live[0], decoy[0]


# The persona-key -> uid mapping (``ring``) is the shared session fixture in
# conftest.py — one derivation from roles, used by scenario and eval tests.


# --------------------------------------------------------------------------- #
# tables + shapes
# --------------------------------------------------------------------------- #
def test_designation_tables_written_with_expected_columns(data_dir):
    des = pd.read_csv(data_dir / "designations.csv")
    assert list(des.columns) == [
        "designation_id", "designated_name", "program", "entity_type",
        "designated_addresses", "designation_date",
        # Part I-B: which list, and when.
        "source_regime", "list_type", "obligation_vs_signal", "listed_since",
    ]
    # Two domestic (Part I) + two foreign national-CT plants (Part I-B S2).
    assert len(des) == 4
    for did in des.designation_id:
        assert _DESIGNATION_ID_RE.fullmatch(did), did

    wh = pd.read_csv(data_dir / "sanctions_hold_warehouse.csv")
    assert list(wh.columns) == ["uid", "hold_status", "as_of_date", "feed_batch_id"]
    adm = pd.read_csv(data_dir / "sanctions_hold_admin.csv")
    assert list(adm.columns) == ["uid", "hold_status", "status_date", "actioned_by", "case_ref"]
    assert set(wh.hold_status) <= _HOLD_STATUSES
    assert set(adm.hold_status) <= _HOLD_STATUSES


def test_live_addresses_exist_in_ledger_decoy_addresses_do_not(data_dir, designations):
    live, decoy = designations
    ledger = set(pd.read_csv(data_dir / "addresses.csv").address)
    assert set(live["designated_addresses"]) <= ledger
    assert not set(decoy["designated_addresses"]) & ledger
    # All designated addresses are TRX-shaped (T + 33 base58 chars) — the decoy
    # differs from the ledger in membership only, never in shape.
    for d in (live, decoy):
        for addr in d["designated_addresses"]:
            assert re.fullmatch(r"T[1-9A-HJ-NP-Za-km-z]{33}", addr), addr


def test_domestic_designations_are_sdn_style_obligation_listed_since_equals_date(data_dir):
    """Part I-B ruling IB-B: both Part-I designations are domestic
    sdn_style/obligation entries whose ``listed_since`` equals their
    ``designation_date`` EXACTLY — the lead-time gap is a property only of the
    foreign plant (S2), so no accidental domestic 'window' can ever exist."""
    des = pd.read_csv(data_dir / "designations.csv")
    domestic = des[des.list_type == "sdn_style"]
    assert len(domestic) == 2
    assert (domestic.source_regime == "SYN-DOMESTIC-OFAC").all()
    assert (domestic.obligation_vs_signal == "obligation").all()
    assert (domestic.listed_since == domestic.designation_date).all()


def test_foreign_plants_are_national_ct_signal_with_lead_time(data_dir, ground_truth, ring):
    """Part I-B S2: two FOREIGN national-CT/signal plants. 3a (lead-time) is a
    transliteration variant of KINGPIN's name (IB-B) over an existing wallet,
    listed ~2 years before the domestic date; 3b (granularity) is a variant of
    SIBLING's name with NO addresses. Both are risk signals, never obligations."""
    des = pd.read_csv(data_dir / "designations.csv", keep_default_na=False)
    foreign = des[des.list_type == "national_ct"]
    assert len(foreign) == 2
    assert (foreign.obligation_vs_signal == "signal").all()
    assert (foreign.source_regime == "SYN-FOREIGN-NCT").all()

    accounts = pd.read_csv(data_dir / "accounts.csv")
    king_name = accounts[accounts.uid == ring["KINGPIN"]].entity_name.iloc[0]
    sib_name = accounts[accounts.uid == ring["SIBLING"]].entity_name.iloc[0]

    # 3a: lead-time plant — exposure non-empty, addresses present, name is a
    # KINGPIN variant (shares the first token, is not the exact registered name),
    # listed strictly before the domestic designation date.
    lead = next(d for d in ground_truth["designations"]
                if d["list_type"] == "national_ct"
                and ground_truth["designation_exposed_uids"][d["designation_id"]])
    assert lead["designated_addresses"] and lead["listed_since"] < lead["designation_date"]
    assert lead["designated_name"] != king_name
    assert lead["designated_name"].split()[0] == king_name.split()[0]
    assert ground_truth["designation_lead_time_window"][lead["designation_id"]]["lead_days"] > 700

    # 3b: granularity plant — no addresses, name is a SIBLING variant, and the
    # empty-address list survives the round-trip (conditional rule, S1).
    name_only = next(d for d in ground_truth["designations"]
                     if d["list_type"] == "national_ct"
                     and not ground_truth["designation_exposed_uids"][d["designation_id"]])
    assert name_only["designated_addresses"] == []
    assert name_only["designated_name"] != sib_name
    assert name_only["designated_name"].split()[0] == sib_name.split()[0]


def test_decoy_designation_name_is_the_sdn_decoy(data_dir, designations):
    """The decoy reuses SDN-0003's precision-decoy name, pinned by equality.

    Pinned through the emitted tables (not a shared constant) so the generator
    section stays purely additive; if either literal drifts, this trips.
    """
    _, decoy = designations
    sdn = pd.read_csv(data_dir / "sdn_list.csv")
    decoy_sdn = sdn[sdn.sdn_id == "SDN-0003"].primary_name.iloc[0]
    assert decoy["designated_name"] == decoy_sdn


# --------------------------------------------------------------------------- #
# exposure answer key — FULL equality (PM ruling: subset checks are too weak)
# --------------------------------------------------------------------------- #
def test_designation_exposure_full_equality(ground_truth, designations, ring):
    live, decoy = designations
    expected_direct = {ring["KINGPIN"], ring["TRUST"], ring["SHELL_NZ"]}
    expected_indirect = {ring["SHELL_AE"], ring["SHELL_TR"], ring["SHELL_HK"], ring["SHELL_CN"]}

    exposed = ground_truth["designation_exposed_uids"][live["designation_id"]]
    assert exposed == sorted(expected_direct | expected_indirect)
    assert ground_truth["designation_direct_uids"][live["designation_id"]] == sorted(expected_direct)

    # Hop distances, exact: 0 = controls a designated address (KINGPIN owns the
    # designated hop, SHELL_NZ its designated wallet); 1 = one transaction from
    # the trust's wallet onto a designated address; 2 = the shells' structured
    # deposits reach a designated address through the trust's wallet.
    expected_hops = {
        str(ring["KINGPIN"]): 0,
        str(ring["SHELL_NZ"]): 0,
        str(ring["TRUST"]): 1,
        str(ring["SHELL_AE"]): 2,
        str(ring["SHELL_TR"]): 2,
        str(ring["SHELL_HK"]): 2,
        str(ring["SHELL_CN"]): 2,
    }
    assert ground_truth["designation_exposure_hops"][live["designation_id"]] == expected_hops

    # The decoy's answer is the empty set across every key — the FP probe.
    for key in ("designation_exposed_uids", "designation_direct_uids",
                "designation_adjacent_uids", "designation_name_match_uids"):
        assert ground_truth[key][decoy["designation_id"]] == []
    assert ground_truth["designation_exposure_hops"][decoy["designation_id"]] == {}


def test_designation_exposed_set_differs_from_legacy_key(ground_truth, designations):
    """The anti-replay property: sweeping the new designation must NOT equal
    replaying the Phase-2 ``sanctioned_exposure_uids`` answer key."""
    live, _ = designations
    exposed = ground_truth["designation_exposed_uids"][live["designation_id"]]
    assert exposed != sorted(ground_truth["sanctioned_exposure_uids"])


def test_designation_named_traps_are_excluded(ground_truth, designations, ring, accounts):
    """The designed negatives, asserted by name (belt to the equality braces):
    EMPLOYEE has legacy sanctioned exposure but no flow to the designated pair;
    RECIDIVIST's flow dead-ends at a wallet with no outbound path; PRIVILEGED is
    device-linked only; noise accounts touch nothing."""
    live, _ = designations
    exposed = set(ground_truth["designation_exposed_uids"][live["designation_id"]])
    assert ring["EMPLOYEE"] not in exposed
    assert ring["EMPLOYEE"] in set(ground_truth["sanctioned_exposure_uids"])  # the trap is real
    assert ring["RECIDIVIST"] not in exposed
    assert ring["PRIVILEGED"] not in exposed
    assert not exposed & set(accounts[accounts.role_in_ring == "noise"].uid)


def test_designation_adjacency_full_equality_and_disjoint(ground_truth, designations, ring):
    """Review-only adjacency: shared-device / reused-KYC linkage to an exposed
    uid. EMPLOYEE (device group with the controller and the trust), PRIVILEGED
    (device group with two exposed shells), SIBLING (KYC document reused by an
    exposed shell) — and nobody else: the second employee and the recidivist
    share devices only with non-exposed accounts."""
    live, _ = designations
    adjacent = ground_truth["designation_adjacent_uids"][live["designation_id"]]
    assert adjacent == sorted({ring["EMPLOYEE"], ring["PRIVILEGED"], ring["SIBLING"]})
    exposed = set(ground_truth["designation_exposed_uids"][live["designation_id"]])
    assert not set(adjacent) & exposed


def test_designation_name_match_key(ground_truth, designations, ring, accounts):
    live, _ = designations
    assert ground_truth["designation_name_match_uids"][live["designation_id"]] == [ring["SHELL_NZ"]]
    # The designated name is a transliteration-style variant, not the exact
    # registered name — the pattern an exact-match screen misses.
    registered = accounts[accounts.uid == ring["SHELL_NZ"]].entity_name.iloc[0]
    assert live["designated_name"] != registered
    assert live["designated_name"].split()[0] == registered.split()[0]


# --------------------------------------------------------------------------- #
# hold tables + reconciliation answer key
# --------------------------------------------------------------------------- #
def test_hold_tables_cover_every_account_exactly_once(data_dir, accounts):
    wh = pd.read_csv(data_dir / "sanctions_hold_warehouse.csv")
    adm = pd.read_csv(data_dir / "sanctions_hold_admin.csv")
    for table in (wh, adm):
        assert sorted(table.uid) == sorted(accounts.uid)
        assert table.uid.is_unique


def test_block_status_gaps_exact(data_dir, ground_truth, ring):
    expected = [
        {"uid": ring["TRUST"], "warehouse_status": "no_hold",
         "admin_status": "blocked", "gap_type": "missed_sync_block"},
        {"uid": ring["SHELL_TR"], "warehouse_status": "blocked",
         "admin_status": "no_hold", "gap_type": "unrecorded_unblock"},
    ]
    assert ground_truth["block_status_gaps"] == expected

    # The CSVs agree with the key row-by-row, and every NON-gap account is
    # consistent across the two systems — the gaps are the only drift.
    wh = pd.read_csv(data_dir / "sanctions_hold_warehouse.csv").set_index("uid")
    adm = pd.read_csv(data_dir / "sanctions_hold_admin.csv").set_index("uid")
    gap_uids = set()
    for gap in expected:
        gap_uids.add(gap["uid"])
        assert wh.loc[gap["uid"], "hold_status"] == gap["warehouse_status"]
        assert adm.loc[gap["uid"], "hold_status"] == gap["admin_status"]
    for uid in wh.index:
        if uid not in gap_uids:
            assert wh.loc[uid, "hold_status"] == adm.loc[uid, "hold_status"]


def test_gaps_sit_on_designation_exposed_accounts(ground_truth, designations):
    """Both planted gaps are on accounts the live designation exposes — the
    sweep cannot surface them by reconciliation alone without the exposure walk."""
    live, _ = designations
    exposed = set(ground_truth["designation_exposed_uids"][live["designation_id"]])
    assert {g["uid"] for g in ground_truth["block_status_gaps"]} <= exposed


def test_new_dates_postdate_activity_and_holds_predate_designation(data_dir, ground_truth):
    """Date coherence for every new table: all designation/hold dates fall
    after the last observed account activity (so the registration-coherence
    guard is untouched), and BOTH planted hold actions predate the designation
    — they are legacy screening actions; the gaps are pre-existing sync
    failures the sweep surfaces, not effects of the designation."""
    last_activity = max(
        str(pd.read_csv(data_dir / "transactions.csv").timestamp.max())[:10],
        str(pd.read_csv(data_dir / "ip_logs.csv").timestamp.max())[:10],
    )
    des = pd.read_csv(data_dir / "designations.csv")
    wh = pd.read_csv(data_dir / "sanctions_hold_warehouse.csv")
    adm = pd.read_csv(data_dir / "sanctions_hold_admin.csv")

    for col, table in (("designation_date", des), ("as_of_date", wh), ("status_date", adm)):
        assert (table[col] > last_activity).all(), col

    designation_date = des.designation_date.min()
    gap_uids = [g["uid"] for g in ground_truth["block_status_gaps"]]
    assert (wh[wh.uid.isin(gap_uids)].as_of_date < designation_date).all()
    assert (adm[adm.uid.isin(gap_uids)].status_date < designation_date).all()
