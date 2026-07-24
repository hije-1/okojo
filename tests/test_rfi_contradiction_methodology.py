"""Phase 5: the contradiction verdict is explainable AND reproducible.

Mirrors the scoring / advisory / SAR-critic methodology guards:
  * the published doc's canonical parameters never drift from the code, and
  * the adjudication policy is stamped into the tamper-evident audit trail, so
    any historical verdict can be reproduced from the record.
"""

from __future__ import annotations

import json
from pathlib import Path

from okojo.orchestrator import run_case
from okojo.rfi import CONTRADICTION_VERSION, contradiction_config

_DOC = Path(__file__).resolve().parents[1] / "docs" / "rfi-contradiction-methodology.md"


def _doc_config() -> dict:
    text = _DOC.read_text(encoding="utf-8")
    lo = text.index("<!-- rfi-contradiction-config:begin -->")
    hi = text.index("<!-- rfi-contradiction-config:end -->")
    block = text[lo:hi]
    return json.loads(block[block.index("{"): block.rindex("}") + 1])


def test_methodology_doc_matches_code():
    """The doc's canonical parameter block equals contradiction_config() exactly."""
    assert _doc_config() == contradiction_config()


def test_methodology_doc_states_current_version():
    assert f"v{CONTRADICTION_VERSION}" in _DOC.read_text(encoding="utf-8")


def test_contradiction_config_stamped_in_audit(conn, trust_uid, tmp_path):
    res = run_case(trust_uid, conn=conn, out_dir=tmp_path / "case", render_graph=False)
    stamped = [
        r for r in res.audit_records
        if r["actor"] == "rfi_checker" and r["action"] == "contradiction_config"
    ]
    assert len(stamped) == 1, "exactly one contradiction_config record expected"
    assert json.loads(stamped[0]["detail"]) == contradiction_config()
    assert res.audit_verified


def test_checker_lifecycle_is_audited(conn, trust_uid, tmp_path):
    """config -> decomposed -> adjudicated -> one verdict record per claim."""
    res = run_case(trust_uid, conn=conn, out_dir=tmp_path / "case", render_graph=False)
    actions = [r["action"] for r in res.audit_records if r["actor"] == "rfi_checker"]
    for expected in ("tool_call", "contradiction_config", "decomposed", "adjudicated"):
        assert expected in actions, expected
    verdicts = [r for r in res.audit_records
                if r["actor"] == "rfi_checker" and r["action"] == "claim_verdict"]
    assert len(verdicts) == len(res.contradictions.adjudications)


def test_audit_detail_is_ascii(conn, trust_uid, tmp_path):
    """Audit text stays ASCII (pyvis/Windows console constraint)."""
    res = run_case(trust_uid, conn=conn, out_dir=tmp_path / "case", render_graph=False)
    for r in res.audit_records:
        detail = r.get("detail") or ""
        assert detail.isascii(), detail
