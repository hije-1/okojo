"""Completeness tripwire for docs/code-map.md.

The code systems map is only trustworthy if it can never silently fall out of
sync with the source tree. This test enumerates the exact module set from the
filesystem — every non-package-init, non-test module under ``src/okojo/``, plus
the demo app and the data-generation script — and asserts the map documents
precisely that set, in BOTH directions:

- a module on disk with no entry in the map fails (someone added code and forgot
  to document it), and
- a map entry whose module no longer exists fails (someone moved/renamed a
  module and left the map stale).

So the map is a maintained inventory, not a hopeful one.
"""

from __future__ import annotations

import re
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
_MAP = _ROOT / "docs" / "code-map.md"

# A backtick-wrapped module path anywhere in the map. The map is authored so
# that only real module paths appear inside backticks ending in ``.py``.
_PATH_RE = re.compile(
    r"`(src/okojo/[\w/]+\.py|app/streamlit_app\.py|scripts/generate_scenario\.py)`"
)


def _filesystem_module_set() -> set[str]:
    """The Q8 module set, straight from the tree: non-__init__, non-test .py
    under src/okojo/, plus the demo app and the generate-scenario script."""
    mods: set[str] = set()
    for p in (_ROOT / "src" / "okojo").rglob("*.py"):
        if p.name == "__init__.py":
            continue
        mods.add(p.relative_to(_ROOT).as_posix())
    mods.add("app/streamlit_app.py")
    mods.add("scripts/generate_scenario.py")
    return mods


def _mapped_module_set() -> set[str]:
    return set(_PATH_RE.findall(_MAP.read_text(encoding="utf-8")))


def test_code_map_documents_every_module():
    """No module on disk is missing from the map."""
    missing = sorted(_filesystem_module_set() - _mapped_module_set())
    assert not missing, f"modules on disk but absent from docs/code-map.md: {missing}"


def test_code_map_has_no_stale_entries():
    """No map entry points at a module that no longer exists."""
    stale = sorted(_mapped_module_set() - _filesystem_module_set())
    assert not stale, f"docs/code-map.md documents modules that no longer exist: {stale}"


def test_code_map_set_is_exact():
    """Belt-and-braces: the two sets are identical."""
    assert _mapped_module_set() == _filesystem_module_set()
