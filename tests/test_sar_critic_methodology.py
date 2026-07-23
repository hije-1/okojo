"""Phase 4: the SAR Critic grade is explainable AND reproducible.

Two defensibility guards, mirroring ``tests/test_scoring_methodology.py`` and
``tests/test_advisory_methodology.py``:
  * the published methodology doc's canonical parameters never drift from the code
    (the doc and ``critic_config()`` are one source of truth), and
  * the critic config is stamped into the tamper-evident audit trail, so any
    historical grade can be reproduced from the record.
"""

from __future__ import annotations

import json
from pathlib import Path

from okojo.orchestrator import run_case
from okojo.sar import CRITIC_VERSION, critic_config

_DOC = Path(__file__).resolve().parents[1] / "docs" / "sar-critic-methodology.md"


def _doc_config() -> dict:
    """Extract the canonical JSON parameter block embedded in the methodology doc."""
    text = _DOC.read_text(encoding="utf-8")
    lo = text.index("<!-- sar-critic-config:begin -->")
    hi = text.index("<!-- sar-critic-config:end -->")
    block = text[lo:hi]
    return json.loads(block[block.index("{"): block.rindex("}") + 1])


def test_methodology_doc_matches_code():
    """The doc's canonical parameter block equals critic_config() exactly —
    the two can never silently drift."""
    assert _doc_config() == critic_config()


def test_methodology_doc_states_current_version():
    assert f"v{CRITIC_VERSION}" in _DOC.read_text(encoding="utf-8")


def test_critic_config_stamped_in_audit(conn, trust_uid, tmp_path):
    """The critic config is written into the hash chain, and the chain verifies."""
    res = run_case(trust_uid, conn=conn, out_dir=tmp_path / "case", render_graph=False)
    stamped = [
        r for r in res.audit_records
        if r["actor"] == "sar_critic" and r["action"] == "critic_config"
    ]
    assert len(stamped) == 1, "exactly one critic_config record expected"
    assert json.loads(stamped[0]["detail"]) == critic_config()
    assert res.audit_verified


def test_critic_lifecycle_is_audited(conn, trust_uid, tmp_path):
    """The full drafter-critic lifecycle is stamped: config -> graded -> terminal."""
    res = run_case(trust_uid, conn=conn, out_dir=tmp_path / "case", render_graph=False)
    actions = [r["action"] for r in res.audit_records if r["actor"] == "sar_critic"]
    assert "critic_config" in actions
    assert "graded" in actions
    assert ("converged" in actions) ^ ("human_fallback" in actions)  # exactly one terminal
