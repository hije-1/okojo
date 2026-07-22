"""Network roster — a triage view of the accounts in a network expansion.

The graph answers *how* accounts connect; the roster answers *who to look at
next*. Each connected account is a potential case of its own, so we summarise —
per account node — the anomalies it would trip if investigated, whether it
carries the internal "do-not-block" red-herring tag, and whether a case file
already exists on disk. Rows are risk-sorted (subject first) so an investigator
can triage the network without re-driving the case selector by hand.

Pure logic (no UI); the Streamlit app renders these rows and every field is
grounded in the same detectors the Profile Aggregator uses.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from ..aggregator.anomalies import detect_all
from ..connectors import Connectors
from .expander import NetworkExpansion

# The internal-tag red herring is surfaced as its own signal (``internal_flagged``),
# so it is excluded from the generic anomaly-chip list to avoid double-counting.
_INTERNAL_CODE = "internal_account_tag"

_SEVERITY_RANK = {"high": 3, "medium": 2, "low": 1}


@dataclass
class RosterRow:
    uid: int
    name: str
    role: str
    is_subject: bool
    anomaly_codes: list[str] = field(default_factory=list)
    worst_severity: str | None = None  # "high" | "medium" | "low" | None
    internal_flagged: bool = False
    has_case_file: bool = False


def build_roster(
    conn: Connectors,
    expansion: NetworkExpansion,
    cases_dir: Path,
) -> list[RosterRow]:
    """Build the risk-sorted roster of account nodes in ``expansion``.

    Address nodes are excluded (they are not cases). Anomalies are computed for
    each account via :func:`detect_all`, which works for any uid, not just the
    subject. ``has_case_file`` is the only on-disk case signal available in
    Phase 1 — the presence of ``cases_dir / case_<uid>`` from a prior run (a
    persistent case store arrives in Phase 6).
    """
    rows: list[RosterRow] = []
    for _nid, data in expansion.graph.nodes(data=True):
        if data.get("kind") != "account":
            continue
        uid = data["uid"]
        account = conn.get_account(uid)
        anomalies = detect_all(conn, account) if account is not None else []

        codes = [a.code for a in anomalies if a.code != _INTERNAL_CODE]
        internal_flagged = any(a.code == _INTERNAL_CODE for a in anomalies)
        worst = None
        if anomalies:
            worst = max(anomalies, key=lambda a: _SEVERITY_RANK.get(a.severity, 0)).severity

        rows.append(RosterRow(
            uid=uid,
            name=str(data.get("label") or f"uid:{uid}"),
            role=str(data.get("role") or "noise"),
            is_subject=bool(data.get("is_subject")),
            anomaly_codes=codes,
            worst_severity=worst,
            internal_flagged=internal_flagged,
            has_case_file=(cases_dir / f"case_{uid}").exists(),
        ))

    # Subject pinned first, then highest risk, then name for stable ordering.
    rows.sort(key=lambda r: (
        not r.is_subject,
        -_SEVERITY_RANK.get(r.worst_severity or "", 0),
        r.name.lower(),
    ))
    return rows
