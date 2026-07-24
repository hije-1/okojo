"""Case orchestrator — a LangGraph state machine over a deterministic backbone.

Phase 6: the fixed Phase 1-5 sequence now runs as a compiled LangGraph
(``okojo.orchestrator.graph``) whose nodes are the same stage functions in the
same order: connectors -> Profile Aggregator -> Network Expander -> Risk
Scorer -> Remark Miner -> Advisory Matcher -> RFI surfacing -> RFI
Contradiction-Checker -> SAR Drafter + Critic -> Case Packager. The backbone
stays deterministic by design (a compliance feature); bounded agentic decision
points are added as dedicated decision nodes, never as hidden control flow.

Every step is written to the tamper-evident audit log as it happens.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Optional

from ..advisory import AdvisoryMatch
from ..agency import DecisionRecord, RfiFollowUp
from ..aggregator import ProfileTimeline
from ..audit import AuditLog
from ..casegraph import CaseGraphStore, RecidivismView
from ..config import REPO_ROOT
from ..connectors import Connectors
from ..network import NetworkExpansion
from ..remarks import AliasMatch, RemarkTell
from ..rfi import ContradictionTable, RfiDecomposition, RfiView
from ..sar import Critique, CritiqueHistory, SarDraft
from ..scorer import RiskScoring
from .graph import CaseState, build_case_graph


@dataclass
class CaseResult:
    subject_uid: int
    subject_name: str
    profile: ProfileTimeline
    expansion: NetworkExpansion
    graph_html_path: Optional[Path]
    risk: RiskScoring
    tells: list[RemarkTell]
    alias_hits: list[AliasMatch]
    rfi: Optional[RfiView]
    rfi_decomposition: Optional[RfiDecomposition]
    contradictions: Optional[ContradictionTable]
    advisory: Optional[AdvisoryMatch]
    # None only when the sufficiency gate referred the case to a human
    # (insufficient evidence to ground a draft attempt).
    sar: Optional[SarDraft]
    critique: Optional[Critique]
    critique_history: Optional[CritiqueHistory]
    audit_log_path: Path
    advisory_embedder: str = ""
    audit_records: list[dict] = field(default_factory=list)
    audit_verified: bool = False
    # Phase 6: the bounded decision trace and the decision effects.
    decisions: list[DecisionRecord] = field(default_factory=list)
    secondary_advisory: Optional[AdvisoryMatch] = None
    rfi_followup: Optional[RfiFollowUp] = None
    # Phase 6: what the persistent case graph knew at case open.
    recidivism: Optional[RecidivismView] = None
    # Phase 6: the decision-ready package, built on the audit trail.
    package_path: Optional[Path] = None
    package_sha256: Optional[str] = None


def default_out_dir(subject_uid: int) -> Path:
    return REPO_ROOT / "data" / "cases" / f"case_{subject_uid}"


def run_case(
    subject_uid: int,
    out_dir: Optional[Path] = None,
    conn: Optional[Connectors] = None,
    max_hops: int = 2,
    render_graph: bool = True,
    audit_clock: Optional[Callable[[], str]] = None,
    case_store_path: Optional[Path] = None,
) -> CaseResult:
    """Execute the case graph for one subject."""
    owns_conn = conn is None
    conn = conn or Connectors()
    # Case-store resolution is two-tier ON PURPOSE: the shared store under
    # data/cases/ (cross-case persistence, the Streamlit path) applies only
    # when the caller did not scope the run — a caller that passes out_dir
    # (every test) gets a store isolated under that directory, so runs can
    # never leak history into each other through a shared default.
    if case_store_path is None:
        case_store_path = (
            Path(out_dir) / "case_graph.sqlite" if out_dir is not None
            else REPO_ROOT / "data" / "cases" / "case_graph.sqlite"
        )
    out_dir = Path(out_dir) if out_dir else default_out_dir(subject_uid)
    out_dir.mkdir(parents=True, exist_ok=True)

    audit_path = out_dir / "audit_log.jsonl"
    if audit_path.exists():
        audit_path.unlink()  # fresh chain per run
    audit = AuditLog(audit_path, clock=audit_clock) if audit_clock else AuditLog(audit_path)

    initial: CaseState = {
        "subject_uid": subject_uid,
        "max_hops": max_hops,
        "render_graph": render_graph,
        "out_dir": out_dir,
        "conn": conn,
        "audit": audit,
        "case_store": CaseGraphStore(Path(case_store_path)),
    }
    try:
        final = build_case_graph().invoke(initial, config={"recursion_limit": 100})
        critique_history = final["critique_history"]
        return CaseResult(
            subject_uid=subject_uid,
            subject_name=final["subject_name"],
            profile=final["profile"],
            expansion=final["expansion"],
            graph_html_path=final["graph_html_path"],
            risk=final["risk"],
            tells=final["tells"],
            alias_hits=final["alias_hits"],
            rfi=final["rfi_view"],
            rfi_decomposition=final["rfi_decomposition"],
            contradictions=final["contradictions"],
            advisory=final["advisory"],
            sar=final["sar"],
            critique=critique_history.final if critique_history else None,
            critique_history=critique_history,
            audit_log_path=audit_path,
            advisory_embedder=final["embedder_name"],
            audit_records=final["audit_records"],
            audit_verified=final["audit_verified"],
            decisions=final.get("decisions", []),
            secondary_advisory=final.get("secondary_advisory"),
            rfi_followup=final.get("rfi_followup"),
            recidivism=final.get("recidivism"),
            package_path=final.get("package_path"),
            package_sha256=final.get("package_sha256"),
        )
    finally:
        if owns_conn:
            conn.close()
