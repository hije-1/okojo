"""Network Expander (Phase 2).

Seeds from the subject and walks the **synthetic** graph 1-7 hops, linking:

  * on-chain flows (transaction edges between accounts/addresses),
  * account control of addresses (``controls`` edges),
  * shared devices and reused KYC documents (account-to-account edges),
  * gas-funding tells (address-to-address edges) — the move that unmasks the
    controller behind a "non-custodial" wallet.

Phase 2 upgrades over the walking-skeleton slice:

  * **1-7-hop** BFS (clamped) rather than the fixed 1-2 hops;
  * gas-funding **controller-collapse** — a ``gas_funding`` link from a
    controller's wallet to a "non-custodial" hop attributes that hop to the
    controller (a ``gas_control`` edge) and pulls the controller into the
    cluster, instead of merely annotating already-discovered addresses;
  * per-node **risk weighting** from the graph-local tells, so the render and
    triage read at a glance;
  * a :class:`networkx.MultiDiGraph`, so two accounts that share *both* a device
    and a KYC document keep both edges instead of one overwriting the other.

Returns a :class:`NetworkExpansion` wrapping the graph plus the accounts reached,
the synthetic-sanctioned addresses touched, the gas-funding controller links, and
the accounts with a directed flow path to a sanctioned endpoint. Elliptic-based
illicit classification remains deferred to a later slice.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field

import networkx as nx

from ..connectors import Connectors

_MAX_HOPS_LIMIT = 7

# Edge types that carry value / control (used for sanctioned-flow reachability).
# Relationship edges (shared_device, reused_kyc) are deliberately excluded so a
# shared device cannot fabricate a "flow" path to a sanctioned endpoint.
_FLOW_ETYPES = {"transaction", "controls", "gas_funding", "gas_control"}

# Risk weights for account nodes (summed, then clamped to 1.0).
_W_SANCTIONED_EXPOSURE = 0.5
_W_GAS_CONTROL = 0.5
_W_SHARED_DEVICE = 0.3
_W_REUSED_KYC = 0.3
_W_STRUCTURED = 0.25
_W_RECIDIVIST = 0.4
_W_RING_ROLE = 0.15


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
    graph: nx.MultiDiGraph
    subject_uid: int
    max_hops: int
    reached_account_uids: list[int] = field(default_factory=list)
    sanctioned_addresses_reached: list[str] = field(default_factory=list)
    gas_funding_links: list[dict] = field(default_factory=list)
    sanctioned_exposed_uids: list[int] = field(default_factory=list)

    def summary(self) -> dict:
        return {
            "subject_uid": self.subject_uid,
            "max_hops": self.max_hops,
            "nodes": self.graph.number_of_nodes(),
            "edges": self.graph.number_of_edges(),
            "accounts_reached": len(self.reached_account_uids),
            "sanctioned_addresses_reached": len(self.sanctioned_addresses_reached),
            "gas_funding_links": len(self.gas_funding_links),
            "sanctioned_exposed_accounts": len(self.sanctioned_exposed_uids),
        }

    def risk_ranked_accounts(self) -> list[tuple[int, float, list[str]]]:
        """Account (uid, risk, reasons) triples, highest risk first."""
        out = [
            (data["uid"], data.get("risk", 0.0), data.get("risk_reasons", []))
            for _, data in self.graph.nodes(data=True)
            if data.get("kind") == "account"
        ]
        out.sort(key=lambda t: t[1], reverse=True)
        return out


class _Builder:
    def __init__(self, conn: Connectors, subject_uid: int):
        self.conn = conn
        self.subject_uid = subject_uid
        self.g = nx.MultiDiGraph()

    def add_account(self, uid: int) -> str:
        nid = _acct_node(uid)
        if nid not in self.g:
            acct = self.conn.get_account(uid)
            self.g.add_node(
                nid, kind="account", uid=uid,
                label=(acct["entity_name"] if acct else f"uid:{uid}"),
                role=(acct["role_in_ring"] if acct else None),
                is_subject=(uid == self.subject_uid),
                internal_tag=(acct["internal_tag"] if acct else None),
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
        # One edge per (src, dst, etype). Keying the MultiDiGraph edge by ``etype``
        # keeps parallel relationships (e.g. two accounts sharing BOTH a device and
        # a KYC doc) instead of letting one overwrite the other, while staying
        # idempotent for a repeated same-type edge.
        if self.g.has_edge(src, dst, key=etype):
            return
        self.g.add_edge(src, dst, key=etype, etype=etype, provenance=provenance, **attrs)


def _incident_etypes(g: nx.MultiDiGraph, nid: str) -> set[str]:
    etypes: set[str] = set()
    for _, _, d in g.out_edges(nid, data=True):
        etypes.add(d.get("etype"))
    for _, _, d in g.in_edges(nid, data=True):
        etypes.add(d.get("etype"))
    return etypes


def _has_structured_out(g: nx.MultiDiGraph, nid: str) -> bool:
    return any(
        d.get("etype") == "transaction" and d.get("structured")
        for _, _, d in g.out_edges(nid, data=True)
    )


def _sanctioned_flow_ancestors(g: nx.MultiDiGraph) -> set[str]:
    """Node ids with a directed value/control path to a sanctioned endpoint.

    Walks *backwards* from the sanctioned address nodes over flow edges only, so
    the result is exactly the set of accounts/addresses whose funds can reach a
    synthetic sanctioned endpoint within this subgraph.
    """
    sanctioned = [
        n for n, d in g.nodes(data=True)
        if d.get("kind") == "address" and d.get("sanctioned")
    ]
    radj: dict[str, set[str]] = {}
    for u, v, d in g.edges(data=True):
        if d.get("etype") in _FLOW_ETYPES:
            radj.setdefault(v, set()).add(u)
    exposed: set[str] = set()
    dq = deque(sanctioned)
    while dq:
        n = dq.popleft()
        for p in radj.get(n, ()):
            if p not in exposed:
                exposed.add(p)
                dq.append(p)
    return exposed


def _score_nodes(g: nx.MultiDiGraph, exposed_nodes: set[str], gas_controllers: set[int]) -> None:
    """Annotate every node with a ``risk`` (0-1) and ``risk_reasons`` list."""
    for nid, data in g.nodes(data=True):
        reasons: list[str] = []
        if data.get("kind") == "address":
            if data.get("sanctioned"):
                data["risk"], data["risk_reasons"] = 1.0, ["sanctioned_endpoint"]
                continue
            label = data.get("addr_label") or ""
            if "hop" in label:
                risk, reasons = 0.8, ["non_custodial_hop"]
            elif "controller" in label:
                risk, reasons = 0.4, ["controller_wallet"]
            else:
                risk = 0.15
            if nid in exposed_nodes:
                risk = max(risk, 0.6)
                reasons.append("sanctioned_flow")
            data["risk"], data["risk_reasons"] = round(min(risk, 1.0), 3), reasons
            continue

        # account node
        risk = 0.0
        if nid in exposed_nodes:
            risk += _W_SANCTIONED_EXPOSURE
            reasons.append("sanctioned_exposure")
        if data.get("uid") in gas_controllers:
            risk += _W_GAS_CONTROL
            reasons.append("gas_funding_control")
        etypes = _incident_etypes(g, nid)
        if "shared_device" in etypes:
            risk += _W_SHARED_DEVICE
            reasons.append("shared_device")
        if "reused_kyc" in etypes:
            risk += _W_REUSED_KYC
            reasons.append("reused_kyc")
        if _has_structured_out(g, nid):
            risk += _W_STRUCTURED
            reasons.append("structured_transfers")
        role = data.get("role")
        if role == "recidivist_mule":
            risk += _W_RECIDIVIST
            reasons.append("recidivist")
        elif role not in (None, "noise", "privileged_internal_redherring"):
            risk += _W_RING_ROLE
        if data.get("internal_tag"):
            reasons.append("internal_tag_review")  # FLAG for review, not obeyed
        data["risk"], data["risk_reasons"] = round(min(risk, 1.0), 3), reasons


def expand(conn: Connectors, subject_uid: int, max_hops: int = 2) -> NetworkExpansion:
    max_hops = max(1, min(int(max_hops), _MAX_HOPS_LIMIT))
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

    # gas-funding controller-collapse: a gas link from a controller's wallet to a
    # "non-custodial" hop attributes the hop to that controller and pulls the
    # controller into the cluster — not a passive after-the-fact annotation.
    gas_links: list[dict] = []
    for gf in conn.gas_funds():
        funder, funded = gf["funder_address"], gf["funded_address"]
        fa = conn.get_address(funder)
        controller = int(fa["controller_uid"]) if fa and fa["controller_uid"] is not None else None
        relevant = (
            _addr_node(funder) in b.g
            or _addr_node(funded) in b.g
            or (controller is not None and controller in discovered)
        )
        if not relevant:
            continue
        fnode, dnode = b.add_address(funder), b.add_address(funded)
        b.add_edge(fnode, dnode, "gas_funding", gf.provenance.cite())
        if controller is not None:
            cnode = b.add_account(controller)
            b.add_edge(cnode, dnode, "gas_control", gf.provenance.cite())
            if controller not in discovered:
                discovered.add(controller)
            gas_links.append(
                {"funder_address": funder, "funded_address": funded, "controller_uid": controller}
            )

    exposed_nodes = _sanctioned_flow_ancestors(b.g)
    gas_controllers = {link["controller_uid"] for link in gas_links}
    _score_nodes(b.g, exposed_nodes, gas_controllers)

    sanctioned = [
        data["address"] for _, data in b.g.nodes(data=True)
        if data.get("kind") == "address" and data.get("sanctioned")
    ]
    exposed_uids = sorted(
        data["uid"] for nid, data in b.g.nodes(data=True)
        if data.get("kind") == "account" and nid in exposed_nodes
    )
    return NetworkExpansion(
        graph=b.g,
        subject_uid=subject_uid,
        max_hops=max_hops,
        reached_account_uids=sorted(discovered),
        sanctioned_addresses_reached=sorted(sanctioned),
        gas_funding_links=gas_links,
        sanctioned_exposed_uids=exposed_uids,
    )
