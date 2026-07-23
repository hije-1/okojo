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
from ..entity import EntityBackbone, build_backbone
from ..provenance import Provenance

# WRatio threshold (0-100). Transliteration variants score ~90+; unrelated
# names sit well below, so ~85 cleanly separates true hits from noise. Public so
# the UI and the methodology doc cite one source of truth.
SCREEN_THRESHOLD = 85


class AliasMatch(BaseModel):
    uid: int
    entity_name: str
    sdn_id: str
    matched_alias: str
    score: float
    program: str
    provenance: list[Provenance]


def screen_aliases(
    conn: Connectors,
    threshold: int = SCREEN_THRESHOLD,
    backbone: Optional[EntityBackbone] = None,
) -> list[AliasMatch]:
    """Fuzzy-screen every account name against the synthetic SDN/alias watchlist.

    Returns the strongest above-threshold match per account (a name resembling a
    watchlisted alias despite exact-match evasion). Account names and watchlist
    aliases are sourced from the shared :class:`EntityBackbone` (one canonical
    entity view); pass a prebuilt ``backbone`` to reuse one across components.
    """
    bb = backbone if backbone is not None else build_backbone(conn)
    watch = bb.watchlist_aliases()  # (WatchlistEntity, alias), in screen order

    hits: list[AliasMatch] = []
    for entity in bb.entities:
        name = entity.name
        best: Optional[tuple] = None  # (score, watchlist_entity, alias)
        for we, alias in watch:
            s = fuzz.WRatio(name, alias)
            if s >= threshold and (best is None or s > best[0]):
                best = (s, we, alias)
        if best is not None:
            s, we, alias = best
            sdn_prov = Provenance(
                source="sdn_list", row_key=we.sdn_id, detail="synthetic watchlist alias",
            )
            hits.append(AliasMatch(
                uid=entity.uid, entity_name=name, sdn_id=we.sdn_id,
                matched_alias=alias, score=round(s, 1), program=str(we.program),
                provenance=[sdn_prov, entity.provenance],
            ))
    return hits
