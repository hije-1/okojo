"""Designation exposure walker — reverse BFS over the full ledger.

The sweep OWNS this walker; the case-graph Network Expander is not extended.
The expander is subject-seeded and walks forward from one account; the sweep
is designation-seeded and must classify the whole ledger, so the natural shape
is one reverse adjacency from the designated address set.

Edge semantics are exactly ``{transaction, controls}`` — the same money-flow
discipline as the scorer's exposure membership and the generator's answer-key
helper: a gas-funding link is a control *tell*, never a value flow, so it can
never fabricate exposure. Hop distance is the minimum number of transaction
edges from the subject (its uid or any wallet it controls) to a designated
address; 0 means the subject controls a designated address outright, and
exposure is DIRECT when hops <= ``DIRECT_HOP_MAX``.

Every exposed account carries provenance for the rows that drive its
classification: the address rows proving control and its own first-leg
transactions that start a shortest path toward the designated set. The
adjacency list (shared device / reused KYC linkage to an exposed account) is
review-only — surfaced, never counted as exposure.
"""

from __future__ import annotations

from collections import deque

from pydantic import BaseModel

from ..connectors import Connectors, Record
from ..provenance import Provenance
from . import DIRECT_HOP_MAX


class ExposedAccount(BaseModel):
    uid: int
    entity_name: str
    hops: int
    direct: bool
    tainted_amount_usdt: float
    provenance: list[Provenance]


class AdjacentAccount(BaseModel):
    """Non-flow linkage to an exposed account — a review lead, not exposure."""

    uid: int
    entity_name: str
    link_types: list[str]              # subset of {"shared_device", "reused_kyc"}
    linked_exposed_uids: list[int]
    provenance: list[Provenance]


class ExposureResult(BaseModel):
    designated_addresses: list[str]
    addresses_in_ledger: list[str]
    addresses_not_in_ledger: list[str]
    exposed: list[ExposedAccount]      # ordered by (hops, uid)
    adjacent: list[AdjacentAccount]    # ordered by uid

    def exposed_uids(self) -> list[int]:
        return sorted(e.uid for e in self.exposed)

    def direct_uids(self) -> list[int]:
        return sorted(e.uid for e in self.exposed if e.direct)

    def adjacent_uids(self) -> list[int]:
        return sorted(a.uid for a in self.adjacent)

    def hops_by_uid(self) -> dict[int, int]:
        return {e.uid: e.hops for e in self.exposed}


def sweep_exposure(conn: Connectors, designated_addresses: list[str]) -> ExposureResult:
    """Classify every account's exposure to the designated address set."""
    txs = conn.all_transactions()
    accounts = conn.all_accounts()
    names = {int(a["uid"]): str(a["entity_name"]) for a in accounts}

    # Control map (addresses.csv is the mock address book; controller_uid reads
    # as float through pandas — normalize before any join).
    addr_rows: dict[str, Record] = {}
    controlled: dict[int, list[str]] = {}
    for rec in conn.all_addresses():
        addr = str(rec["address"])
        addr_rows[addr] = rec
        if rec["controller_uid"] is not None:
            controlled.setdefault(int(rec["controller_uid"]), []).append(addr)

    designated = list(designated_addresses)
    in_ledger = [a for a in designated if a in addr_rows]
    not_in_ledger = [a for a in designated if a not in addr_rows]

    # Reverse multi-source BFS over transaction edges: dist[node] = minimum
    # number of transactions from node to any designated address.
    rev: dict[str, list[str]] = {}
    txs_from: dict[str, list[Record]] = {}
    for t in txs:
        rev.setdefault(str(t["to_ref"]), []).append(str(t["from_ref"]))
        txs_from.setdefault(str(t["from_ref"]), []).append(t)

    dist: dict[str, int] = {a: 0 for a in designated}
    dq = deque(designated)
    while dq:
        node = dq.popleft()
        for src in rev.get(node, ()):
            if src not in dist:
                dist[src] = dist[node] + 1
                dq.append(src)

    exposed: list[ExposedAccount] = []
    for acct in accounts:
        uid = int(acct["uid"])
        cluster = [f"uid:{uid}"] + controlled.get(uid, [])
        reached = [dist[n] for n in cluster if n in dist]
        if not reached:
            continue
        hops = min(reached)

        prov: list[Provenance] = []
        tainted = 0.0
        if hops == 0:
            # The subject controls a designated address: cite the address rows
            # proving control; taint = all value through those addresses.
            for addr in controlled.get(uid, []):
                if addr in designated:
                    prov.append(addr_rows[addr].provenance)
                    for t in txs:
                        if addr in (str(t["from_ref"]), str(t["to_ref"])):
                            tainted += float(t["amount_usdt"])
                            prov.append(t.provenance)
        else:
            # First-leg driving transactions: the subject's own transfers that
            # start a shortest path toward the designated set. If the leg
            # leaves a controlled wallet, cite the address row proving control.
            legs: list[Record] = []
            for node in cluster:
                for t in txs_from.get(node, ()):
                    if dist.get(str(t["to_ref"])) == hops - 1:
                        legs.append(t)
                        if node != f"uid:{uid}" and addr_rows[node].provenance not in prov:
                            prov.append(addr_rows[node].provenance)
            for t in sorted(legs, key=lambda r: str(r["tx_id"])):
                tainted += float(t["amount_usdt"])
                prov.append(t.provenance)

        exposed.append(ExposedAccount(
            uid=uid,
            entity_name=names[uid],
            hops=hops,
            direct=hops <= DIRECT_HOP_MAX,
            tainted_amount_usdt=round(tainted, 2),
            provenance=prov,
        ))
    exposed.sort(key=lambda e: (e.hops, e.uid))

    return ExposureResult(
        designated_addresses=designated,
        addresses_in_ledger=in_ledger,
        addresses_not_in_ledger=not_in_ledger,
        exposed=exposed,
        adjacent=_adjacency(conn, {e.uid for e in exposed}, names),
    )


def _adjacency(
    conn: Connectors, exposed_uids: set[int], names: dict[int, str]
) -> list[AdjacentAccount]:
    """Shared-device / reused-KYC linkage from non-exposed to exposed accounts."""
    links: dict[int, dict] = {}

    def _note(uid: int, link_type: str, exposed_in_group: set[int], rows: list[Record]) -> None:
        entry = links.setdefault(uid, {"types": set(), "linked": set(), "prov": []})
        entry["types"].add(link_type)
        entry["linked"] |= exposed_in_group
        for r in rows:
            if r.provenance not in entry["prov"]:
                entry["prov"].append(r.provenance)

    device_groups: dict[str, list[Record]] = {}
    for rec in conn.all_devices():
        device_groups.setdefault(str(rec["device_fingerprint"]), []).append(rec)
    for rows in device_groups.values():
        uids = {int(r["uid"]) for r in rows}
        hit = uids & exposed_uids
        if hit:
            for r in rows:
                if int(r["uid"]) not in exposed_uids:
                    _note(int(r["uid"]), "shared_device", hit, rows)

    kyc_groups: dict[str, list[Record]] = {}
    for rec in conn.all_accounts():
        kyc_groups.setdefault(str(rec["kyc_doc_id"]), []).append(rec)
    for rows in kyc_groups.values():
        if len(rows) < 2:
            continue
        uids = {int(r["uid"]) for r in rows}
        hit = uids & exposed_uids
        if hit:
            for r in rows:
                if int(r["uid"]) not in exposed_uids:
                    _note(int(r["uid"]), "reused_kyc", hit, rows)

    return [
        AdjacentAccount(
            uid=uid,
            entity_name=names[uid],
            link_types=sorted(entry["types"]),
            linked_exposed_uids=sorted(entry["linked"]),
            provenance=entry["prov"],
        )
        for uid, entry in sorted(links.items())
    ]
