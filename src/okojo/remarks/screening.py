"""SDN/alias screening — fuzzy-matches account names against the synthetic watchlist.

Where the remark miner reads free-text, this screens the *registered account
names* against the synthetic SDN/alias watchlist with RapidFuzz. The attack it
defeats: an entity opens under a transliteration variant of a sanctioned name so
an exact-match screen slides past it. Every hit is grounded in both the watchlist
row and the account row (the grounding contract).
"""

from __future__ import annotations

from typing import Optional

from pydantic import BaseModel
from rapidfuzz import fuzz

from ..connectors import Connectors
from ..provenance import Provenance

# WRatio threshold (0-100). Transliteration variants score ~90+; unrelated
# names sit well below, so ~85 cleanly separates true hits from noise.
_SCREEN_THRESHOLD = 85


class AliasMatch(BaseModel):
    uid: int
    entity_name: str
    sdn_id: str
    matched_alias: str
    score: float
    program: str
    provenance: list[Provenance]


def screen_aliases(conn: Connectors, threshold: int = _SCREEN_THRESHOLD) -> list[AliasMatch]:
    """Fuzzy-screen every account name against the synthetic SDN/alias watchlist.

    Returns the strongest above-threshold match per account (a name resembling a
    watchlisted alias despite exact-match evasion).
    """
    watch: list[tuple] = []  # (sdn_record, alias_string)
    for row in conn.sdn_list():
        for alias in str(row["aliases"]).split(";"):
            alias = alias.strip()
            if alias:
                watch.append((row, alias))

    hits: list[AliasMatch] = []
    for acct in conn.all_accounts():
        name = str(acct["entity_name"])
        best: Optional[tuple] = None  # (score, sdn_record, alias)
        for row, alias in watch:
            s = fuzz.WRatio(name, alias)
            if s >= threshold and (best is None or s > best[0]):
                best = (s, row, alias)
        if best is not None:
            s, row, alias = best
            sdn_prov = Provenance(
                source="sdn_list", row_key=row["sdn_id"], detail="synthetic watchlist alias",
            )
            hits.append(AliasMatch(
                uid=acct["uid"], entity_name=name, sdn_id=row["sdn_id"],
                matched_alias=alias, score=round(s, 1), program=str(row["program"]),
                provenance=[sdn_prov, acct.provenance],
            ))
    return hits
