"""Phase 6: the decision policy is explainable AND reproducible.

Two defensibility guards, mirroring the scoring/retrieval/critic/contradiction
methodology tests:
  * the published methodology doc's canonical policy never drifts from the
    code (the doc and ``agency_config()`` are one source of truth), and
  * the policy is stamped into the tamper-evident audit trail once per run,
    so any historical decision trace can be reproduced from the record.
"""

from __future__ import annotations

import json
from pathlib import Path

from okojo.agency import AGENCY_VERSION, agency_config
from okojo.orchestrator import run_case

_DOC = Path(__file__).resolve().parents[1] / "docs" / "agency-methodology.md"


def _doc_config() -> dict:
    """Extract the canonical JSON policy block embedded in the methodology doc."""
    text = _DOC.read_text(encoding="utf-8")
    lo = text.index("<!-- agency-config:begin -->")
    hi = text.index("<!-- agency-config:end -->")
    block = text[lo:hi]
    return json.loads(block[block.index("{"): block.rindex("}") + 1])


def test_methodology_doc_matches_code():
    """The doc's canonical policy block equals agency_config() exactly —
    the two can never silently drift."""
    assert _doc_config() == agency_config()


def test_methodology_doc_states_current_version():
    assert f"v{AGENCY_VERSION}" in _DOC.read_text(encoding="utf-8")


def test_agency_config_stamped_in_audit(conn, trust_uid, tmp_path):
    """The decision policy is written into the hash chain exactly once, and
    the chain verifies."""
    res = run_case(trust_uid, conn=conn, out_dir=tmp_path / "case", render_graph=False)
    stamped = [
        r for r in res.audit_records
        if r["actor"] == "agency" and r["action"] == "agency_config"
    ]
    assert len(stamped) == 1, "exactly one agency_config record expected"
    assert json.loads(stamped[0]["detail"]) == agency_config()
    assert res.audit_verified


def test_every_decision_is_stamped_and_round_trips(conn, trust_uid, tmp_path):
    """The decision trace the caller sees IS the tamper-evident one: each
    DecisionRecord has exactly one agency/decision stamp whose JSON detail
    round-trips to the in-memory record, in the same order."""
    res = run_case(trust_uid, conn=conn, out_dir=tmp_path / "case", render_graph=False)
    stamped = [
        r for r in res.audit_records
        if r["actor"] == "agency" and r["action"] == "decision"
    ]
    assert len(stamped) == len(res.decisions)
    for record, rec in zip(stamped, res.decisions):
        assert record["target"] == rec.decision_id
        assert json.loads(record["detail"]) == rec.summary()
    assert res.audit_verified
