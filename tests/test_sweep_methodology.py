"""Phase 8: the sweep policy is explainable AND reproducible.

The same two defensibility guards as every other versioned capability — the
EIGHTH doc<->code anti-drift pair: the published methodology doc's canonical
policy block equals ``sweep_config()`` exactly, and the config is stamped into
the sweep's own tamper-evident audit chain once per run.
"""

from __future__ import annotations

import json
from pathlib import Path

from okojo.sweep import SWEEP_VERSION, run_sweep, sweep_config

_DOC = Path(__file__).resolve().parents[1] / "docs" / "sweep-methodology.md"


def _doc_config() -> dict:
    """Extract the canonical JSON policy block embedded in the methodology doc."""
    text = _DOC.read_text(encoding="utf-8")
    lo = text.index("<!-- sweep-config:begin -->")
    hi = text.index("<!-- sweep-config:end -->")
    block = text[lo:hi]
    return json.loads(block[block.index("{"): block.rindex("}") + 1])


def test_methodology_doc_matches_code():
    """The doc's canonical policy block equals sweep_config() exactly — the
    two can never silently drift."""
    assert _doc_config() == sweep_config()


def test_methodology_doc_states_current_version():
    assert f"v{SWEEP_VERSION}" in _DOC.read_text(encoding="utf-8")


def test_methodology_doc_publishes_part_ib_surface():
    """The Part I-B additions are documented, not just coded: the source-list
    registry / visible-absence section, the required-artifact standard, and the
    named-out declared-but-not-ingested regime all appear in the doc."""
    text = _DOC.read_text(encoding="utf-8")
    assert "Source lists — the published registry, and visible absence" in text
    assert "visible absence" in text.lower()
    assert "required-artifact standard" in text.lower()
    # The living visible-absence demonstration is named explicitly.
    assert "SYN-UN-CONSOLIDATED" in text
    assert "conditionally required" in text.lower()  # the empty-address rule


def test_sweep_config_stamped_in_audit(conn, sweep_designations, tmp_path):
    """The sweep policy is written into the sweep's own hash chain exactly
    once, and the chain verifies."""
    live, _ = sweep_designations
    res = run_sweep(live, out_dir=tmp_path / "sweep", conn=conn)
    stamped = [
        r for r in res.audit_records
        if r["actor"] == "remediation_sweep" and r["action"] == "sweep_config"
    ]
    assert len(stamped) == 1, "exactly one sweep_config record expected"
    assert json.loads(stamped[0]["detail"]) == sweep_config()
    assert res.audit_verified
