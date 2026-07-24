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
from ..aggregator import ProfileTimeline
from ..audit import AuditLog
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
    sar: SarDraft
    critique: Optional[Critique]
    critique_history: Optional[CritiqueHistory]
    audit_log_path: Path
    advisory_embedder: str = ""
    audit_records: list[dict] = field(default_factory=list)
    audit_verified: bool = False


def default_out_dir(subject_uid: int) -> Path:
    return REPO_ROOT / "data" / "cases" / f"case_{subject_uid}"


def run_case(
    subject_uid: int,
    out_dir: Optional[Path] = None,
    conn: Optional[Connectors] = None,
    max_hops: int = 2,
    render_graph: bool = True,
    audit_clock: Optional[Callable[[], str]] = None,
) -> CaseResult:
    """Execute the case graph for one subject."""
    owns_conn = conn is None
    conn = conn or Connectors()
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
            critique=critique_history.final,
            critique_history=critique_history,
            audit_log_path=audit_path,
            advisory_embedder=final["embedder_name"],
            audit_records=final["audit_records"],
            audit_verified=final["audit_verified"],
        )
    finally:
        if owns_conn:
            conn.close()
