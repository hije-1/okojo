"""Phase 6: the case-graph policy is explainable AND reproducible.

The same two defensibility guards as every other versioned capability:
doc<->code anti-drift on ``casegraph_config()``, and the config stamped into
the tamper-evident audit chain once per run.
"""

from __future__ import annotations

import json
from pathlib import Path

from okojo.casegraph import CASEGRAPH_VERSION, casegraph_config
from okojo.orchestrator import run_case

_DOC = Path(__file__).resolve().parents[1] / "docs" / "casegraph-methodology.md"


def _doc_config() -> dict:
    """Extract the canonical JSON policy block embedded in the methodology doc."""
    text = _DOC.read_text(encoding="utf-8")
    lo = text.index("<!-- casegraph-config:begin -->")
    hi = text.index("<!-- casegraph-config:end -->")
    block = text[lo:hi]
    return json.loads(block[block.index("{"): block.rindex("}") + 1])


def test_methodology_doc_matches_code():
    """The doc's canonical policy block equals casegraph_config() exactly —
    the two can never silently drift."""
    assert _doc_config() == casegraph_config()


def test_methodology_doc_states_current_version():
    assert f"v{CASEGRAPH_VERSION}" in _DOC.read_text(encoding="utf-8")


def test_casegraph_config_stamped_in_audit(conn, trust_uid, tmp_path):
    """The case-graph policy is written into the hash chain exactly once, and
    the chain verifies."""
    res = run_case(trust_uid, conn=conn, out_dir=tmp_path / "case", render_graph=False)
    stamped = [
        r for r in res.audit_records
        if r["actor"] == "case_graph" and r["action"] == "casegraph_config"
    ]
    assert len(stamped) == 1, "exactly one casegraph_config record expected"
    assert json.loads(stamped[0]["detail"]) == casegraph_config()
    assert res.audit_verified
