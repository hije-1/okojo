"""Minimal Network Expander (Phase 1).

Seeds from the subject and walks the **synthetic** graph 1-2 hops, linking:

  * on-chain flows (transaction edges between accounts/addresses),
  * account control of addresses (``controls`` edges),
  * shared devices and reused KYC documents (account-to-account edges),
  * gas-funding tells (address-to-address edges) — the move that unmasks the
    controller behind a "non-custodial" wallet.

Returns a :class:`NetworkExpansion` wrapping a networkx graph plus the set of
accounts reached and any synthetic-sanctioned addresses touched. The full
1-7-hop expansion, Elliptic, and risk-weighting arrive in Phase 2; this is the
thin, subject-connected version the walking skeleton needs.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import networkx as nx

from ..connectors import Connectors


def _acct_node(uid: int) -> str:
    return f"acct:{uid}"


def _addr_node(addr: str) -> str:
    return f"addr:{addr}"


def _ref_node(ref: str) -> str:
    """Map a transaction ref ("uid:NNN" or an address) to a graph node id."""
    if ref.startswith("uid:"):
        return _acct_node(int(ref[4:]))
    return _addr_node(ref)


@dataclass
class NetworkExpansion:
    graph: nx.DiGraph
    subject_uid: int
    max_hops: int
    reached_account_uids: list[int] = field(default_factory=list)
    sanctioned_addresses_reached: list[str] = field(default_factory=list)

    def summary(self) -> dict:
        return {
            "subject_uid": self.subject_uid,
            "max_hops": self.max_hops,
            "nodes": self.graph.number_of_nodes(),
            "edges": self.graph.number_of_edges(),
            "accounts_reached": len(self.reached_account_uids),
            "sanctioned_addresses_reached": len(self.sanctioned_addresses_reached),
        }


class _Builder:
    def __init__(self, conn: Connectors, subject_uid: int):
        self.conn = conn
        self.subject_uid = subject_uid
        self.g = nx.DiGraph()

    def add_account(self, uid: int) -> str:
        nid = _acct_node(uid)
        if nid not in self.g:
            acct = self.conn.get_account(uid)
            self.g.add_node(
                nid, kind="account", uid=uid,
                label=(acct["entity_name"] if acct else f"uid:{uid}"),
                role=(acct["role_in_ring"] if acct else None),
                is_subject=(uid == self.subject_uid),
                provenance=f"accounts[uid:{uid}]",
            )
        return nid

    def add_address(self, addr: str) -> str:
        nid = _addr_node(addr)
        if nid not in self.g:
            a = self.conn.get_address(addr)
            controller = None
            sanctioned = False
            addr_label = None
            if a is not None:
                controller = int(a["controller_uid"]) if a["controller_uid"] is not None else None
                sanctioned = bool(a["is_sanctioned_synthetic"])
                addr_label = a["label"]
            self.g.add_node(
                nid, kind="address", address=addr, label=addr[:10],
                sanctioned=sanctioned, controller_uid=controller, addr_label=addr_label,
                provenance=f"addresses[{addr}]",
            )
        return nid

    def ensure_ref(self, ref: str) -> str:
        if ref.startswith("uid:"):
            return self.add_account(int(ref[4:]))
        return self.add_address(ref)

    def add_edge(self, src: str, dst: str, etype: str, provenance: str, **attrs) -> None:
        # Keep the first edge of a given type between two nodes (a DiGraph holds one
        # edge per direction); annotate it so the render can style by relationship.
        if self.g.has_edge(src, dst) and self.g[src][dst].get("etype") == etype:
            return
        self.g.add_edge(src, dst, etype=etype, provenance=provenance, **attrs)


def expand(conn: Connectors, subject_uid: int, max_hops: int = 2) -> NetworkExpansion:
    b = _Builder(conn, subject_uid)
    b.add_account(subject_uid)

    discovered: set[int] = {subject_uid}
    frontier: set[int] = {subject_uid}

    for _ in range(max_hops):
        next_frontier: set[int] = set()
        for uid in frontier:
            acct = conn.get_account(uid)
            src_acct = b.add_account(uid)

            # controls edges + gather this account's refs
            refs = [f"uid:{uid}"]
            for addr_rec in conn.addresses_for(uid):
                addr = addr_rec["address"]
                refs.append(addr)
                b.add_edge(src_acct, b.add_address(addr), "controls", addr_rec.provenance.cite())

            # transaction edges + counterparty discovery
            for ref in refs:
                for tx in conn.transactions_touching(ref):
                    fn = b.ensure_ref(tx["from_ref"])
                    tn = b.ensure_ref(tx["to_ref"])
                    b.add_edge(
                        fn, tn, "transaction", tx.provenance.cite(),
                        amount=float(tx["amount_usdt"]), remark=(tx["remark"] or ""),
                        structured=bool(tx["is_structured_round_number"]),
                    )
                    for r in (tx["from_ref"], tx["to_ref"]):
                        cid = None
                        if r.startswith("uid:"):
                            cid = int(r[4:])
                        else:
                            a = conn.get_address(r)
                            if a is not None and a["controller_uid"] is not None:
                                cid = int(a["controller_uid"])
                        if cid is not None and cid not in discovered:
                            discovered.add(cid)
                            next_frontier.add(cid)

            # shared-device edges
            for dev in conn.devices_for(uid):
                for co in conn.accounts_on_device(dev["device_fingerprint"]):
                    cu = co["uid"]
                    if cu == uid:
                        continue
                    b.add_edge(src_acct, b.add_account(cu), "shared_device", dev.provenance.cite())
                    if cu not in discovered:
                        discovered.add(cu)
                        next_frontier.add(cu)

            # reused-KYC edges
            if acct is not None:
                for co in conn.accounts_with_kyc(acct["kyc_doc_id"]):
                    cu = co["uid"]
                    if cu == uid:
                        continue
                    b.add_edge(src_acct, b.add_account(cu), "reused_kyc", co.provenance.cite())
                    if cu not in discovered:
                        discovered.add(cu)
                        next_frontier.add(cu)

        frontier = next_frontier

    # gas-funding edges among addresses already in the graph (the controller tell)
    for gf in conn.gas_funds():
        funder, funded = gf["funder_address"], gf["funded_address"]
        if _addr_node(funder) in b.g or _addr_node(funded) in b.g:
            b.add_edge(
                b.add_address(funder), b.add_address(funded),
                "gas_funding", gf.provenance.cite(),
            )

    sanctioned = [
        data["address"] for _, data in b.g.nodes(data=True)
        if data.get("kind") == "address" and data.get("sanctioned")
    ]
    return NetworkExpansion(
        graph=b.g,
        subject_uid=subject_uid,
        max_hops=max_hops,
        reached_account_uids=sorted(discovered),
        sanctioned_addresses_reached=sorted(sanctioned),
    )
