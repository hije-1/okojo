"""Phase 7: the packaging policy is explainable AND reproducible.

The same doc<->code anti-drift guard as the six other versioned capabilities.
Deliberately NO audit-stamp test: the packaging policy is pinned through the
artifact itself (the package embeds package_version and the chain's
``packaged`` stamp carries the package file's SHA-256) rather than via a
seventh config stamp — see docs/packager-methodology.md.
"""

from __future__ import annotations

import json
from pathlib import Path

from okojo.packager import PACKAGE_VERSION, packager_config

_DOC = Path(__file__).resolve().parents[1] / "docs" / "packager-methodology.md"


def _doc_config() -> dict:
    """Extract the canonical JSON policy block embedded in the methodology doc."""
    text = _DOC.read_text(encoding="utf-8")
    lo = text.index("<!-- packager-config:begin -->")
    hi = text.index("<!-- packager-config:end -->")
    block = text[lo:hi]
    return json.loads(block[block.index("{"): block.rindex("}") + 1])


def test_methodology_doc_matches_code():
    """The doc's canonical policy block equals packager_config() exactly —
    the two can never silently drift."""
    assert _doc_config() == packager_config()


def test_methodology_doc_states_current_version():
    assert f"v{PACKAGE_VERSION}" in _DOC.read_text(encoding="utf-8")


def test_config_version_is_the_embedded_package_version():
    """One version, two surfaces: the config block and every emitted package
    carry the same PACKAGE_VERSION constant."""
    assert packager_config()["version"] == PACKAGE_VERSION
