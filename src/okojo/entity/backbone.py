"""Shared entity backbone — one canonical view of every entity in a case.

Before this module, four subsystems each built their own ad-hoc notion of "an
entity" from the same synthetic substrate: the SDN screener flattened
``sdn_list`` aliases, the tell miner derived name tokens from account names, and
the network expander/scorer built graph nodes. They were correlated only by
fuzzy string match, never by a shared representation.

:class:`EntityBackbone` is that shared representation. It is assembled once from
the read-only :class:`~okojo.connectors.Connectors` layer and exposes:

* **account entities** — canonical name, distinctive name tokens, entity type,
  jurisdictions (residence / nationality / KYC-issuing country), and the crypto
  wallets each controls (with the synthetic-sanctioned flag);
* **watchlist entities** — the synthetic SDN rows with their alias lists.

The SDN screener and the tell miner now *delegate* to it (one definition of the
alias/token derivation, not a second copy), and the advisory matcher's
structured-corroborator pass queries the same backbone — so a jurisdiction or
sanctioned-address signal means the same thing everywhere. Every entity carries
its :class:`~okojo.provenance.Provenance` pointer, so facts drawn from the
backbone remain grounded.
"""

from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field

from ..connectors import Connectors
from ..provenance import Provenance

# Generic corporate/filler tokens excluded when deriving distinctive name
# tokens. This is the single source of truth for that stop list — the tell
# miner imports the derivation from here rather than keeping its own copy.
STOP_TOKENS: frozenset[str] = frozenset({
    "and", "the", "group", "trading", "limited", "ltd", "llc", "inc", "plc",
    "company", "co", "partners", "holdings", "trust", "capital", "global",
    "international", "services", "sons", "llp", "gmbh",
})


def name_tokens(entity_name: str) -> list[str]:
    """Distinctive tokens from an entity name (>=4 chars, alphabetic, non-stop).

    Preserves the tokenisation the tell miner previously did inline, so the set
    of derived aliases is unchanged: split on commas/whitespace, strip trailing
    dots, lowercase, keep alphabetic tokens of length >= 4 that aren't generic.
    """
    toks: list[str] = []
    for token in str(entity_name).replace(",", " ").split():
        t = token.strip(".").lower()
        if len(t) >= 4 and t.isalpha() and t not in STOP_TOKENS:
            toks.append(t)
    return toks


class EntityAddress(BaseModel):
    """A crypto wallet a canonical entity controls (ground-truth link)."""

    address: str
    network: Optional[str] = None
    is_sanctioned: bool = False
    label: Optional[str] = None


class Entity(BaseModel):
    """Canonical account entity — one per ``uid``."""

    uid: int
    name: str
    entity_type: Optional[str] = None
    role_in_ring: Optional[str] = None
    residence_country: Optional[str] = None
    nationality_country: Optional[str] = None
    jurisdictions: list[str] = Field(default_factory=list)
    name_tokens: list[str] = Field(default_factory=list)
    addresses: list[EntityAddress] = Field(default_factory=list)
    provenance: Provenance

    def controls_sanctioned_address(self) -> bool:
        return any(a.is_sanctioned for a in self.addresses)

    def in_jurisdiction(self, code: str) -> bool:
        return code in self.jurisdictions


class WatchlistEntity(BaseModel):
    """Canonical watchlist (synthetic SDN) entity — one per ``sdn_id``."""

    sdn_id: str
    primary_name: str
    aliases: list[str] = Field(default_factory=list)
    program: Optional[str] = None
    entity_type: Optional[str] = None
    provenance: Provenance


class EntityBackbone:
    """One deduped view of every entity in a case, shared across components."""

    def __init__(self, entities: list[Entity], watchlist: list[WatchlistEntity]):
        self.entities = entities
        self.watchlist = watchlist
        self._by_uid = {e.uid: e for e in entities}

    # -- account lookups ---------------------------------------------------- #
    def account(self, uid: int) -> Optional[Entity]:
        return self._by_uid.get(uid)

    def distinctive_name_tokens(self) -> list[str]:
        """Sorted union of distinctive name tokens across non-noise entities.

        Reproduces the tell miner's previous ``_derive_alias_terms`` exactly.
        """
        terms: set[str] = set()
        for e in self.entities:
            if e.role_in_ring == "noise":
                continue
            terms.update(e.name_tokens)
        return sorted(terms)

    def entities_in_jurisdiction(self, code: str) -> list[Entity]:
        return [e for e in self.entities if code in e.jurisdictions]

    def entities_controlling_sanctioned_address(self) -> list[Entity]:
        return [e for e in self.entities if e.controls_sanctioned_address()]

    # -- watchlist ---------------------------------------------------------- #
    def watchlist_aliases(self) -> list[tuple[WatchlistEntity, str]]:
        """(watchlist-entity, alias) pairs, in ``sdn_list`` / split order.

        Preserves the exact iteration order the SDN screener depended on, so
        its best-match selection (and thus its output) is unchanged.
        """
        out: list[tuple[WatchlistEntity, str]] = []
        for we in self.watchlist:
            for alias in we.aliases:
                out.append((we, alias))
        return out


def build_backbone(conn: Connectors) -> EntityBackbone:
    """Assemble the shared backbone from the read-only connector layer."""
    entities: list[Entity] = []
    for acct in conn.all_accounts():
        uid = acct["uid"]

        # Jurisdictions: declared residence + nationality, plus the KYC-issuing
        # country, order-stable and deduped.
        juris: list[str] = []
        for c in (acct["residence_country"], acct["nationality_country"]):
            if c and c not in juris:
                juris.append(c)
        kyc = conn.get_kyc(acct["kyc_doc_id"]) if acct["kyc_doc_id"] else None
        if kyc and kyc["issuing_country"] and kyc["issuing_country"] not in juris:
            juris.append(kyc["issuing_country"])

        addrs = [
            EntityAddress(
                address=a["address"],
                network=a["network"],
                is_sanctioned=bool(a["is_sanctioned_synthetic"]),
                label=a["label"],
            )
            for a in conn.addresses_for(uid)
        ]

        entities.append(Entity(
            uid=uid,
            name=str(acct["entity_name"]),
            entity_type=acct["entity_type"],
            role_in_ring=acct["role_in_ring"],
            residence_country=acct["residence_country"],
            nationality_country=acct["nationality_country"],
            jurisdictions=juris,
            name_tokens=name_tokens(acct["entity_name"]),
            addresses=addrs,
            provenance=acct.provenance,
        ))

    watchlist: list[WatchlistEntity] = []
    for row in conn.sdn_list():
        aliases = [a.strip() for a in str(row["aliases"]).split(";") if a.strip()]
        watchlist.append(WatchlistEntity(
            sdn_id=row["sdn_id"],
            primary_name=str(row["primary_name"]),
            aliases=aliases,
            program=str(row["program"]),
            entity_type=row["entity_type"],
            provenance=Provenance(source="sdn_list", row_key=row["sdn_id"]),
        ))

    return EntityBackbone(entities, watchlist)
