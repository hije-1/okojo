"""Phase 3: advisory retrieval is explainable AND reproducible.

Two defensibility guards, mirroring ``tests/test_scoring_methodology.py``:
  * the published methodology doc's canonical parameters never drift from the code
    (the doc and ``retrieval_config()`` are one source of truth), and
  * the retrieval config is stamped into the tamper-evident audit trail, so any
    historical advisory match can be reproduced from the record.
"""

from __future__ import annotations

import json
from pathlib import Path

from okojo.advisory import RETRIEVAL_VERSION, retrieval_config
from okojo.orchestrator import run_case

_DOC = Path(__file__).resolve().parents[1] / "docs" / "advisory-methodology.md"


def _doc_config() -> dict:
    """Extract the canonical JSON parameter block embedded in the methodology doc."""
    text = _DOC.read_text(encoding="utf-8")
    lo = text.index("<!-- advisory-config:begin -->")
    hi = text.index("<!-- advisory-config:end -->")
    block = text[lo:hi]
    return json.loads(block[block.index("{"): block.rindex("}") + 1])


def test_methodology_doc_matches_code():
    """The doc's canonical parameter block equals retrieval_config() exactly —
    the two can never silently drift."""
    assert _doc_config() == retrieval_config()


def test_methodology_doc_states_current_version():
    assert f"v{RETRIEVAL_VERSION}" in _DOC.read_text(encoding="utf-8")


def test_retrieval_config_stamped_in_audit(conn, trust_uid, tmp_path):
    """The retrieval config is written into the hash chain, and the chain verifies."""
    res = run_case(trust_uid, conn=conn, out_dir=tmp_path / "case", render_graph=False)
    stamped = [
        r for r in res.audit_records
        if r["actor"] == "advisory_matcher" and r["action"] == "retrieval_config"
    ]
    assert len(stamped) == 1, "exactly one retrieval_config record expected"
    assert json.loads(stamped[0]["detail"]) == retrieval_config()
    assert res.audit_verified
