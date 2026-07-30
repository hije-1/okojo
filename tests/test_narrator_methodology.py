"""Phase 9: the narration policy is explainable AND fixed to its version.

The eleventh doc<->code anti-drift guard, mirroring the ten versioned
capabilities. Deliberately NO audit-stamp test: the narrator writes nothing to
any chain, so — like the packager — its policy is pinned through the artifact
(every narrative embeds narrator_version) rather than via a config stamp. See
docs/narrator-methodology.md.
"""

from __future__ import annotations

import json
from pathlib import Path

from okojo.narrator import NARRATOR_VERSION, narrator_config

_DOC = Path(__file__).resolve().parents[1] / "docs" / "narrator-methodology.md"


def _doc_config() -> dict:
    """Extract the canonical JSON policy block embedded in the methodology doc."""
    text = _DOC.read_text(encoding="utf-8")
    lo = text.index("<!-- narrator-config:begin -->")
    hi = text.index("<!-- narrator-config:end -->")
    block = text[lo:hi]
    return json.loads(block[block.index("{"): block.rindex("}") + 1])


def test_methodology_doc_matches_code():
    """The doc's canonical policy block equals narrator_config() exactly —
    the two can never silently drift."""
    assert _doc_config() == narrator_config()


def test_methodology_doc_states_current_version():
    assert f"v{NARRATOR_VERSION}" in _DOC.read_text(encoding="utf-8")


def test_config_version_is_the_narrator_version():
    """One version, two surfaces: the config block and every emitted narrative
    carry the same NARRATOR_VERSION constant."""
    assert narrator_config()["version"] == NARRATOR_VERSION
