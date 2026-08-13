"""Okojo — an agentic crypto-investigations co-pilot (synthetic-data research prototype)."""


def _resolve_version() -> str:
    """The single version source.

    Derived from the installed distribution metadata, with a source-tree fallback
    that reads ``pyproject.toml`` directly for an editable / uninstalled checkout.
    Never a hand-maintained literal, so the importable ``okojo.__version__`` can
    never drift from the packaged version (asserted by ``tests/test_packaging.py``).
    """
    from importlib.metadata import PackageNotFoundError, version

    try:
        return version("okojo")
    except PackageNotFoundError:
        # Source checkout with no installed distribution (e.g. tests run against
        # src/ on sys.path): read the authoritative version from pyproject.toml.
        import tomllib
        from pathlib import Path

        pyproject = Path(__file__).resolve().parents[2] / "pyproject.toml"
        if pyproject.is_file():
            with pyproject.open("rb") as fh:
                return tomllib.load(fh)["project"]["version"]
        return "0+unknown"


__version__ = _resolve_version()
