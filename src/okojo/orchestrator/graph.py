"""LangGraph state machine over the deterministic case backbone (Phase 6).

The component stages are verbatim code motion of the Phase 1-5 linear
pipeline, wired in the same fixed order. Around that backbone sit five
BOUNDED decision points (``okojo.agency``): expand another hop? pull a second
advisory? re-RFI? evidence sufficient to draft? does the SAR clear the bar?
Each decision node calls a pure rule of the evidence state, records a
:class:`DecisionRecord`, and stamps it into the audit chain; the conditional
edge then routes on the *recorded outcome string*, so the path taken through
the graph and the decision trace in the tamper-evident log cannot disagree.

Determinism posture (a compliance feature, not an afterthought):
- Every decision is a deterministic function of the evidence state -- same
  scenario, same decision trace, every time. No stochastic branching exists.
- No checkpointer is ever instantiated -- no UUIDs, no wall clock, and no
  state serialization enter the run path.
- The graph has no parallel fan-out: the runtime executes exactly one node
  per superstep, and the only branches are the five decision routers
  (``build_case_graph().get_graph()`` enumerates the topology; a shape test
  pins the node and edge sets).
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
from ..agency import (
    DecisionRecord,
    RfiFollowUp,
    agency_config,
    decide_expand,
    decide_re_rfi,
    decide_sar_bar,
    decide_second_advisory,
    decide_sufficiency,
    draft_followup,
)
from ..aggregator import ProfileTimeline, build_profile
from ..audit import AuditLog
from ..config import REPO_ROOT
from ..connectors import Connectors
from ..entity import EntityBackbone, build_backbone
from ..network import (
    ExpansionWalk,
    NetworkExpansion,
    clamp_hops,
    finish_walk,
    render,
    start_walk,
    step_walk,
)
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
    hop_cap: int
    walk: ExpansionWalk
    expansion: NetworkExpansion
    graph_html_path: Optional[Path]
    risk: RiskScoring
    backbone: EntityBackbone
    tells: list[RemarkTell]
    alias_hits: list[AliasMatch]
    embedder_name: str
    advisory_matches: list[AdvisoryMatch]
    advisory: Optional[AdvisoryMatch]
    secondary_advisory: Optional[AdvisoryMatch]
    rfi_view: Optional[RfiView]
    rfi_decomposition: Optional[RfiDecomposition]
    contradictions: Optional[ContradictionTable]
    rfi_followup: Optional[RfiFollowUp]
    sar: Optional[SarDraft]
    critique_history: Optional[CritiqueHistory]
    # the bounded decision trace, in the order the decisions were taken
    decisions: list[DecisionRecord]
    audit_records: list[dict]
    audit_verified: bool


def _record_decision(state: CaseState, rec: DecisionRecord) -> CaseState:
    """Append a decision to the trace and stamp it into the audit chain.

    Every bounded decision is logged with its outcome, rationale, and the
    evidence that drove it; the eval asserts each stamp round-trips to the
    in-memory record, so the trace the analyst reviews IS the tamper-evident
    one.
    """
    state["audit"].append("agency", "decision", target=rec.decision_id,
                          detail=json.dumps(rec.summary()))
    return {"decisions": state.get("decisions", []) + [rec]}


def _last_outcome(state: CaseState) -> str:
    """Router: the branch taken is exactly the last recorded outcome."""
    return state["decisions"][-1].outcome


def _case_open(state: CaseState) -> CaseState:
    conn, audit, subject_uid = state["conn"], state["audit"], state["subject_uid"]
    subject = conn.get_account(subject_uid)
    if subject is None:
        raise ValueError(f"No account with uid {subject_uid}")
    audit.append("orchestrator", "case_open", target=f"uid:{subject_uid}",
                 detail=str(subject["entity_name"]), provenance=subject.provenance)
    # Stamp the versioned decision policy into the hash chain once per run, so
    # any historical decision trace can be reproduced exactly — mirroring the
    # scoring/retrieval/critic/contradiction config stamps.
    audit.append("agency", "agency_config", detail=json.dumps(agency_config()))
    return {"subject_name": str(subject["entity_name"])}


def _profile(state: CaseState) -> CaseState:
    conn, audit, subject_uid = state["conn"], state["audit"], state["subject_uid"]
    audit.append("profile_aggregator", "tool_call", target=f"uid:{subject_uid}")
    profile = build_profile(conn, subject_uid)
    audit.append("profile_aggregator", "profile_built", target=f"uid:{subject_uid}",
                 detail=f"{len(profile.events)} events, {len(profile.anomalies)} anomalies")
    return {"profile": profile}


def _network_seed(state: CaseState) -> CaseState:
    conn, audit, subject_uid = state["conn"], state["audit"], state["subject_uid"]
    audit.append("network_expander", "tool_call", target=f"uid:{subject_uid}",
                 detail=f"max_hops={state['max_hops']}")
    return {"walk": start_walk(conn, subject_uid),
            "hop_cap": clamp_hops(state["max_hops"])}


def _network_hop(state: CaseState) -> CaseState:
    step_walk(state["conn"], state["walk"])
    return {"walk": state["walk"]}


def _decide_expand(state: CaseState) -> CaseState:
    walk, cap = state["walk"], state["hop_cap"]
    rec = decide_expand(
        hops_done=len(walk.hop_stats), cap=cap,
        new_accounts_last_hop=walk.hop_stats[-1]["new_accounts"],
    )
    return _record_decision(state, rec)


def _network_finalize(state: CaseState) -> CaseState:
    conn, audit = state["conn"], state["audit"]
    # max_hops records the cap the walk ran under: an early frontier-exhausted
    # stop skipped only provably no-op hops, so the summary (which feeds the
    # audit chain) is identical to a fixed walk to the cap.
    expansion = finish_walk(conn, state["walk"], max_hops=state["hop_cap"])
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


def _decide_second_advisory(state: CaseState) -> CaseState:
    return _record_decision(state, decide_second_advisory(state["advisory_matches"]))


def _attach_secondary(state: CaseState) -> CaseState:
    # Surfaced for the analyst only — the SAR drafter consumes the primary
    # match alone (a published boundary in agency_config / the methodology doc).
    secondary = state["advisory_matches"][1]
    state["audit"].append("advisory_matcher", "secondary_surfaced",
                          detail=secondary.advisory_id,
                          provenance=secondary.provenance)
    return {"secondary_advisory": secondary}


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


def _decide_re_rfi(state: CaseState) -> CaseState:
    return _record_decision(state, decide_re_rfi(state["contradictions"]))


def _draft_rfi_followup(state: CaseState) -> CaseState:
    # Drafted and proposed to the human investigator, never sent.
    followup = draft_followup(state["contradictions"])
    state["audit"].append(
        "agency", "rfi_followup_drafted", target=followup.rfi_id,
        detail=json.dumps({"questions": len(followup.questions),
                           "claim_ids": [q.claim_id for q in followup.questions]}),
        provenance=[a.provenance for a in state["contradictions"].contradictions],
    )
    return {"rfi_followup": followup}


def _decide_sufficiency(state: CaseState) -> CaseState:
    profile = state["profile"]
    rec = decide_sufficiency(
        subject_resolved="subject_name" in state,
        event_count=len(profile.events),
    )
    return _record_decision(state, rec)


def _human_referral(state: CaseState) -> CaseState:
    # The negative branch of the sufficiency gate: no draft is attempted and
    # nothing is fabricated — the case goes to a human with the gap named.
    # (Never taken on the planted scenario, where every roster subject grounds
    # a draft attempt; exercised by unit tests on sparse synthetic states.)
    audit, subject_uid = state["audit"], state["subject_uid"]
    audit.append("orchestrator", "human_referral", target=f"uid:{subject_uid}",
                 detail=json.dumps({
                     "disposition": "insufficient_evidence",
                     "note": "referred to a human investigator; no SAR draft "
                             "attempted (nothing is fabricated)",
                 }))
    return {"sar": None, "critique_history": None}


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


def _decide_sar_bar(state: CaseState) -> CaseState:
    # Records the disposition; both outcomes proceed to packaging, because a
    # human reviews and decides either way — this decision never files.
    return _record_decision(state, decide_sar_bar(state["critique_history"]))


def _package(state: CaseState) -> Optional[CaseState]:
    audit, subject_uid = state["audit"], state["subject_uid"]
    audit.append("case_packager", "packaged", target=f"uid:{subject_uid}",
                 detail="decision-ready package assembled (human review required)")
    return None  # audit stamp only; None (not {}) is LangGraph's no-state-update


def _finalize(state: CaseState) -> CaseState:
    audit = state["audit"]
    return {"audit_records": audit.read_all(), "audit_verified": audit.verify()}


# Node ids reuse the audit-actor vocabulary where a node is a component stage,
# and a decide_*/effect vocabulary for the bounded decision points — so the
# graph shape reads like the audit trail it produces, and every branch in the
# topology corresponds to a stamped decision outcome.
_NODES: tuple[tuple[str, object], ...] = (
    ("case_open", _case_open),
    ("profile_aggregator", _profile),
    ("network_seed", _network_seed),
    ("network_hop", _network_hop),
    ("decide_expand", _decide_expand),
    ("network_finalize", _network_finalize),
    ("risk_scorer", _risk),
    ("entity_backbone", _backbone),
    ("remark_miner", _tells),
    ("advisory_matcher", _advisory),
    ("decide_second_advisory", _decide_second_advisory),
    ("attach_secondary", _attach_secondary),
    ("rfi_reader", _rfi),
    ("rfi_checker", _contradictions),
    ("decide_re_rfi", _decide_re_rfi),
    ("draft_rfi_followup", _draft_rfi_followup),
    ("decide_sufficiency", _decide_sufficiency),
    ("sar_drafter", _sar),
    ("human_referral", _human_referral),
    ("decide_sar_bar", _decide_sar_bar),
    ("case_packager", _package),
    ("audit_finalize", _finalize),
)


@lru_cache(maxsize=1)
def build_case_graph():
    """Compile the case graph once; the compiled graph is stateless per-invoke.

    The backbone is fixed; the only branches are the five bounded decision
    points, each routed by the outcome string of the decision just recorded
    (so the trace in the audit chain and the path through the graph cannot
    disagree).
    """
    g = StateGraph(CaseState)
    for name, fn in _NODES:
        g.add_node(name, fn)

    g.add_edge(START, "case_open")
    g.add_edge("case_open", "profile_aggregator")
    g.add_edge("profile_aggregator", "network_seed")

    # D1 expand_hop: the first hop always runs (cap >= 1); after each hop the
    # decision either continues the loop or finalizes the expansion.
    g.add_edge("network_seed", "network_hop")
    g.add_edge("network_hop", "decide_expand")
    g.add_conditional_edges("decide_expand", _last_outcome, {
        "continue": "network_hop",
        "stop_cap": "network_finalize",
        "stop_frontier_exhausted": "network_finalize",
    })

    g.add_edge("network_finalize", "risk_scorer")
    g.add_edge("risk_scorer", "entity_backbone")
    g.add_edge("entity_backbone", "remark_miner")
    g.add_edge("remark_miner", "advisory_matcher")

    # D2 second_advisory: surface the runner-up match, or move on.
    g.add_edge("advisory_matcher", "decide_second_advisory")
    g.add_conditional_edges("decide_second_advisory", _last_outcome, {
        "pull_second": "attach_secondary",
        "single_match": "rfi_reader",
        "no_match": "rfi_reader",
    })
    g.add_edge("attach_secondary", "rfi_reader")

    g.add_edge("rfi_reader", "rfi_checker")

    # D3 re_rfi: draft a follow-up for contradicted claims, or move on.
    g.add_edge("rfi_checker", "decide_re_rfi")
    g.add_conditional_edges("decide_re_rfi", _last_outcome, {
        "recommend_re_rfi": "draft_rfi_followup",
        "no_contradictions": "decide_sufficiency",
        "not_applicable": "decide_sufficiency",
    })
    g.add_edge("draft_rfi_followup", "decide_sufficiency")

    # D4 sufficiency: attempt a fail-closed draft, or refer to a human.
    g.add_conditional_edges("decide_sufficiency", _last_outcome, {
        "sufficient": "sar_drafter",
        "insufficient": "human_referral",
    })

    # D5 sar_bar: record the disposition; both outcomes package for human review.
    g.add_edge("sar_drafter", "decide_sar_bar")
    g.add_edge("decide_sar_bar", "case_packager")
    g.add_edge("human_referral", "case_packager")

    g.add_edge("case_packager", "audit_finalize")
    g.add_edge("audit_finalize", END)
    return g.compile()
