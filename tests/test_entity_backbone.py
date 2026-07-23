"""Shared entity backbone — one canonical entity view, delegated to by the
SDN screener and the tell miner without changing their outputs."""

from __future__ import annotations

from okojo.entity import build_backbone
from okojo.remarks import mine_remarks, screen_aliases

# The tell miner's pre-backbone stop list + derivation, inlined here as a frozen
# reference so the backbone's token derivation can't silently drift.
_LEGACY_STOP = {
    "and", "the", "group", "trading", "limited", "ltd", "llc", "inc", "plc",
    "company", "co", "partners", "holdings", "trust", "capital", "global",
    "international", "services", "sons", "llp", "gmbh",
}


def _legacy_alias_terms(conn) -> list[str]:
    terms: set[str] = set()
    for acct in conn.all_accounts():
        if acct["role_in_ring"] == "noise":
            continue
        for token in str(acct["entity_name"]).replace(",", " ").split():
            t = token.strip(".").lower()
            if len(t) >= 4 and t.isalpha() and t not in _LEGACY_STOP:
                terms.add(t)
    return sorted(terms)


def test_backbone_covers_all_accounts_and_watchlist(conn):
    bb = build_backbone(conn)
    assert len(bb.entities) == len(conn.all_accounts())
    assert len(bb.watchlist) == len(conn.sdn_list())


def test_entities_are_grounded_and_indexed(conn):
    bb = build_backbone(conn)
    for e in bb.entities:
        assert e.name
        assert e.provenance.source == "accounts"
        assert e.provenance.row_key == f"uid:{e.uid}"
        # lookup returns the same entity object
        assert bb.account(e.uid) is e


def test_watchlist_entities_carry_aliases_and_provenance(conn):
    bb = build_backbone(conn)
    assert bb.watchlist
    for we in bb.watchlist:
        assert we.provenance.source == "sdn_list"
        assert we.provenance.row_key == we.sdn_id
        assert isinstance(we.aliases, list)


def test_distinctive_tokens_match_legacy_derivation(conn):
    # The backbone reproduces the miner's previous alias-token derivation exactly.
    bb = build_backbone(conn)
    assert bb.distinctive_name_tokens() == _legacy_alias_terms(conn)


def test_jurisdictions_populated_for_structured_signal(conn):
    # Jurisdiction data is present (the structured corroborator relies on it):
    # the cross-border ring hubs all appear.
    bb = build_backbone(conn)
    all_juris = {j for e in bb.entities for j in e.jurisdictions}
    assert {"AE", "TR", "HK", "NZ", "CN"}.issubset(all_juris)


def test_watchlist_aliases_preserve_screen_order(conn):
    bb = build_backbone(conn)
    pairs = bb.watchlist_aliases()
    # every alias of every watchlist entity is present, grouped by entity in order
    expected = [(we, a) for we in bb.watchlist for a in we.aliases]
    assert pairs == expected


def test_screener_output_identical_with_shared_backbone(conn):
    # Passing a prebuilt backbone yields byte-identical screening results
    # (genuinely one backbone, not a second copy).
    bb = build_backbone(conn)
    a = [h.model_dump() for h in screen_aliases(conn)]
    b = [h.model_dump() for h in screen_aliases(conn, backbone=bb)]
    assert a == b


def test_miner_output_identical_with_shared_backbone(conn):
    bb = build_backbone(conn)
    a = [h.model_dump() for h in mine_remarks(conn)]
    b = [h.model_dump() for h in mine_remarks(conn, backbone=bb)]
    assert a == b
