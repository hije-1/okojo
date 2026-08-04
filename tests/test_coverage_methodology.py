"""COVERAGE: the coverage policy is explainable AND reproducible.

The same defensibility guard as every other versioned capability — the TWELFTH
doc<->code anti-drift pair: the published methodology doc's canonical policy
block equals ``coverage_config()`` exactly, so the two can never silently drift.
"""

from __future__ import annotations

import json
from pathlib import Path

from okojo.coverage import COVERAGE_VERSION, coverage_config

_DOC = Path(__file__).resolve().parents[1] / "docs" / "coverage-methodology.md"


def _doc_config() -> dict:
    text = _DOC.read_text(encoding="utf-8")
    lo = text.index("<!-- coverage-config:begin -->")
    hi = text.index("<!-- coverage-config:end -->")
    block = text[lo:hi]
    return json.loads(block[block.index("{"): block.rindex("}") + 1])


def test_methodology_doc_matches_code():
    """The doc's canonical policy block equals coverage_config() exactly."""
    assert _doc_config() == coverage_config()


def test_methodology_doc_states_current_version():
    assert f"v{COVERAGE_VERSION}" in _DOC.read_text(encoding="utf-8")


def test_methodology_doc_publishes_the_surface():
    """The design commitments are documented, not just coded: the three legs,
    the two gap classes, visible absence, and the territory-scoping annotation."""
    text = _DOC.read_text(encoding="utf-8")
    assert "visible absence" in text.lower()
    assert "no-coverage" in text.lower() and "ingestion gap" in text.lower()
    assert "nationality" in text.lower()
    # The living demonstrations are named explicitly.
    assert "SYN-UN-CONSOLIDATED" in text or "UN-style" in text
    assert "XV" in text and "QZ" in text
