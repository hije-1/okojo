"""Remark/Tell Miner (Phase 2 — fuzzy matching).

Attribution often breaks open on a single remark: an address labelled with its
controller's nickname, an "aggregation wallet" tag, an off-book fee-share note.
This miner makes that systematic rather than lucky.

Phase 2 replaces the Phase-1 substring match with **RapidFuzz** so the miner
catches transliterations, nicknames, and minor spelling drift — matching each
free-text remark against (a) a curated set of high-signal control/illicit
phrases and (b) alias terms drawn from the case's own entity names (so a remark
naming a controller matches even when the spelling wobbles). SDN/alias-watchlist
screening of *account names* lives alongside in :mod:`okojo.remarks.screening`.
"""

from __future__ import annotations

from typing import Iterable, Optional

from pydantic import BaseModel
from rapidfuzz import fuzz

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

# Fuzzy thresholds (0-100). Phrases use partial_ratio (a short phrase inside a
# longer remark); aliases use whole-word ratio so a nickname/transliteration is
# caught without short tokens matching unrelated substrings.
_PHRASE_THRESHOLD = 88
_ALIAS_THRESHOLD = 88


class RemarkTell(BaseModel):
    tx_id: str
    remark: str
    category: str          # "illicit_phrase" | "control_alias"
    matched_terms: list[str]
    score: float = 100.0   # best fuzzy match score (0-100)
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
    phrase_threshold: int = _PHRASE_THRESHOLD,
    alias_threshold: int = _ALIAS_THRESHOLD,
) -> list[RemarkTell]:
    phrases = signal_phrases if signal_phrases is not None else DEFAULT_SIGNAL_PHRASES
    aliases = list(alias_terms) if alias_terms is not None else _derive_alias_terms(conn)

    hits: list[RemarkTell] = []
    for tx in conn.remarks():
        remark = str(tx["remark"])
        low = remark.lower()
        words = [w for w in (t.strip(".,").lower() for t in remark.split()) if len(w) >= 4]

        # illicit / control phrases — fuzzy partial match against the whole remark
        matched_phrases: list[str] = []
        best_phrase = 0.0
        for ph in phrases:
            s = fuzz.partial_ratio(ph, low)
            if s >= phrase_threshold:
                matched_phrases.append(ph)
                best_phrase = max(best_phrase, s)
        if matched_phrases:
            hits.append(RemarkTell(
                tx_id=tx["tx_id"], remark=remark, category="illicit_phrase",
                matched_terms=matched_phrases, score=round(best_phrase, 1),
                note="; ".join(phrases[ph] for ph in matched_phrases),
                provenance=tx.provenance,
            ))

        # control aliases — fuzzy whole-word match (catches nicknames/translit.)
        matched_aliases: list[str] = []
        best_alias = 0.0
        for a in aliases:
            for w in words:
                s = fuzz.ratio(a, w)
                if s >= alias_threshold:
                    matched_aliases.append(a)
                    best_alias = max(best_alias, s)
                    break
        if matched_aliases:
            hits.append(RemarkTell(
                tx_id=tx["tx_id"], remark=remark, category="control_alias",
                matched_terms=sorted(set(matched_aliases)), score=round(best_alias, 1),
                note="remark names a known case entity - possible controller attribution",
                provenance=tx.provenance,
            ))

    return hits
