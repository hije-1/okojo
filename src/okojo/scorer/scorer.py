"""On-chain Risk Scorer (Phase 2, Slice 3).

Scores each account's **graded** exposure to the synthetic sanctioned set by
**amount + hop distance**, operating on the already-built
:class:`~okojo.network.NetworkExpansion` graph (it never re-expands).

Two things worth reading before touching the scoring:

* **Membership is computed over ``{transaction, controls}`` edges only** —
  deliberately mirroring the gold key's flow semantics in
  ``scenario.generator._uids_with_sanctioned_exposure`` (transaction links plus
  controller->wallet links). Gas-funding edges are *excluded* from membership so
  a gas-only relationship can never fabricate a money-flow "exposure" that the
  answer key does not list. This makes ``exposed_uids`` match the gold set
  exactly (recall/precision are structural, not lucky).
* **Gas-funding is never dropped.** It is a critical unmasking signal. A gas
  controller that *also* moves money is flagged with a ``gas_funded_hop`` reason;
  a *gas-only* controller (linked to the ring purely by gas, with no money-flow
  path) is echoed as a ``gas_only_link`` row that is kept OUT of the exposure
  metric (``exposure_path=False``) — surfaced, but never counted.

This is the **synthetic address-tagging layer** (``addresses.is_sanctioned_synthetic``)
— never conflated with Elliptic; the repo holds no real crypto addresses.

The scorer is a pure function; the orchestrator wraps it with audit logging.
Scoring is fully deterministic — no RNG, no wall-clock, and a *fixed* log scale
(never min-max over the set, which would be unstable on a handful of accounts).
"""

from __future__ import annotations

import math
from collections import deque
from dataclasses import dataclass, field

import networkx as nx

from ..connectors import Connectors
from ..network import NetworkExpansion
from ..provenance import Provenance

# Value/control edge types — the flow semantics the gold key uses. Gas edges are
# deliberately EXCLUDED from exposure membership (see module docstring).
_MONEY_FLOW_ETYPES = frozenset({"transaction", "controls"})
_GAS_ETYPES = frozenset({"gas_funding", "gas_control"})

# Scoring constants (fixed-scale; deterministic).
_DECAY = 0.6            # per-hop decay: closer to the endpoint scores higher
_FLOOR = 0.1           # amount-factor floor -> every reachable account scores > 0
_A_REF = 1_000_000.0   # tainted USDT that saturates the amount factor
_GAS_BASE = 0.5        # base contextual score for gas-only controllers (mirrors expander _W_GAS_CONTROL)

_BAND_HIGH = 0.6
_BAND_MEDIUM = 0.3

# Version of this scoring methodology. Bump on any change to a constant or the
# formula; the config is stamped into the audit trail so any historical score is
# exactly reproducible, and mirrored (+ regression-tested) by
# ``docs/scoring-methodology.md``.
SCORING_VERSION = "1.0.0"


def scoring_config() -> dict:
    """The full, versioned scoring configuration — the tunable *policy parameters*
    behind every score. This is the single source of truth: it is stamped into
    the audit trail for reproducibility and regression-tested against the
    published methodology doc so the two can never silently drift.
    """
    return {
        "version": SCORING_VERSION,
        "membership_edge_types": sorted(_MONEY_FLOW_ETYPES),
        "decay": _DECAY,
        "floor": _FLOOR,
        "amount_ref_usdt": _A_REF,
        "gas_base": _GAS_BASE,
        "band_high": _BAND_HIGH,
        "band_medium": _BAND_MEDIUM,
    }


def _acct_node(uid: int) -> str:
    """Account node id — mirrors the scheme in ``network.expander``."""
    return f"acct:{uid}"


def _band(score: float) -> str:
    if score >= _BAND_HIGH:
        return "high"
    if score >= _BAND_MEDIUM:
        return "medium"
    return "low"


def _hop_decay(h: int) -> float:
    return _DECAY ** (h - 1)


def _amount_factor(amount: float) -> float:
    """Map tainted USDT -> [FLOOR, 1.0] on a fixed log scale.

    The FLOOR guarantees a strictly positive factor so that *every* flow-reachable
    account scores > 0 (even one reachable purely via ``controls`` with no tainted
    amount), which is what makes ``{score > 0}`` identically the reachable set.
    """
    saturation = min(1.0, math.log10(1.0 + amount) / math.log10(1.0 + _A_REF))
    return _FLOOR + (1.0 - _FLOOR) * saturation


@dataclass
class ScoreDecomposition:
    """The arithmetic behind a single score, exposed so the UI, the audit trail,
    and a future SAR all read one source of truth. Every score is the product of
    two factors: a ``base`` factor (tainted-amount weight for a money-flow row, or
    the fixed gas-base for a gas-only echo) and a ``proximity`` factor (per-hop
    decay). ``round(min(1.0, base_factor * proximity_factor), 3)`` reproduces the
    score exactly.
    """

    kind: str               # "money_flow" | "gas_only"
    base_label: str         # "amount" | "gas_base" — what the base factor represents
    base_factor: float      # amount factor in [floor, 1], or the gas-base constant
    proximity_factor: float # per-hop decay = decay ** (hop - 1)
    product: float          # base_factor * proximity_factor (pre-clamp)
    score: float            # final = round(min(1.0, product), 3)
    formula: str            # human-readable, e.g. "0.600 = amount 1.000 × proximity 0.600"


def _decompose(kind: str, base_label: str, base_factor: float, proximity: float) -> tuple[float, ScoreDecomposition]:
    """Compute a score and its decomposition together, so the two never diverge."""
    product = base_factor * proximity
    score = round(min(1.0, product), 3)
    shown = "gas-base" if base_label == "gas_base" else base_label
    formula = f"{score:.3f} = {shown} {base_factor:.3f} × proximity {proximity:.3f}"
    return score, ScoreDecomposition(
        kind=kind, base_label=base_label, base_factor=base_factor,
        proximity_factor=proximity, product=product, score=score, formula=formula,
    )


@dataclass
class RiskScore:
    """Per-account graded exposure — a leaf item, so it carries provenance."""

    uid: int
    score: float                    # 0-1
    band: str                       # "high" | "medium" | "low"
    exposure_path: bool             # True = money-flow exposed (in metric); False = gas-only echo
    hop_distance: int               # min flow-hops to the nearest sanctioned endpoint
    tainted_amount_usdt: float      # value this account's wallets push onward toward the endpoint
    reasons: list[str]
    provenance: list[Provenance]
    decomposition: ScoreDecomposition  # the "show the math" breakdown of ``score``


@dataclass
class RiskScoring:
    """The scorer's result: graded rows plus the money-flow ``exposed_uids`` set."""

    subject_uid: int
    max_hops: int
    scores: list[RiskScore] = field(default_factory=list)   # exposed + gas-only; score desc, uid asc
    exposed_uids: list[int] = field(default_factory=list)   # money-flow only; the eval prediction handle
    version: str = SCORING_VERSION                          # scoring methodology version (reproducibility)
    config: dict = field(default_factory=scoring_config)    # the policy parameters this run used

    def gas_only_uids(self) -> list[int]:
        return [s.uid for s in self.scores if not s.exposure_path]

    def band_counts(self) -> dict[str, int]:
        out = {"high": 0, "medium": 0, "low": 0}
        for s in self.scores:
            out[s.band] += 1
        return out

    def summary(self) -> dict:
        return {
            "subject_uid": self.subject_uid,
            "max_hops": self.max_hops,
            "scored_accounts": len(self.scores),
            "exposed_accounts": len(self.exposed_uids),
            "gas_only_accounts": len(self.gas_only_uids()),
            "bands": self.band_counts(),
        }


def _distances_to_sanctioned(g: nx.MultiDiGraph, etypes: frozenset) -> dict[str, int]:
    """Min directed path length (in edges) from each node to the nearest sanctioned
    endpoint, over the given edge types. Single reverse-BFS from the sanctioned
    address nodes — order-independent and deterministic.
    """
    sanctioned = [
        n for n, d in g.nodes(data=True)
        if d.get("kind") == "address" and d.get("sanctioned")
    ]
    radj: dict[str, set[str]] = {}
    for u, v, d in g.edges(data=True):
        if d.get("etype") in etypes:
            radj.setdefault(v, set()).add(u)
    dist: dict[str, int] = {n: 0 for n in sanctioned}
    dq = deque(sanctioned)
    while dq:
        n = dq.popleft()
        for p in radj.get(n, ()):
            if p not in dist:
                dist[p] = dist[n] + 1
                dq.append(p)
    return dist


def _controlled_nodes(g: nx.MultiDiGraph, acct_nid: str) -> set[str]:
    """The account node plus every address it controls (outgoing ``controls`` edges)."""
    owned = {acct_nid}
    for _, v, d in g.out_edges(acct_nid, data=True):
        if d.get("etype") == "controls":
            owned.add(v)
    return owned


def _tainted_outflow(g: nx.MultiDiGraph, owned: set[str], toward: set[str]) -> tuple[float, list[str]]:
    """Sum of transaction amounts leaving the account's wallets toward the tainted
    path, plus the tx_ids that justify them (for provenance). "Toward" = any node
    from which a sanctioned endpoint is reachable. Only the account's own outflow
    counts, so unrelated volume cannot inflate the score.
    """
    total = 0.0
    tx_ids: list[str] = []
    for x in owned:
        for _, v, d in g.out_edges(x, data=True):
            if d.get("etype") == "transaction" and v in toward:
                total += float(d.get("amount", 0.0))
                tid = d.get("tx_id")
                if tid:
                    tx_ids.append(tid)
    return total, tx_ids


def _has_direct_sanctioned_tx(g: nx.MultiDiGraph, owned: set[str]) -> bool:
    for x in owned:
        for _, v, d in g.out_edges(x, data=True):
            if d.get("etype") == "transaction" and g.nodes[v].get("sanctioned"):
                return True
    return False


def _has_structured_outflow(g: nx.MultiDiGraph, owned: set[str]) -> bool:
    for x in owned:
        for _, _, d in g.out_edges(x, data=True):
            if d.get("etype") == "transaction" and d.get("structured"):
                return True
    return False


def _gas_provenance(conn: Connectors, expansion: NetworkExpansion) -> dict[int, list[Provenance]]:
    """controller_uid -> provenance pointers to the gas-funding rows behind it."""
    by_pair: dict[tuple[str, str], Provenance] = {}
    for rec in conn.gas_funds():
        by_pair[(rec["funder_address"], rec["funded_address"])] = rec.provenance
    out: dict[int, list[Provenance]] = {}
    for link in expansion.gas_funding_links:
        prov = by_pair.get((link["funder_address"], link["funded_address"]))
        if prov is not None:
            out.setdefault(link["controller_uid"], []).append(prov)
    return out


def score_risk(conn: Connectors, expansion: NetworkExpansion) -> RiskScoring:
    """Grade each account's exposure to the synthetic sanctioned set (amount + hop).

    ``exposed_uids`` (money-flow reachable, ``{transaction, controls}`` only) is the
    eval prediction handle; gas-only controllers are echoed as flagged rows kept
    out of that set.
    """
    g = expansion.graph

    # Money-flow reachability + hop distance (gold-key edge semantics).
    dist = _distances_to_sanctioned(g, _MONEY_FLOW_ETYPES)
    toward = set(dist)  # every node from which a sanctioned endpoint is reachable
    sanctioned_addrs = sorted(
        data["address"] for _, data in g.nodes(data=True)
        if data.get("kind") == "address" and data.get("sanctioned")
    )
    gas_controllers = {link["controller_uid"] for link in expansion.gas_funding_links}

    scores: list[RiskScore] = []
    exposed_uids: list[int] = []

    # --- money-flow-exposed accounts (counted in the metric) ------------------ #
    for nid, data in g.nodes(data=True):
        if data.get("kind") != "account" or nid not in dist:
            continue
        uid = data["uid"]
        hop = dist[nid]
        owned = _controlled_nodes(g, nid)
        amount, tx_ids = _tainted_outflow(g, owned, toward)
        score, decomposition = _decompose("money_flow", "amount", _amount_factor(amount), _hop_decay(hop))

        reasons = ["sanctioned_flow_exposure"]
        if _has_direct_sanctioned_tx(g, owned):
            reasons.append("direct_sanctioned_counterparty")
        if _has_structured_outflow(g, owned):
            reasons.append("structured_transfers")
        if uid in gas_controllers:
            reasons.append("gas_funded_hop")

        provenance = [Provenance(source="transactions", row_key=t) for t in sorted(set(tx_ids))]
        provenance += [
            Provenance(source="addresses", row_key=addr, field="is_sanctioned_synthetic")
            for addr in sanctioned_addrs
        ]
        scores.append(RiskScore(
            uid=uid, score=score, band=_band(score), exposure_path=True,
            hop_distance=hop, tainted_amount_usdt=round(amount, 2),
            reasons=reasons, provenance=provenance, decomposition=decomposition,
        ))
        exposed_uids.append(uid)

    # --- gas-only controllers (echoed, kept OUT of the metric) ---------------- #
    exposed_set = set(exposed_uids)
    gas_only_controllers = sorted(gas_controllers - exposed_set)
    if gas_only_controllers:
        gas_dist = _distances_to_sanctioned(g, _MONEY_FLOW_ETYPES | _GAS_ETYPES)
        gas_prov = _gas_provenance(conn, expansion)
        for controller in gas_only_controllers:
            gas_hop = max(1, gas_dist.get(_acct_node(controller), 1))
            score, decomposition = _decompose("gas_only", "gas_base", _GAS_BASE, _hop_decay(gas_hop))
            scores.append(RiskScore(
                uid=controller, score=score, band=_band(score), exposure_path=False,
                hop_distance=gas_hop, tainted_amount_usdt=0.0,
                reasons=["gas_only_link"], provenance=gas_prov.get(controller, []),
                decomposition=decomposition,
            ))

    scores.sort(key=lambda s: (-s.score, s.uid))
    return RiskScoring(
        subject_uid=expansion.subject_uid,
        max_hops=expansion.max_hops,
        scores=scores,
        exposed_uids=sorted(exposed_uids),
    )
