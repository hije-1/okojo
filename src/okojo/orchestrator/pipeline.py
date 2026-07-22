"""Thin, explicit orchestrator (Phase 1).

Runs one synthetic case end-to-end through a *thin* version of every stage:
connectors -> Profile Aggregator -> Network Expander -> Remark Miner ->
Advisory Matcher -> SAR Drafter -> Case Packager. Control flow is a plain,
legible sequence (the deterministic backbone is itself a compliance feature);
bounded agentic decision points and LangGraph arrive in Phase 6.

Every step is written to the tamper-evident audit log as it happens.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Optional

from ..advisory import AdvisoryMatch, match_advisory
from ..aggregator import ProfileTimeline, build_profile
from ..audit import AuditLog
from ..config import REPO_ROOT
from ..connectors import Connectors
from ..network import NetworkExpansion, expand, render
from ..remarks import AliasMatch, RemarkTell, mine_remarks, screen_aliases
from ..rfi import RfiView, load_rfi
from ..sar import SarDraft, build_sar


@dataclass
class CaseResult:
    subject_uid: int
    subject_name: str
    profile: ProfileTimeline
    expansion: NetworkExpansion
    graph_html_path: Optional[Path]
    tells: list[RemarkTell]
    alias_hits: list[AliasMatch]
    rfi: Optional[RfiView]
    advisory: Optional[AdvisoryMatch]
    sar: SarDraft
    audit_log_path: Path
    audit_records: list[dict] = field(default_factory=list)
    audit_verified: bool = False


def default_out_dir(subject_uid: int) -> Path:
    return REPO_ROOT / "data" / "cases" / f"case_{subject_uid}"


def _rel(path: Path) -> str:
    """Repo-relative path for audit logging — never leak an absolute/home path."""
    try:
        return path.relative_to(REPO_ROOT).as_posix()
    except ValueError:
        return path.name


def run_case(
    subject_uid: int,
    out_dir: Optional[Path] = None,
    conn: Optional[Connectors] = None,
    max_hops: int = 2,
    render_graph: bool = True,
    audit_clock: Optional[Callable[[], str]] = None,
) -> CaseResult:
    """Execute the walking-skeleton pipeline for one subject."""
    owns_conn = conn is None
    conn = conn or Connectors()
    out_dir = Path(out_dir) if out_dir else default_out_dir(subject_uid)
    out_dir.mkdir(parents=True, exist_ok=True)

    audit_path = out_dir / "audit_log.jsonl"
    if audit_path.exists():
        audit_path.unlink()  # fresh chain per run
    audit = AuditLog(audit_path, clock=audit_clock) if audit_clock else AuditLog(audit_path)

    try:
        subject = conn.get_account(subject_uid)
        if subject is None:
            raise ValueError(f"No account with uid {subject_uid}")
        audit.append("orchestrator", "case_open", target=f"uid:{subject_uid}",
                     detail=str(subject["entity_name"]), provenance=subject.provenance)

        # 1) Profile Aggregator
        audit.append("profile_aggregator", "tool_call", target=f"uid:{subject_uid}")
        profile = build_profile(conn, subject_uid)
        audit.append("profile_aggregator", "profile_built", target=f"uid:{subject_uid}",
                     detail=f"{len(profile.events)} events, {len(profile.anomalies)} anomalies")

        # 2) Network Expander
        audit.append("network_expander", "tool_call", target=f"uid:{subject_uid}",
                     detail=f"max_hops={max_hops}")
        expansion = expand(conn, subject_uid, max_hops=max_hops)
        audit.append("network_expander", "expanded", detail=json.dumps(expansion.summary()))
        graph_html_path: Optional[Path] = None
        if render_graph:
            graph_html_path = out_dir / "network.html"
            render(expansion, graph_html_path)
            audit.append("network_expander", "graph_rendered", target=_rel(graph_html_path))

        # 3) Remark / Tell Miner (+ SDN/alias screening of account names)
        audit.append("remark_miner", "tool_call")
        tells = mine_remarks(conn)
        audit.append("remark_miner", "mined", detail=f"{len(tells)} remark tell(s)")
        alias_hits = screen_aliases(conn)
        audit.append("remark_miner", "alias_screened",
                     detail=f"{len(alias_hits)} account name(s) match the synthetic watchlist")

        # 4) Advisory Matcher (event-triggered on RFI text)
        audit.append("advisory_matcher", "tool_call")
        rfis = conn.rfi_for(subject_uid)
        docs = [(r["response_text"], r.provenance) for r in rfis]
        advisory = match_advisory(docs) if docs else None
        audit.append("advisory_matcher", "matched",
                     detail=(advisory.advisory_id if advisory else "no match"),
                     provenance=(advisory.provenance if advisory else None))

        # 4b) RFI surfacing (read-only; claim-by-claim adjudication is Phase 5)
        rfi_view = load_rfi(conn, subject_uid)
        audit.append("rfi_reader", "rfi_surfaced", target=f"uid:{subject_uid}",
                     detail=(rfi_view.rfi_id if rfi_view else "no rfi"),
                     provenance=(rfi_view.provenance if rfi_view else None))

        # 5) SAR Drafter (grounded, template-first)
        audit.append("sar_drafter", "tool_call", target=f"uid:{subject_uid}")
        sar = build_sar(conn, profile, expansion, tells, advisory)
        audit.append("sar_drafter", "drafted", target=f"uid:{subject_uid}",
                     detail=f"{len(sar.claims)} grounded claim(s)")

        # 6) Case Packager
        audit.append("case_packager", "packaged", target=f"uid:{subject_uid}",
                     detail="decision-ready package assembled (human review required)")

        records = audit.read_all()
        verified = audit.verify()

        return CaseResult(
            subject_uid=subject_uid,
            subject_name=str(subject["entity_name"]),
            profile=profile,
            expansion=expansion,
            graph_html_path=graph_html_path,
            tells=tells,
            alias_hits=alias_hits,
            rfi=rfi_view,
            advisory=advisory,
            sar=sar,
            audit_log_path=audit_path,
            audit_records=records,
            audit_verified=verified,
        )
    finally:
        if owns_conn:
            conn.close()
