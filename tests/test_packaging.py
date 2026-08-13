"""Packaging invariant: one version source (F-021).

``okojo.__version__`` derives from the installed distribution metadata, with a
source-tree fallback to ``pyproject.toml``. Either way it must equal the version
declared in ``pyproject.toml`` — so the importable version can never drift from
the packaged one, the way the stale hard-coded ``"0.0.1"`` attribute did.
"""

from __future__ import annotations

import tomllib
from pathlib import Path

import okojo

_PYPROJECT = Path(__file__).resolve().parents[1] / "pyproject.toml"


def _pyproject_version() -> str:
    with _PYPROJECT.open("rb") as fh:
        return tomllib.load(fh)["project"]["version"]


def test_version_matches_pyproject():
    assert okojo.__version__ == _pyproject_version()


def test_version_is_not_the_stale_literal():
    """Guard against a regression to the hard-coded ``0.0.1`` the audit flagged."""
    assert okojo.__version__ != "0.0.1"
