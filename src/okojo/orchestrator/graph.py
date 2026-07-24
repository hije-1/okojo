"""LangGraph state machine over the deterministic case backbone (Phase 6).

Slice A is a *mechanical* conversion: every node below is verbatim code motion
of the corresponding stage block from the Phase 1-5 linear pipeline, wired in
the same fixed order. Outputs, audit stamps, and stamp order are identical to
the linear orchestrator this replaces (a byte-identity test pins it). Bounded
agentic decision points arrive as dedicated decision nodes in a later slice.

Determinism posture (a compliance feature, not an afterthought):
- No checkpointer is ever instantiated -- no UUIDs, no wall clock, and no
  state serialization enter the run path.
- The graph has no fan-out, so the runtime executes exactly one node per
  superstep in a fixed, inspectable order (``build_case_graph().get_graph()``
  enumerates it; a shape test pins the node and edge sets).
- Tracing/telemetry stays disabled: Okojo never sets the LANGCHAIN_*/
  LANGSMITH_* environment variables, and a guard test asserts the run path
  opens no network sockets.
"""

from __future__ import annotations

import json
import warnings
from functools import lru_cache
from pathlib import Path
from typing import Optional, TypedDict

with warnings.catch_warnings(record=True):
    # langgraph's package import pulls in its checkpoint serializer, which
    # emits a langchain-core pending-deprecation warning -- and langchain-core
    # force-surfaces its own warnings by PREPENDING a filter at import time,
    # so an ordinary "ignore" filter (ours or pytest's) cannot win. Recording
    # swallows the import-time noise instead. Scoped to this import only;
    # Okojo never instantiates a checkpointer, so the warned-about API is
    # never on our run path.
    from langgraph.graph import END, START, StateGraph

from ..advisory import (
    AdvisoryMatch,
    build_advisory_retriever,
    build_structured_context,
    load_advisories,
    match_advisories,
    retrieval_config,
)
from ..advisory.embeddings import get_embedder
from ..aggregator import ProfileTimeline, build_profile
from ..audit import AuditLog
from ..config import REPO_ROOT
from ..connectors import Connectors
from ..entity import EntityBackbone, build_backbone
from ..network import NetworkExpansion, expand, render
from ..remarks import AliasMatch, RemarkTell, mine_remarks, screen_aliases
from ..rfi import (
    ContradictionTable,
    RfiDecomposition,
    RfiView,
    check_contradictions,
    contradiction_config,
    decompose,
    load_rfi,
)
from ..sar import (
    CritiqueHistory,
    SarDraft,
    critic_config,
    draft_with_critic,
    validate_grounding,
)
from ..scorer import RiskScoring, score_risk


def _rel(path: Path) -> str:
    """Repo-relative path for audit logging — never leak an absolute/home path."""
    try:
        return path.relative_to(REPO_ROOT).as_posix()
    except ValueError:
        return path.name


class CaseState(TypedDict, total=False):
    """Everything one case run carries between nodes.

    Legibility is the point: the full evidence state at any node boundary is
    this one flat, typed mapping — nothing hides in closures or globals. The
    ``conn`` and ``audit`` handles are passed by reference (never serialized;
    no checkpointer exists to try).
    """

    # run inputs
    subject_uid: int
    max_hops: int
    render_graph: bool
    out_dir: Path
    conn: Connectors
    audit: AuditLog
    # evidence accumulated by the nodes, in pipeline order
    subject_name: str
    profile: ProfileTimeline
    expansion: NetworkExpansion
    graph_html_path: Optional[Path]
    risk: RiskScoring
    backbone: EntityBackbone
    tells: list[RemarkTell]
    alias_hits: list[AliasMatch]
    embedder_name: str
    advisory_matches: list[AdvisoryMatch]
    advisory: Optional[AdvisoryMatch]
    rfi_view: Optional[RfiView]
    rfi_decomposition: Optional[RfiDecomposition]
    contradictions: Optional[ContradictionTable]
    sar: SarDraft
    critique_history: CritiqueHistory
    audit_records: list[dict]
    audit_verified: bool


def _case_open(state: CaseState) -> CaseState:
    conn, audit, subject_uid = state["conn"], state["audit"], state["subject_uid"]
    subject = conn.get_account(subject_uid)
    if subject is None:
        raise ValueError(f"No account with uid {subject_uid}")
    audit.append("orchestrator", "case_open", target=f"uid:{subject_uid}",
                 detail=str(subject["entity_name"]), provenance=subject.provenance)
    return {"subject_name": str(subject["entity_name"])}


def _profile(state: CaseState) -> CaseState:
    conn, audit, subject_uid = state["conn"], state["audit"], state["subject_uid"]
    audit.append("profile_aggregator", "tool_call", target=f"uid:{subject_uid}")
    profile = build_profile(conn, subject_uid)
    audit.append("profile_aggregator", "profile_built", target=f"uid:{subject_uid}",
                 detail=f"{len(profile.events)} events, {len(profile.anomalies)} anomalies")
    return {"profile": profile}


def _network(state: CaseState) -> CaseState:
    conn, audit, subject_uid = state["conn"], state["audit"], state["subject_uid"]
    max_hops = state["max_hops"]
    audit.append("network_expander", "tool_call", target=f"uid:{subject_uid}",
                 detail=f"max_hops={max_hops}")
    expansion = expand(conn, subject_uid, max_hops=max_hops)
    audit.append("network_expander", "expanded", detail=json.dumps(expansion.summary()))
    graph_html_path: Optional[Path] = None
    if state["render_graph"]:
        graph_html_path = state["out_dir"] / "network.html"
        render(expansion, graph_html_path)
        audit.append("network_expander", "graph_rendered", target=_rel(graph_html_path))
    return {"expansion": expansion, "graph_html_path": graph_html_path}


def _risk(state: CaseState) -> CaseState:
    conn, audit, subject_uid = state["conn"], state["audit"], state["subject_uid"]
    audit.append("risk_scorer", "tool_call", target=f"uid:{subject_uid}")
    risk = score_risk(conn, state["expansion"])
    # Stamp the versioned scoring config into the hash chain, so any historical
    # score can be reproduced exactly (defensibility / reproducibility).
    audit.append("risk_scorer", "scoring_config", detail=json.dumps(risk.config))
    audit.append("risk_scorer", "scored", detail=json.dumps(risk.summary()))
    return {"risk": risk}


def _backbone(state: CaseState) -> CaseState:
    # One shared entity backbone — the screener, tell miner, and advisory
    # matcher all query the SAME canonical entity view (not private copies).
    return {"backbone": build_backbone(state["conn"])}


def _tells(state: CaseState) -> CaseState:
    conn, audit = state["conn"], state["audit"]
    backbone = state["backbone"]
    audit.append("remark_miner", "tool_call")
    tells = mine_remarks(conn, backbone=backbone)
    audit.append("remark_miner", "mined", detail=f"{len(tells)} remark tell(s)")
    alias_hits = screen_aliases(conn, backbone=backbone)
    audit.append("remark_miner", "alias_screened",
                 detail=f"{len(alias_hits)} account name(s) match the synthetic watchlist")
    return {"tells": tells, "alias_hits": alias_hits}


def _advisory(state: CaseState) -> CaseState:
    # Advisory Matcher (event-triggered on RFI text; hybrid retrieval +
    # corroboration gate over the shared backbone). One embedder + one
    # retriever per advisory, built once.
    conn, audit = state["conn"], state["audit"]
    audit.append("advisory_matcher", "tool_call")
    embedder = get_embedder()
    advisories = load_advisories()
    retrievers = {a.advisory_id: build_advisory_retriever(a, embedder) for a in advisories}
    # Stamp the versioned retrieval config into the hash chain (reproducibility),
    # mirroring the risk_scorer/scoring_config stamp; record the active embedder
    # so the run is reproducible down to the semantic backend that produced it.
    audit.append("advisory_matcher", "retrieval_config", detail=json.dumps(retrieval_config()))
    audit.append("advisory_matcher", "embedder_active", detail=embedder.name)

    rfis = conn.rfi_for(state["subject_uid"])
    docs = [(r["response_text"], r.provenance) for r in rfis]
    # Structured corroboration evidence: the case's raw jurisdictions (from the
    # backbone) plus grounded watchlist / on-chain-exposure pointers, if any.
    alias_hits, risk = state["alias_hits"], state["risk"]
    watchlist_prov = alias_hits[0].provenance[0] if alias_hits else None
    exposure_prov = next(
        (s.provenance[0] for s in risk.scores if s.exposure_path and s.provenance), None
    )
    structured = build_structured_context(
        state["backbone"], watchlist_provenance=watchlist_prov,
        exposure_provenance=exposure_prov,
    )
    matches = (
        match_advisories(docs, advisories, retrievers=retrievers, structured=structured)
        if docs else []
    )
    advisory = matches[0] if matches else None
    audit.append("advisory_matcher", "matched",
                 detail=(advisory.advisory_id if advisory else "no match"),
                 provenance=(advisory.provenance if advisory else None))
    return {"embedder_name": embedder.name, "advisory_matches": matches,
            "advisory": advisory}


def _rfi(state: CaseState) -> CaseState:
    # RFI surfacing (read-only view for the analyst)
    conn, audit, subject_uid = state["conn"], state["audit"], state["subject_uid"]
    rfi_view = load_rfi(conn, subject_uid)
    audit.append("rfi_reader", "rfi_surfaced", target=f"uid:{subject_uid}",
                 detail=(rfi_view.rfi_id if rfi_view else "no rfi"),
                 provenance=(rfi_view.provenance if rfi_view else None))
    return {"rfi_view": rfi_view}


def _contradictions(state: CaseState) -> CaseState:
    # RFI Contradiction-Checker: decompose the response into discrete claims,
    # then test each adversarially against registry, prior-RFI, on-chain and
    # device evidence. Only the RFI under review is adjudicated; a prior
    # answer is consumed as a rebuttal source.
    conn, audit, subject_uid = state["conn"], state["audit"], state["subject_uid"]
    rfi_view = state["rfi_view"]
    decomposition: Optional[RfiDecomposition] = None
    contradictions: Optional[ContradictionTable] = None
    if rfi_view is not None:
        audit.append("rfi_checker", "tool_call", target=f"uid:{subject_uid}")
        # Stamp the versioned adjudication policy into the hash chain, so any
        # historical verdict can be reproduced exactly (defensibility),
        # mirroring risk_scorer/scoring_config and advisory/retrieval_config.
        audit.append("rfi_checker", "contradiction_config",
                     detail=json.dumps(contradiction_config()))
        decomposition = decompose(conn, subject_uid)
        audit.append("rfi_checker", "decomposed", target=f"uid:{subject_uid}",
                     detail=json.dumps(decomposition.summary()),
                     provenance=decomposition.claims[0].provenance
                     if decomposition and decomposition.claims else None)
        contradictions = check_contradictions(
            conn, subject_uid, state["backbone"], decomposition=decomposition,
        )
        audit.append("rfi_checker", "adjudicated", target=f"uid:{subject_uid}",
                     detail=json.dumps(contradictions.summary()))
        for adj in contradictions.adjudications:
            audit.append("rfi_checker", "claim_verdict",
                         target=f"{contradictions.rfi_id}:{adj.claim_id}",
                         detail=json.dumps(adj.summary()))
    return {"rfi_decomposition": decomposition, "contradictions": contradictions}


def _sar(state: CaseState) -> CaseState:
    # SAR Drafter + Critic (grounded, self-critiquing). draft_with_critic
    # builds a grounded first draft (fail-closed on any uncitable or
    # unresolvable claim), grades it against the FinCEN rubric, and runs a
    # deterministic, bounded revision loop that fills gaps from evidence in
    # hand or flags the residue for human review. Every step is stamped.
    conn, audit, subject_uid = state["conn"], state["audit"], state["subject_uid"]
    audit.append("sar_drafter", "tool_call", target=f"uid:{subject_uid}")
    audit.append("sar_critic", "critic_config", detail=json.dumps(critic_config()))
    sar, critique_history = draft_with_critic(
        conn, state["profile"], state["expansion"], state["tells"],
        state["advisory"], contradictions=state["contradictions"],
    )

    grounding = validate_grounding(conn, sar)
    audit.append("sar_drafter", "grounding_validated", target=f"uid:{subject_uid}",
                 detail=json.dumps(grounding.summary()))
    audit.append("sar_drafter", "drafted", target=f"uid:{subject_uid}",
                 detail=f"{len(sar.claims)} grounded claim(s)")
    # First-pass grade, then one record per bounded revision pass.
    audit.append("sar_critic", "graded", target=f"uid:{subject_uid}",
                 detail=json.dumps(critique_history.initial.summary()))
    for i, (addressed, c) in enumerate(
        zip(critique_history.revisions, critique_history.critiques[1:]), start=1
    ):
        audit.append("sar_critic", "revision", target=f"uid:{subject_uid}",
                     detail=json.dumps({"iteration": i, "addressed": addressed,
                                        "coverage": round(c.coverage, 3)}))
    if critique_history.converged:
        audit.append("sar_critic", "converged", target=f"uid:{subject_uid}",
                     detail=json.dumps(critique_history.final.summary()))
    else:
        audit.append("sar_critic", "human_fallback", target=f"uid:{subject_uid}",
                     detail=json.dumps({"flagged": critique_history.flagged,
                                        "coverage": round(critique_history.final.coverage, 3)}))
    return {"sar": sar, "critique_history": critique_history}


def _package(state: CaseState) -> Optional[CaseState]:
    audit, subject_uid = state["audit"], state["subject_uid"]
    audit.append("case_packager", "packaged", target=f"uid:{subject_uid}",
                 detail="decision-ready package assembled (human review required)")
    return None  # audit stamp only; None (not {}) is LangGraph's no-state-update


def _finalize(state: CaseState) -> CaseState:
    audit = state["audit"]
    return {"audit_records": audit.read_all(), "audit_verified": audit.verify()}


# Node ids reuse the audit-actor vocabulary so the graph shape reads like the
# audit trail it produces.
_NODES: tuple[tuple[str, object], ...] = (
    ("case_open", _case_open),
    ("profile_aggregator", _profile),
    ("network_expander", _network),
    ("risk_scorer", _risk),
    ("entity_backbone", _backbone),
    ("remark_miner", _tells),
    ("advisory_matcher", _advisory),
    ("rfi_reader", _rfi),
    ("rfi_checker", _contradictions),
    ("sar_drafter", _sar),
    ("case_packager", _package),
    ("audit_finalize", _finalize),
)


@lru_cache(maxsize=1)
def build_case_graph():
    """Compile the case graph once; the compiled graph is stateless per-invoke."""
    g = StateGraph(CaseState)
    for name, fn in _NODES:
        g.add_node(name, fn)
    g.add_edge(START, _NODES[0][0])
    for (a, _), (b, _) in zip(_NODES, _NODES[1:]):
        g.add_edge(a, b)
    g.add_edge(_NODES[-1][0], END)
    return g.compile()
