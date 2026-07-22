"""Remark/Tell Miner (Phase 1 — basic string match).

Attribution often breaks open on a single remark: an address labelled with its
controller's nickname, an "aggregation wallet" tag, an off-book fee-share note.
This miner makes that systematic rather than lucky.

Phase 1 uses plain case-insensitive substring matching against (a) a curated set
of high-signal control/illicit phrases and (b) alias terms drawn from the case's
own entity names (so a remark naming a controller matches). Fuzzy matching
across transliterations/nicknames (RapidFuzz) arrives in Phase 2.
"""

from __future__ import annotations

from typing import Iterable, Optional

from pydantic import BaseModel

from ..connectors import Connectors
from ..provenance import Provenance

# Curated control/illicit-arrangement phrases -> why the phrase matters.
DEFAULT_SIGNAL_PHRASES: dict[str, str] = {
    "aggregation wallet": "pooled/aggregation wallet - not a client address (attribution tell)",
    "aggregation fee": "off-book aggregation fee-share arrangement (fee-skim tell)",
    "custody": "custody labelling - a control claim to test, not accept",
}

# Generic tokens to exclude when deriving alias terms from entity names.
_STOP_TOKENS = {
    "and", "the", "group", "trading", "limited", "ltd", "llc", "inc", "plc",
    "company", "co", "partners", "holdings", "trust", "capital", "global",
    "international", "services", "sons", "llp", "gmbh",
}


class RemarkTell(BaseModel):
    tx_id: str
    remark: str
    category: str          # "illicit_phrase" | "control_alias"
    matched_terms: list[str]
    note: str
    provenance: Provenance


def _derive_alias_terms(conn: Connectors) -> list[str]:
    """Distinctive name tokens from non-noise (ring) accounts, used to catch
    remarks that name a controller (e.g. an 'Old <firstname> wallet' nickname)."""
    terms: set[str] = set()
    for acct in conn.all_accounts():
        if acct["role_in_ring"] == "noise":
            continue
        for token in str(acct["entity_name"]).replace(",", " ").split():
            t = token.strip(".").lower()
            if len(t) >= 4 and t.isalpha() and t not in _STOP_TOKENS:
                terms.add(t)
    return sorted(terms)


def mine_remarks(
    conn: Connectors,
    alias_terms: Optional[Iterable[str]] = None,
    signal_phrases: Optional[dict[str, str]] = None,
) -> list[RemarkTell]:
    phrases = signal_phrases if signal_phrases is not None else DEFAULT_SIGNAL_PHRASES
    aliases = list(alias_terms) if alias_terms is not None else _derive_alias_terms(conn)

    hits: list[RemarkTell] = []
    for tx in conn.remarks():
        remark = str(tx["remark"])
        low = remark.lower()

        matched_phrases = [ph for ph in phrases if ph in low]
        if matched_phrases:
            hits.append(RemarkTell(
                tx_id=tx["tx_id"],
                remark=remark,
                category="illicit_phrase",
                matched_terms=matched_phrases,
                note="; ".join(phrases[ph] for ph in matched_phrases),
                provenance=tx.provenance,
            ))

        matched_aliases = [a for a in aliases if a in low]
        if matched_aliases:
            hits.append(RemarkTell(
                tx_id=tx["tx_id"],
                remark=remark,
                category="control_alias",
                matched_terms=matched_aliases,
                note="remark names a known case entity - possible controller attribution",
                provenance=tx.provenance,
            ))

    return hits
