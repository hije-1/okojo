"""Slice 4b: scoring is explainable AND reproducible.

Two defensibility guards:
  * the published methodology doc's canonical parameters never drift from the
    code (the doc and ``scoring_config()`` are one source of truth), and
  * the scoring config is stamped into the tamper-evident audit trail, so any
    historical score can be reproduced from the record.
"""

from __future__ import annotations

import json
from pathlib import Path

from okojo.orchestrator import run_case
from okojo.scorer import SCORING_VERSION, scoring_config

_DOC = Path(__file__).resolve().parents[1] / "docs" / "scoring-methodology.md"


def _doc_config() -> dict:
    """Extract the canonical JSON parameter block embedded in the methodology doc."""
    text = _DOC.read_text(encoding="utf-8")
    lo = text.index("<!-- scoring-config:begin -->")
    hi = text.index("<!-- scoring-config:end -->")
    block = text[lo:hi]
    return json.loads(block[block.index("{"): block.rindex("}") + 1])


def test_methodology_doc_matches_code():
    """The doc's canonical parameter block equals scoring_config() exactly —
    the two can never silently drift."""
    assert _doc_config() == scoring_config()


def test_methodology_doc_states_current_version():
    assert f"v{SCORING_VERSION}" in _DOC.read_text(encoding="utf-8")


def test_scoring_config_stamped_in_audit(conn, trust_uid, tmp_path):
    """The scoring config is written into the hash chain, and the chain verifies."""
    res = run_case(trust_uid, conn=conn, out_dir=tmp_path / "case", render_graph=False)
    stamped = [
        r for r in res.audit_records
        if r["actor"] == "risk_scorer" and r["action"] == "scoring_config"
    ]
    assert len(stamped) == 1, "exactly one scoring_config record expected"
    assert json.loads(stamped[0]["detail"]) == scoring_config()
    assert res.audit_verified
