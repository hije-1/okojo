"""Phase 8 Part II: the identity-resolution policy is explainable AND reproducible.

The ninth doc<->code anti-drift pair — the same two defensibility guards as every
other versioned capability: the published methodology doc's canonical policy
block equals ``identity_config()`` exactly, and the config is stamped into the
sweep's tamper-evident audit chain once per run.
"""

from __future__ import annotations

import json
from pathlib import Path

from okojo.identity import IDENTITY_VERSION, identity_config

_DOC = Path(__file__).resolve().parents[1] / "docs" / "identity-methodology.md"


def _doc_config() -> dict:
    """Extract the canonical JSON policy block embedded in the methodology doc."""
    text = _DOC.read_text(encoding="utf-8")
    lo = text.index("<!-- identity-config:begin -->")
    hi = text.index("<!-- identity-config:end -->")
    block = text[lo:hi]
    return json.loads(block[block.index("{"): block.rindex("}") + 1])


def test_methodology_doc_matches_code():
    """The doc's canonical policy block equals identity_config() exactly."""
    assert _doc_config() == identity_config()


def test_methodology_doc_states_current_version():
    assert f"v{IDENTITY_VERSION}" in _DOC.read_text(encoding="utf-8")


def test_methodology_doc_cites_published_standards_and_posture():
    """The transliteration tables cite PUBLISHED romanization conventions, and
    the vendor-agnostic production posture is stated (no vendor named)."""
    text = _DOC.read_text(encoding="utf-8")
    for standard in ("BGN/PCGN", "ISO 9", "ISO 233", "ALA-LC", "UNGEGN"):
        assert standard in text, standard
    assert "commercial screening API" in text
    assert "review-tier" in text.lower()
    # The vendor-agnostic stance is stated positively (no vendor name is embedded
    # here, so this test never introduces a screening-vendor token itself).
    assert "no vendor named or implied" in text.lower()
